"""``manage.py tenancy_create_org --key K --name N --owner-email E --operator OPS``.

Creates an organization with no members and a ``pending`` owner invitation to ``E``
(``services.platform_org``, design.md §4.5, AC-TEN-22). ``--operator`` must be an email of
``PLATFORM_OPERATOR_EMAILS``, checked by ``_platform.operator_of`` as every operator command
(an operator not allowed is logged as a security WARNING, Q-241).
The invitation link goes to stdout once, never through the logger: whoever runs the command
hands it to the owner. Running it again with the same ``--key`` and values creates nothing and
says so (Q-123); with other values it is refused. Either repeat is audited as
``organization.create_repeated`` (Q-235).

Exit codes: ``0`` created, or already created with these values; ``1`` the key belongs to other
values, or ``FRONTEND_BASE_URL`` is not set (nothing written in either case); ``2`` a bad argument
(argparse's own code, and ours for an operator not in the allowlist or an invalid value).
Messages carry ids only, never an email.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.tenancy.domain.invitations import INVITATION_TTL
from apps.tenancy.management.commands._platform import operator_of
from apps.tenancy.services.platform_org import (
    CreationKeyConflictError,
    InvalidOrgRequestError,
    PlatformOrg,
    clean_request,
    create_platform_org,
)

CONFLICT_EXIT = 1
USAGE_EXIT = 2


class Command(BaseCommand):
    help = (
        "Create an organization and its owner invitation (audited; platform operator only). "
        "Prints the invitation link once."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--key", required=True, help="Idempotency key, unique (max. 64).")
        parser.add_argument("--name", required=True, help="Name of the organization (max. 120).")
        parser.add_argument("--owner-email", required=True, help="Email of the first owner.")
        parser.add_argument(
            "--operator",
            required=True,
            help="Your email in PLATFORM_OPERATOR_EMAILS; audited with the OS user.",
        )

    def handle(
        self,
        *args: object,
        key: str,
        name: str,
        owner_email: str,
        operator: str,
        **options: object,
    ) -> None:
        actor = operator_of(operator, self)
        try:
            request = clean_request(key=key, name=name, owner_email=owner_email)
            result = create_platform_org(request, actor)
        except InvalidOrgRequestError as error:
            raise CommandError(str(error), returncode=USAGE_EXIT) from None
        except CreationKeyConflictError as error:
            raise CommandError(
                f"The key already created organization {error.organization_id} with another name "
                "or owner email; nothing changed.",
                returncode=CONFLICT_EXIT,
            ) from None
        except ImproperlyConfigured as error:
            raise CommandError(str(error), returncode=CONFLICT_EXIT) from None
        self.stdout.write(self.report(result))

    def report(self, result: PlatformOrg) -> str:
        if not result.created:
            return (
                f"Organization {result.organization_id} already exists with this key and these "
                "values; nothing changed and no new link was issued."
            )
        return (
            f"Organization {result.organization_id} created; owner invitation "
            f"{result.invitation_id}, valid for {INVITATION_TTL.days} days.\n"
            "Send this link to the owner; it is shown only this once:\n"
            f"{result.accept_url}"
        )
