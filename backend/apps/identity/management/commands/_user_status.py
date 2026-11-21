"""What ``deactivate_user`` and ``reactivate_user`` share (design.md §6.5); not a command itself.

Arguments: ``--email`` or ``--user-id`` (exactly one), ``--operator`` (required) and ``--reason``.
``--operator`` is an email of ``PLATFORM_OPERATOR_EMAILS``, checked by
``apps.common.platform_operators`` as every operator command does (decision of 2026-11-14,
T-TEN-18); the operator is that email plus the user of the operating system (``PlatformOperator``).

Exit codes: ``0`` the change was made or the user was already in that state (said on stdout);
``1`` no user matches; ``2`` a bad argument (argparse's own code, and ours for an ``--operator``
not in the allowlist or an invalid ``--reason``). Messages name the user by id only: never the
email given, so a mistyped address of somebody else does not end up in a terminal log either.
"""

from __future__ import annotations

import uuid
from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.common.platform_operators import allowed_operator, os_user
from apps.identity.services.user_status import (
    PlatformOperator,
    StatusChange,
    UserNotFoundError,
    UserTarget,
)

NOT_FOUND_EXIT = 1
USAGE_EXIT = 2


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise ArgumentTypeError("not a UUID") from error


class UserStatusCommand(BaseCommand):
    done: str
    unchanged: str

    def change(
        self, *, target: UserTarget, operator: PlatformOperator, note: str | None, now: datetime
    ) -> StatusChange:
        raise NotImplementedError

    def add_arguments(self, parser: ArgumentParser) -> None:
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--email", help="The user's email (trimmed and lowercased).")
        target.add_argument("--user-id", type=parse_uuid, help="The user's id (UUID).")
        parser.add_argument(
            "--operator",
            required=True,
            help="Your email in PLATFORM_OPERATOR_EMAILS; audited with the OS user.",
        )
        parser.add_argument("--reason", default=None, help="Optional note for the audit event.")

    def handle(
        self,
        *args: object,
        email: str | None,
        user_id: uuid.UUID | None,
        operator: str,
        reason: str | None,
        **options: object,
    ) -> None:
        try:
            actor = PlatformOperator(name=allowed_operator(operator), os_user=os_user())
            target = UserTarget(user_id=user_id, email=email)
            change = self.change(target=target, operator=actor, note=reason, now=timezone.now())
        except UserNotFoundError as error:
            raise CommandError("No user matches.", returncode=NOT_FOUND_EXIT) from error
        except ValueError as error:
            raise CommandError(str(error), returncode=USAGE_EXIT) from error
        self.stdout.write(self.report(change))

    def report(self, change: StatusChange) -> str:
        template = self.done if change.changed else self.unchanged
        return template.format(user_id=change.user_id, revoked=change.revoked_sessions)
