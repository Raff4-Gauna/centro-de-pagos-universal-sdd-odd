"""``manage.py tenancy_owner_recovery --org ID --email E --reason R --operator OPS``.

Issues an ``owner`` invitation with ``purpose=owner_recovery`` to an organization that has an owner
(``services.platform_access``, design.md §4.5, Q-224): when its only owner lost the Google account,
for instance. A mandatory ``--reason`` (Q-225). Nobody is revoked: the current owners stay, and
they can revoke the new one, accepted or not. Without an owner, the first owner's invitation is the
way (``tenancy_owner_invite``, Q-213). The existing owners are not notified yet: there is no email
provider (Q-224). The link is printed once, never through the logger. ``--operator`` must be an
email of ``PLATFORM_OPERATOR_EMAILS`` (``apps.common.platform_operators``, as every operator
command).

Exit codes: ``0`` issued; ``1`` refused with nothing changed (unknown organization, one without an
active owner, an active member or a valid ``pending`` invitation with that email, or no
``FRONTEND_BASE_URL``); ``2`` a bad argument (argparse's own code, and ours for an operator not in
the allowlist, an id that is not a UUID, an invalid ``--email`` or a blank reason). Messages carry
ids only, never an email nor the reason.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.common.tenancy.errors import OrganizationNotFound
from apps.tenancy.domain.invitations import INVITATION_TTL
from apps.tenancy.management.commands._platform import (
    OPERATOR_HELP,
    ORG_HELP,
    REFUSED_EXIT,
    USAGE_EXIT,
    operator_of,
    organization_id,
)
from apps.tenancy.services.invitations import InvitationPending, InviteeAlreadyMember
from apps.tenancy.services.platform_access import (
    InvalidInviteeEmailError,
    OrganizationWithoutOwnerError,
    issue_owner_recovery,
)
from apps.tenancy.services.platform_org_status import InvalidReasonError

REFUSALS: dict[type[Exception], str] = {
    OrganizationNotFound: "does not exist",
    OrganizationWithoutOwnerError: (
        "has no active owner: reissue the first owner's invitation (tenancy_owner_invite)"
    ),
    InviteeAlreadyMember: "already has an active member with that email",
    InvitationPending: "already has a pending invitation to that email",
}


class Command(BaseCommand):
    help = (
        "Issue an owner recovery invitation to an organization that has an owner; revokes "
        "nobody (audited; platform operator only). Prints the link once."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--org", required=True, help=ORG_HELP)
        parser.add_argument("--email", required=True, help="The new owner's email.")
        parser.add_argument("--reason", required=True, help="Why (audited; max. 200).")
        parser.add_argument("--operator", required=True, help=OPERATOR_HELP)

    def handle(
        self, *args: object, org: str, email: str, reason: str, operator: str, **options: object
    ) -> None:
        actor, target = operator_of(operator), organization_id(org)
        try:
            issued = issue_owner_recovery(target, email, reason, actor)
        except (InvalidInviteeEmailError, InvalidReasonError) as error:
            raise CommandError(str(error), returncode=USAGE_EXIT) from None
        except (
            OrganizationNotFound,
            OrganizationWithoutOwnerError,
            InviteeAlreadyMember,
            InvitationPending,
        ) as error:
            raise CommandError(
                f"Organization {target} {REFUSALS[type(error)]}; nothing changed.",
                returncode=REFUSED_EXIT,
            ) from None
        except ImproperlyConfigured as error:
            raise CommandError(f"{error}; nothing changed.", returncode=REFUSED_EXIT) from None
        self.stdout.write(
            f"Owner recovery invitation {issued.invitation_id} to organization {target} issued; "
            f"valid for {INVITATION_TTL.days} days. Nobody was revoked: its {issued.owners} "
            "current owner(s) stay, and are not notified by email (no provider yet).\n"
            "Send this link to the new owner; it is shown only this once:\n"
            f"{issued.accept_url}"
        )
