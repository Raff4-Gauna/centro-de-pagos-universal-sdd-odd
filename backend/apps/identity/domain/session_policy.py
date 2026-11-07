"""How long a session lives and what a refresh does (RN-IDA-10, RN-IDA-11, ADR-0004 §3).

Pure: the caller passes ``now`` and the stored values. Only ``absolute_expiry`` produces an absolute
deadline, and it starts from the login: a refresh has no way to move it (AC-IDA-16).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
IDLE_LIFETIME = timedelta(days=7)
ABSOLUTE_LIFETIME = timedelta(days=30)
REFRESH_GRACE = timedelta(seconds=30)


class RefreshDecision(StrEnum):
    ROTATE = "rotate"
    GRACE = "grace"
    REUSE = "reuse"


def absolute_expiry(created_at: datetime) -> datetime:
    return created_at + ABSOLUTE_LIFETIME


def idle_expiry(now: datetime, absolute_expires_at: datetime) -> datetime:
    """Idle deadline after a use at ``now``, capped by the absolute one."""
    return min(now + IDLE_LIFETIME, absolute_expires_at)


def is_expired(*, idle_expires_at: datetime, absolute_expires_at: datetime, now: datetime) -> bool:
    """At the deadline it is already expired: a session lives while ``deadline > now``."""
    return now >= min(idle_expires_at, absolute_expires_at)


def decide_refresh(
    *, used_at: datetime | None, successor_is_live: bool, now: datetime
) -> RefreshDecision:
    """What to do with a known token of a session already checked as active and not expired.

    ``used_at`` is the token's mark; ``successor_is_live`` says whether the token that replaced it
    is the session's live one. Without that second condition, a token stolen and replayed right
    after a chain of rotations would pass as a concurrent tab.
    """
    if used_at is None:
        return RefreshDecision.ROTATE
    if successor_is_live and now - used_at <= REFRESH_GRACE:
        return RefreshDecision.GRACE
    return RefreshDecision.REUSE
