"""``manage.py tenancy_support_access --org ID --email E [--role R] --reason R --operator OPS``.

Issues a support invitation to an organization (``services.platform_access``, design.md §4.5,
Q-222): ``purpose=support``, ``--role`` ``admin``, ``operator`` or ``viewer`` (the default), never
``owner``, and a mandatory ``--reason`` (Q-225). Being the operator gives no access by itself
(RN-TEN-20): the person at ``--email`` gets in by accepting it, and then is a normal member, visible
and revocable by the owners. Only for an organization with an active owner (Q-238): before that,
the first owner's commands (``tenancy_owner_invite``, Q-213, Q-236). The link is printed once,
never through the logger. ``--operator`` must be an email of ``PLATFORM_OPERATOR_EMAILS``
(``apps.common.platform_operators``, as every operator command).

Exit codes: ``0`` issued; ``1`` refused with nothing changed (unknown organization, one without an
active owner, an active member or a valid ``pending`` invitation with that email, or no
``FRONTEND_BASE_URL``); ``2`` a bad
argument (argparse's own code, also for ``--role owner``, and ours for an operator not in the
allowlist, an id that is not a UUID, an invalid ``--email`` or a blank reason). Messages carry ids
only, never an email nor the reason.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.common.authz.roles import Role
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
    DEFAULT_SUPPORT_ROLE,
    SUPPORT_ROLES,
    InvalidInviteeEmailError,
    OrganizationWithoutOwnerError,
    grant_support_access,
)
from apps.tenancy.services.platform_org_status import InvalidReasonError

REFUSALS: dict[type[Exception], str] = {
    OrganizationNotFound: "does not exist",
    OrganizationWithoutOwnerError: (
        "has no active owner yet: issue the first owner's invitation (tenancy_owner_invite)"
    ),
    InviteeAlreadyMember: "already has an active member with that email",
    InvitationPending: "already has a pending invitation to that email",
}


class Command(BaseCommand):
    help = (
        "Issue a support invitation to an organization, never owner (audited; platform "
        "operator only). Prints the link once."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--org", required=True, help=ORG_HELP)
        parser.add_argument("--email", required=True, help="Who gets in (the invitee's email).")
        parser.add_argument(
            "--role",
            choices=[role.value for role in SUPPORT_ROLES],
            default=DEFAULT_SUPPORT_ROLE.value,
            help=f"Role of the membership (default: {DEFAULT_SUPPORT_ROLE.value}).",
        )
        parser.add_argument("--reason", required=True, help="Why (audited; max. 200).")
        parser.add_argument("--operator", required=True, help=OPERATOR_HELP)

    def handle(
        self,
        *args: object,
        org: str,
        email: str,
        reason: str,
        operator: str,
        role: str = DEFAULT_SUPPORT_ROLE.value,
        **options: object,
    ) -> None:
        actor, target = operator_of(operator, self), organization_id(org)
        try:
            issued = grant_support_access(target, email, reason, actor, role=Role(role))
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
            f"Support invitation {issued.invitation_id} to organization {target} issued, "
            f"role {issued.role.value}; valid for {INVITATION_TTL.days} days.\n"
            "Accepted, it is a normal membership that the owners see and can revoke.\n"
            "Open this link with the invited account; it is shown only this once:\n"
            f"{issued.accept_url}"
        )
