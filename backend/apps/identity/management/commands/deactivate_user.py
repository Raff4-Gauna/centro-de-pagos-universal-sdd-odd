"""``manage.py deactivate_user (--email E | --user-id U) --operator NAME [--reason TEXT]``.

The person can no longer log in nor refresh, and every session of theirs ends now: the next request
with any of their JWTs answers ``401 session_revoked`` (RN-IDA-07, AC-IDA-27). Audited as
``identity.user_deactivated`` plus one ``identity.session_revoked`` per session, actor the platform
operator. On a user already inactive it does nothing and says so. Exit codes: ``_user_status``.
"""

from __future__ import annotations

from datetime import datetime

from apps.identity.management.commands._user_status import UserStatusCommand
from apps.identity.services.user_status import (
    PlatformOperator,
    StatusChange,
    UserTarget,
    deactivate_user,
)


class Command(UserStatusCommand):
    help = "Deactivate a user and revoke all their sessions (audited; platform operator only)."
    done = "User {user_id} deactivated; {revoked} session(s) revoked."
    unchanged = "User {user_id} was already inactive; nothing changed."

    def change(
        self, *, target: UserTarget, operator: PlatformOperator, note: str | None, now: datetime
    ) -> StatusChange:
        return deactivate_user(target=target, operator=operator, note=note, now=now)
