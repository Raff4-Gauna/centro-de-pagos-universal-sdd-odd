"""``manage.py reactivate_user (--email E | --user-id U) --operator NAME [--reason TEXT]``.

The person may log in again; the sessions the deactivation ended stay ended, so they have to
(RN-IDA-07, AC-IDA-27). Audited as ``identity.user_reactivated``, actor the platform operator. On a
user already active it does nothing and says so. Exit codes: ``_user_status``.
"""

from __future__ import annotations

from datetime import datetime

from apps.identity.management.commands._user_status import UserStatusCommand
from apps.identity.services.user_status import (
    PlatformOperator,
    StatusChange,
    UserTarget,
    reactivate_user,
)


class Command(UserStatusCommand):
    help = "Reactivate a user; their old sessions stay revoked (audited; platform operator only)."
    done = "User {user_id} reactivated; they have to log in again."
    unchanged = "User {user_id} was already active; nothing changed."

    def change(
        self, *, target: UserTarget, operator: PlatformOperator, note: str | None, now: datetime
    ) -> StatusChange:
        return reactivate_user(target=target, operator=operator, note=note, now=now)
