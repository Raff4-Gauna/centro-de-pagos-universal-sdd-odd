"""What ``deactivate_user`` and ``reactivate_user`` share (design.md §6.5); not a command itself.

Arguments: ``--email`` or ``--user-id`` (exactly one), ``--operator`` (required) and ``--reason``.
The operator is the declared name plus the user of the operating system (``PlatformOperator``).

Exit codes: ``0`` the change was made or the user was already in that state (said on stdout);
``1`` no user matches; ``2`` a bad argument (argparse's own code, and ours for an invalid
``--operator`` or ``--reason``). Messages name the user by id only: never the email given, so a
mistyped address of somebody else does not end up in a terminal log either.
"""

from __future__ import annotations

import getpass
import uuid
from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.identity.services.user_status import (
    PlatformOperator,
    StatusChange,
    UserNotFoundError,
    UserTarget,
)

NOT_FOUND_EXIT = 1
USAGE_EXIT = 2
UNKNOWN_OS_USER = "unknown"


def os_user() -> str:
    """The user of the operating system running the command, or ``unknown`` if it has none."""
    try:
        return getpass.getuser() or UNKNOWN_OS_USER
    except (OSError, KeyError):  # no USER/LOGNAME and no passwd entry (a bare container)
        return UNKNOWN_OS_USER


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
            "--operator", required=True, help="Who runs this; audited with the OS user."
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
            actor = PlatformOperator(name=operator, os_user=os_user())
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
