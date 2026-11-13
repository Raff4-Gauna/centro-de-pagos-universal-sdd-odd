"""Logout of the current session (RF-IDA-05, RN-IDA-14, design.md §4.6, §7.4).

``logout`` gets what the BFF holds of the session, the refresh token of ``__Host-cpu_rt`` and the
access JWT of ``__Host-cpu_at`` (either, both or none), and ends that session. It always lets the
caller answer ``204``: it raises on nothing a client sends, only on a ``reason`` the BFF may not
use. Order:

1. **Which session.** The refresh token first: its SHA-256 and the ``sid`` it names, whether it is
   the live token or a used one (a tab may still hold the one rotated in the grace window). If that
   finds nothing, the JWT: a valid signature is enough, however long ago it expired (AC-IDA-35),
   and its ``sub`` must be the session's user. Neither → no effects.
2. **Lock order.** Only the session row is locked (``SELECT … FOR UPDATE``); the token is read
   without a lock, since the session a token belongs to never changes. A refresh locks the token
   and then the session (``services/refresh.py``), so the two never hold one lock each waiting for
   the other: a logout waits for a refresh in flight, or the refresh for the logout, and then finds
   the session revoked. Whoever adds a lock here takes it in that same order: token, then session.
3. **What it does.** An ``active`` session within its deadlines is revoked with ``reason`` and
   audited in the same transaction: ``identity.logout`` for ``logout``, ``identity.session_revoked``
   with ``superseded`` for the login over a previous session (ADR-0004 §13). One already past a
   deadline is marked ``expired``, as a refresh would, and is not audited: it had already ended.
   Anything else (revoked, expired, unknown) is left as it is: the second logout has no effects.

Nothing logged carries a token or its hash (RNF-IDA-03): the ``sid``, the ``user_id``, the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.common.logging import get_logger
from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
    SessionRevocationReason,
)
from apps.identity.domain.errors import MalformedRefreshTokenError
from apps.identity.domain.secrets_format import hash_secret, parse_refresh_token
from apps.identity.domain.session_policy import is_expired
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.services.session_lifecycle import expire, revoke
from apps.identity.tokens.access_token import (
    AccessTokenError,
    verify_access_token_ignoring_expiry,
)

LOGOUT_EVENT = "identity.logout"
LOGOUT_REASONS = frozenset({RevokeReason.LOGOUT, RevokeReason.SUPERSEDED})

logger = get_logger(__name__)


class LogoutResult(StrEnum):
    REVOKED = "revoked"
    EXPIRED = "expired"  # it was past a deadline: marked, not logged out
    ALREADY_ENDED = "already_ended"
    NO_SESSION = "no_session"


@dataclass(frozen=True)
class _SessionRef:
    session_id: UUID
    user_id: UUID | None  # known from a JWT; a refresh token's hash already proves the session


def logout(
    *,
    refresh_token: str | None = None,
    access_token: str | None = None,
    reason: RevokeReason = RevokeReason.LOGOUT,
    now: datetime,
) -> bool:
    """End the session those tokens name; ``True`` only if this call revoked it."""
    if reason not in LOGOUT_REASONS:
        raise ValueError("logout ends a session only for logout or superseded")
    ref = _by_refresh_token(refresh_token) or _by_access_token(access_token)
    if ref is None:
        logger.info(LOGOUT_EVENT, result=LogoutResult.NO_SESSION.value)
        return False
    with transaction.atomic():
        result, user_id = _end_locked(ref, reason=reason, now=now)
    # ``sid`` as in the JWT: any key holding "session" is redacted from the logs (C-06).
    ids = {"sid": str(ref.session_id)} if user_id is None else _ids(ref.session_id, user_id)
    logger.info(LOGOUT_EVENT, result=result.value, reason=reason.value, **ids)
    return result is LogoutResult.REVOKED


def _by_refresh_token(raw: str | None) -> _SessionRef | None:
    if not raw:
        return None
    try:
        session_id = parse_refresh_token(raw)
    except MalformedRefreshTokenError:
        return None
    # Live or used, no lock (point 2): the hash and the sid of the token, both.
    known = RefreshToken.objects.filter(token_hash=hash_secret(raw), session_id=session_id)
    if not known.exists():
        return None
    return _SessionRef(session_id=session_id, user_id=None)


def _by_access_token(raw: str | None) -> _SessionRef | None:
    if not raw:
        return None
    try:
        identity = verify_access_token_ignoring_expiry(raw)
    except AccessTokenError:
        return None
    return _SessionRef(session_id=identity.session_id, user_id=identity.user_id)


def _end_locked(
    ref: _SessionRef, *, reason: RevokeReason, now: datetime
) -> tuple[LogoutResult, UUID | None]:
    found = AuthSession.objects.select_for_update().filter(pk=ref.session_id)
    if ref.user_id is not None:
        found = found.filter(user_id=ref.user_id)
    session = found.first()
    if session is None:
        return LogoutResult.NO_SESSION, None
    if session.status != SessionStatus.ACTIVE:
        return LogoutResult.ALREADY_ENDED, session.user_id
    if is_expired(
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
        now=now,
    ):
        expire(session.pk, now=now)
        return LogoutResult.EXPIRED, session.user_id
    revoke(session.pk, reason=reason, now=now)
    _audit(session, reason=reason, now=now)
    return LogoutResult.REVOKED, session.user_id


def _audit(session: AuthSession, *, reason: RevokeReason, now: datetime) -> None:
    """Inside the transaction of the revocation (design.md §7.4): both happen or neither."""
    if reason == RevokeReason.LOGOUT:
        action, audit_reason = IdentityAuditAction.LOGOUT, None
    else:
        action = IdentityAuditAction.SESSION_REVOKED
        audit_reason = SessionRevocationReason.SUPERSEDED.value
    get_audit_port().record(
        AuditEvent(
            action=action,
            result=AuditResult.SUCCESS,
            reason=audit_reason,
            actor_type=AuditActorType.USER,
            actor_id=session.user_id,
            occurred_at=now,
            metadata={"sid": str(session.pk)},
        )
    )


def _ids(session_id: UUID, user_id: UUID) -> dict[str, str]:
    return {"sid": str(session_id), "user_id": str(user_id)}
