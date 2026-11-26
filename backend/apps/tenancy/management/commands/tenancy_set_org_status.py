"""``manage.py tenancy_set_org_status --org ID --status suspended|active --reason R --operator O``.

Suspends or reactivates an organization (``services.platform_org_status``, design.md §4.5,
RN-TEN-18): the only way to change its status, which no route of the API offers (AC-TEN-29).
Suspended, its members only read and the server-to-server processing of ``pending`` charges goes
on (§4.1, AC-TEN-28). ``--operator`` must be an email of ``PLATFORM_OPERATOR_EMAILS``
(``apps.common.platform_operators``, as every operator command); ``--reason`` goes to the audit
event only.

Exit codes: ``0`` changed; ``1`` refused with nothing changed (unknown organization, or it already
has that status: audited as ``transition.rejected``); ``2`` a bad argument (argparse's own code,
and ours for an operator not in the allowlist, an id that is not a UUID or a blank reason).
Messages carry ids only, never an email nor the reason.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.errors import OrganizationNotFound
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.management.commands._platform import (
    OPERATOR_HELP,
    ORG_HELP,
    REFUSED_EXIT,
    USAGE_EXIT,
    operator_of,
    organization_id,
)
from apps.tenancy.services.platform_org_status import (
    InvalidReasonError,
    clean_reason,
    set_org_status,
)


class Command(BaseCommand):
    help = "Suspend or reactivate an organization (audited; platform operator only)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--org", required=True, help=ORG_HELP)
        parser.add_argument(
            "--status", required=True, choices=[status.value for status in OrgStatus]
        )
        parser.add_argument("--reason", required=True, help="Why (audited; max. 200).")
        parser.add_argument("--operator", required=True, help=OPERATOR_HELP)

    def handle(
        self, *args: object, org: str, status: str, reason: str, operator: str, **options: object
    ) -> None:
        actor = operator_of(operator, self)
        target_id, target = organization_id(org), OrgStatus(status)
        try:
            clean = clean_reason(reason)
        except InvalidReasonError as error:
            raise CommandError(str(error), returncode=USAGE_EXIT) from None
        try:
            set_org_status(target_id, target, clean, actor)
        except OrganizationNotFound:
            raise CommandError(
                f"Organization {target_id} does not exist; nothing changed.",
                returncode=REFUSED_EXIT,
            ) from None
        except InvalidTransition:
            raise CommandError(
                f"Organization {target_id} is already {target.value}; nothing changed.",
                returncode=REFUSED_EXIT,
            ) from None
        self.stdout.write(f"Organization {target_id} is now {target.value}.")
