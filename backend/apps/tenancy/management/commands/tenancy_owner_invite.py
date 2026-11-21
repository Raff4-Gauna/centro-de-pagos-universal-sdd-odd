"""``manage.py tenancy_owner_invite reissue|revoke --org ID --operator OPS``.

Renews or withdraws the first owner's invitation of an organization that has no owner yet
(``services.platform_owner_invite``, design.md §4.5, Q-213). ``reissue`` replaces a ``pending`` or
``expired`` one with a new one to the same email, valid for seven days, and prints its link once,
never through the logger. ``revoke`` withdraws the ``pending`` one. ``--operator`` must be an email
of ``PLATFORM_OPERATOR_EMAILS`` (``apps.common.platform_operators``, as every operator command).

Exit codes: ``0`` done; ``1`` refused with nothing changed (unknown organization, it already has an
owner, it has no first owner invitation, the invitation is in a state that does not allow it,
which is audited as ``transition.rejected``, another ``pending`` invitation to that email, or no
``FRONTEND_BASE_URL``); ``2`` a bad argument (argparse's own code, and ours for an operator not in
the allowlist or an id that is not a UUID). Messages carry ids only, never an email.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.common.tenancy.errors import OrganizationNotFound
from apps.tenancy.domain.invitations import INVITATION_TTL
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.management.commands._platform import (
    OPERATOR_HELP,
    ORG_HELP,
    REFUSED_EXIT,
    operator_of,
    organization_id,
)
from apps.tenancy.services.invitations import InvitationPending
from apps.tenancy.services.platform_owner_invite import (
    REISSUE,
    REVOKE,
    NoOwnerInvitationError,
    OrganizationHasOwnerError,
    reissue_owner_invitation,
    revoke_owner_invitation,
)


class Command(BaseCommand):
    help = (
        "Reissue or revoke the first owner's invitation of an organization without owner "
        "(audited; platform operator only). A reissue prints the new link once."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("action", choices=[REISSUE, REVOKE])
        parser.add_argument("--org", required=True, help=ORG_HELP)
        parser.add_argument("--operator", required=True, help=OPERATOR_HELP)

    def handle(
        self, *args: object, action: str, org: str, operator: str, **options: object
    ) -> None:
        actor, target = operator_of(operator), organization_id(org)
        try:
            if action == REVOKE:
                revoked = revoke_owner_invitation(target, actor)
                self.stdout.write(f"Owner invitation {revoked} of organization {target} revoked.")
                return
            reissued = reissue_owner_invitation(target, actor)
        except (
            OrganizationNotFound,
            OrganizationHasOwnerError,
            NoOwnerInvitationError,
            InvalidTransition,
            InvitationPending,
            ImproperlyConfigured,
        ) as error:
            raise CommandError(self.refusal(target, error), returncode=REFUSED_EXIT) from None
        self.stdout.write(
            f"Owner invitation {reissued.invitation_id} of organization {target} issued, "
            f"replacing {reissued.replaces}; valid for {INVITATION_TTL.days} days.\n"
            "Send this link to the owner; it is shown only this once:\n"
            f"{reissued.accept_url}"
        )

    def refusal(self, target: object, error: Exception) -> str:
        reasons = {
            OrganizationNotFound: "does not exist",
            OrganizationHasOwnerError: "already has an owner, who manages its invitations",
            NoOwnerInvitationError: "has no first owner invitation",
            InvalidTransition: "has a first owner invitation in a state that does not allow it",
            InvitationPending: "has another pending invitation to that email",
        }
        reason = reasons.get(type(error))
        if reason is None:
            return f"{error}; nothing changed."
        return f"Organization {target} {reason}; nothing changed."
