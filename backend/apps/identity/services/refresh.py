"""Refresh a session (RF-IDA-04, RN-IDA-10, RN-IDA-11, design.md §4.5, ADR-0004 §3 and §12).

``refresh_session`` takes the refresh token the BFF holds and ``now``, one reading of the clock for
every mark it writes or compares (``used_at``, ``last_used_at``, the deadlines and the JWT). Order
of design.md §4.5, all inside one transaction:

1. The text must be ``rt1.<sid>.<secret>`` (``token_invalid``, without the database).
2. The token is looked up by its SHA-256 and the session it names, ``SELECT … FOR UPDATE``; then its
   session, ``FOR UPDATE`` too. Unknown → ``token_invalid``. Every refresh of a session waits for
   the one before it, so two of them never decide on the same state.
3. The session must be ``active`` (``session_revoked``); past a deadline it is marked ``expired`` on
   the spot (``ended_at = idle_expires_at``) and answers ``session_revoked``; so does an inactive
   user (AC-IDA-09). These checks come before anything is issued: ``issue_refresh_token`` does not
   look at the session, it trusts its caller.
4. ``session_policy.decide_refresh`` says what the token is worth:
   - **rotate** (unused): the token is marked used, a new one replaces it, the session moves
     ``last_used_at`` and its idle deadline (never past the absolute one, which nothing here
     writes: AC-IDA-16) → a new pair (AC-IDA-14).
   - **grace** (used ≤ 30 s ago and its successor is the live one): a new access token only,
     ``refresh_token=None``; nothing is written or audited (AC-IDA-28).
   - **reuse** (anything else): the session is revoked (``refresh_reuse``), audited as
     ``refresh_reuse_detected`` and ``session_revoked`` with an alert → ``session_revoked``
     (AC-IDA-15). The live token of the session dies with it: a revoked session refreshes nothing.

A rejection is raised only after the transaction commits, so an ``expired`` or a revocation stays.
Nothing logged carries the token or its hash (RNF-IDA-03): ids (``sid``, ``user_id``), the outcome
and the code only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Subquery

from apps.common.logging import get_logger
from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
    SessionRevocationReason,
)
from apps.identity.domain.errors import (
    IdentityError,
    IdentityErrorCode,
    MalformedRefreshTokenError,
)
from apps.identity.domain.secrets_format import hash_secret, parse_refresh_token
from apps.identity.domain.session_policy import (
    RefreshDecision,
    decide_refresh,
    idle_expiry,
    is_expired,
)
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.services.session_lifecycle import expire, issue_refresh_token, revoke
from apps.identity.tokens.access_token import issue_access_token

REFRESHED_EVENT = "identity.refresh_succeeded"
REJECTED_EVENT = "identity.refresh_rejected"
REUSE_EVENT = "identity.refresh_reuse_detected"

logger = get_logger(__name__)


@dataclass(frozen=True)
class RefreshedSession:
    """What the BFF gets. ``refresh_token`` is ``None`` in the grace window (design.md §6.1)."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    session_expires_in: int
    decision: RefreshDecision
    user_id: UUID


class RefreshRejectedError(IdentityError):
    """``token_invalid`` or ``session_revoked``; it carries the code and nothing else."""


def refresh_session(raw_token: str, *, now: datetime) -> RefreshedSession:
    try:
        session_id = parse_refresh_token(raw_token)
    except MalformedRefreshTokenError:
        logger.info(REJECTED_EVENT, reason=IdentityErrorCode.TOKEN_INVALID.value)
        raise
    with transaction.atomic():
        outcome = _refresh_locked(raw_token, session_id, now=now)
    if isinstance(outcome, IdentityErrorCode):
        logger.info(REJECTED_EVENT, reason=outcome.value)
        raise RefreshRejectedError(outcome)
    logger.info(
        REFRESHED_EVENT,
        result=outcome.decision.value,
        sid=str(session_id),
        user_id=str(outcome.user_id),
    )
    return outcome


def _refresh_locked(
    raw_token: str, session_id: UUID, *, now: datetime
) -> RefreshedSession | IdentityErrorCode:
    token = (
        RefreshToken.objects.select_for_update()
        .filter(token_hash=hash_secret(raw_token), session_id=session_id)
        .first()
    )
    if token is None:
        return IdentityErrorCode.TOKEN_INVALID
    session = (
        AuthSession.objects.select_for_update(of=("self",))
        .select_related("user")
        .get(pk=session_id)
    )
    if session.status != SessionStatus.ACTIVE:
        return IdentityErrorCode.SESSION_REVOKED
    if is_expired(
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
        now=now,
    ):
        expire(session.pk, now=now)
        return IdentityErrorCode.SESSION_REVOKED
    if not session.user.is_active:
        return IdentityErrorCode.SESSION_REVOKED
    decision = decide_refresh(
        used_at=token.used_at, successor_is_live=_successor_is_live(token), now=now
    )
    if decision is RefreshDecision.ROTATE:
        return _rotate(session, token, now=now)
    if decision is RefreshDecision.GRACE:
        return _refreshed(session, None, decision, now=now)
    _revoke_for_reuse(session, now=now)
    return IdentityErrorCode.SESSION_REVOKED


def _successor_is_live(token: RefreshToken) -> bool:
    """Whether the token that replaced ``token`` is still unused, i.e. the session's live one."""
    if token.used_at is None or token.replaced_by_id is None:
        return False
    return RefreshToken.objects.filter(pk=token.replaced_by_id, used_at__isnull=True).exists()


def _rotate(session: AuthSession, token: RefreshToken, *, now: datetime) -> RefreshedSession:
    # Used first: the database allows one unused token per session.
    token.used_at = now
    token.save(update_fields=["used_at"])
    raw_successor = issue_refresh_token(session, now=now)
    successor = RefreshToken.objects.filter(token_hash=hash_secret(raw_successor)).values("pk")
    RefreshToken.objects.filter(pk=token.pk).update(replaced_by=Subquery(successor))
    session.last_used_at = now
    session.idle_expires_at = idle_expiry(now, session.absolute_expires_at)
    session.save(update_fields=["last_used_at", "idle_expires_at"])
    return _refreshed(session, raw_successor, RefreshDecision.ROTATE, now=now)


def _refreshed(
    session: AuthSession, refresh_token: str | None, decision: RefreshDecision, *, now: datetime
) -> RefreshedSession:
    access_token = issue_access_token(user_id=session.user_id, session_id=session.pk, now=now)
    return RefreshedSession(
        access_token=access_token,
        refresh_token=refresh_token,
        session_expires_in=int((session.idle_expires_at - now).total_seconds()),
        decision=decision,
        user_id=session.user_id,
    )


def _revoke_for_reuse(session: AuthSession, *, now: datetime) -> None:
    """A used token out of the grace window: possible theft, so the whole session ends."""
    revoke(session.pk, reason=RevokeReason.REFRESH_REUSE, now=now)
    # ``sid`` as in the JWT: any key holding "session" is redacted from the logs (C-06).
    ids = {"sid": str(session.pk), "user_id": str(session.user_id)}
    audit = get_audit_port()
    audit.record(
        AuditEvent(
            action=IdentityAuditAction.REFRESH_REUSE_DETECTED,
            result=AuditResult.FAILURE,
            actor_type=AuditActorType.SYSTEM,
            occurred_at=now,
            metadata=dict(ids),
        )
    )
    audit.record(
        AuditEvent(
            action=IdentityAuditAction.SESSION_REVOKED,
            result=AuditResult.SUCCESS,
            reason=SessionRevocationReason.REFRESH_REUSE.value,
            actor_type=AuditActorType.SYSTEM,
            occurred_at=now,
            metadata=dict(ids),
        )
    )
    logger.warning(REUSE_EVENT, alert=True, **ids)
