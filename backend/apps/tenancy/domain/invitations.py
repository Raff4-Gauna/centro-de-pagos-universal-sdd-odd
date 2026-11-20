"""Pure rules of an invitation (RN-TEN-12, Q-206, RNF-TEN-03, design.md §5). No Django.

- **Email** (AC-TEN-35): ``normalize_email`` trims the ends and lowercases the whole address, and
  nothing else: dots and ``+`` aliases are other addresses. It keeps the contract of identity's
  normalizer (RN-IDA-05, Q-107) without importing it, because ``domain/`` imports no other app; a
  shared table of cases proves both agree. Checking that the text *is* an email (``EmailValidator``,
  at most 254) belongs where the input enters (serializer or command), not here.
- **Expiry** (AC-TEN-25): seven days from issue, valid while ``now < expires_at``, in UTC. The clock
  is a parameter: every function gets ``now`` or ``issued_at`` from the caller and none reads it, so
  the edge (``T + 7d - 1min`` accepts, ``T + 7d`` does not) is a unit test. A naive datetime raises.
- **Token** (RNF-TEN-03): ``new_token`` has 256 bits of entropy and is shown once; the row keeps
  only ``hash_token(token)``, its SHA-256 in hex (64 characters). Nothing here logs.
- **Accepting** (AC-TEN-17/18/19/25/35, design.md §4.4): ``decide_accept`` gives the
  ``InvalidReason`` of an invitation that cannot be accepted, or ``None``, in the order of the
  diagram: another email first, then a status other than ``pending``, then the clock. What needs the
  database (a suspended organization, already a member) is the service's.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from enum import StrEnum

INVITATION_TTL = timedelta(days=7)
TOKEN_BYTES = 32  # 256 bits
TOKEN_HASH_LENGTH = 64


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InvitationPurpose(StrEnum):
    """Why it was issued: the operator ones carry a reason (Q-213, Q-222, Q-224, Q-225)."""

    STANDARD = "standard"
    FIRST_OWNER = "first_owner"
    SUPPORT = "support"
    OWNER_RECOVERY = "owner_recovery"


OPERATOR_PURPOSES = frozenset({InvitationPurpose.SUPPORT, InvitationPurpose.OWNER_RECOVERY})


class RevokedReason(StrEnum):
    REVOKED = "revoked"
    RESENT = "resent"
    INVITER_LOST_PERMISSION = "inviter_lost_permission"  # Q-223
    OPERATOR = "operator"


class InvalidReason(StrEnum):
    """The ``reason`` of ``invitation_invalid`` (design.md §6); never says more than this."""

    NOT_FOUND = "not_found"
    EMAIL_MISMATCH = "email_mismatch"
    REVOKED = "revoked"
    USED = "used"
    EXPIRED = "expired"


# A status other than ``pending`` and what it answers: ``accepted`` is a token used already.
_CLOSED = {
    InvitationStatus.ACCEPTED: InvalidReason.USED,
    InvitationStatus.REVOKED: InvalidReason.REVOKED,
    InvitationStatus.EXPIRED: InvalidReason.EXPIRED,
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def emails_match(invited_email: str, user_email: str) -> bool:
    """The authenticated user may accept: same address after ``normalize_email`` (AC-TEN-35)."""
    return normalize_email(invited_email) == normalize_email(user_email)


def _require_aware(moment: datetime, name: str) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def expires_at_for(issued_at: datetime) -> datetime:
    _require_aware(issued_at, "issued_at")
    return issued_at + INVITATION_TTL


def is_expired(expires_at: datetime, now: datetime) -> bool:
    """Expired from ``expires_at`` on: valid only while ``now < expires_at`` (RN-TEN-12)."""
    _require_aware(expires_at, "expires_at")
    _require_aware(now, "now")
    return now >= expires_at


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    if not token:
        raise ValueError("an empty token has no hash")
    return hashlib.sha256(token.encode()).hexdigest()


def decide_accept(
    *,
    status: InvitationStatus,
    expires_at: datetime,
    invited_email: str,
    user_email: str,
    now: datetime,
) -> InvalidReason | None:
    """Why the user cannot accept it, or ``None`` if the invitation itself allows it."""
    if not emails_match(invited_email, user_email):
        return InvalidReason.EMAIL_MISMATCH
    closed = _CLOSED.get(InvitationStatus(status))
    if closed is not None:
        return closed
    if is_expired(expires_at, now):
        return InvalidReason.EXPIRED
    return None
