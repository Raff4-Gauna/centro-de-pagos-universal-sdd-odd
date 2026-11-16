"""The periodic purge of session data (RF-IDA-10, RN-IDA-25, Q-118, design.md §3.3).

``purge_auth_data(now=...)`` runs four steps, each in batches of ``batch_size`` rows, one
transaction per batch, at most ``MAX_BATCHES`` batches per step and run (a bigger backlog is left
for the next hour: a run is bounded):

1. **Materialize ``expired``.** Active sessions whose idle deadline is ``<= now`` become ``expired``
   with ``ended_at = idle_expires_at``, the rule of ``session_lifecycle.expire`` (the idle deadline
   never passes the absolute one, so it is the earlier of the two).
2. **Login attempts** with ``expires_at < now`` are deleted.
3. **Sessions ended more than 90 days ago** (``ended_at < now - 90 days``, revoked or expired) are
   deleted with all their refresh tokens: the tokens first, then the sessions left without any.
4. **Gauge.** The count of active sessions is logged as ``auth.sessions_active`` (RNF-IDA-04).

Users are never deleted (Q-118): sessions point at them with ``PROTECT`` and nothing here touches
``users``. Sessions, tokens and attempts are global entities, without ``organization_id`` (spec §9).

**Locks.** A refresh locks its token and then its session (``services/refresh.py``); a logout, a
login over a previous session and the revocations lock only sessions. The purge follows that order
and never waits holding a session:

- Steps 1, 2 and the session part of 3 lock with ``SKIP LOCKED``: a row someone holds is skipped,
  and the next run takes it. They never wait, so they cannot be part of a deadlock.
- The token part of 3 locks only tokens (``FOR UPDATE OF`` the token), in ascending id order, and
  does wait: a refresh holding a token of a dead session finishes (``session_revoked``) without
  needing anything the purge holds. Waiting, not skipping, is what keeps the chains whole: a token
  is always issued after the one it replaces, so the lowest ids of a session are its oldest, and a
  batch of the lowest ids never leaves behind a token that points at a deleted one.

Idempotent: a second run at the same ``now`` finds nothing to do. Nothing logged names a token, a
hash or a session: counts only, under keys the log redaction would not blank.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Exists, F, OuterRef

from apps.common.logging import get_logger
from apps.identity.models import AuthSession, LoginAttempt, RefreshToken, SessionStatus

RETENTION = timedelta(days=90)
BATCH_SIZE = 1000
MAX_BATCHES = 100

ACTIVE_GAUGE_EVENT = "auth.sessions_active"
PURGED_EVENT = "auth.purge_completed"

logger = get_logger(__name__)


@dataclass(frozen=True)
class PurgeResult:
    expired_sessions: int
    deleted_login_attempts: int
    deleted_refresh_tokens: int
    deleted_sessions: int
    active_sessions: int


def purge_auth_data(*, now: datetime, batch_size: int = BATCH_SIZE) -> PurgeResult:
    cutoff = now - RETENTION
    result = PurgeResult(
        expired_sessions=_in_batches(lambda: _expire_batch(now, batch_size), batch_size),
        deleted_login_attempts=_in_batches(
            lambda: _delete_login_attempt_batch(now, batch_size), batch_size
        ),
        deleted_refresh_tokens=_in_batches(
            lambda: _delete_token_batch(cutoff, batch_size), batch_size
        ),
        deleted_sessions=_in_batches(lambda: _delete_session_batch(cutoff, batch_size), batch_size),
        active_sessions=AuthSession.objects.filter(
            status=SessionStatus.ACTIVE, idle_expires_at__gt=now
        ).count(),
    )
    # Keys without "session" or "token": the redaction would blank them (C-06).
    logger.info(
        PURGED_EVENT,
        expired=result.expired_sessions,
        login_attempts=result.deleted_login_attempts,
        refresh_rows=result.deleted_refresh_tokens,
        ended=result.deleted_sessions,
    )
    logger.info(ACTIVE_GAUGE_EVENT, value=result.active_sessions)
    return result


def _in_batches(batch: Callable[[], int], batch_size: int) -> int:
    """Run ``batch`` in its own transaction until one handles fewer than ``batch_size`` rows."""
    total = 0
    for _ in range(MAX_BATCHES):
        with transaction.atomic():
            handled = batch()
        total += handled
        if handled < batch_size:
            break
    return total


def _expire_batch(now: datetime, batch_size: int) -> int:
    ids = list(
        AuthSession.objects.select_for_update(skip_locked=True)
        .filter(status=SessionStatus.ACTIVE, idle_expires_at__lte=now)
        .order_by("idle_expires_at")
        .values_list("pk", flat=True)[:batch_size]
    )
    if ids:
        AuthSession.objects.filter(pk__in=ids, status=SessionStatus.ACTIVE).update(
            status=SessionStatus.EXPIRED, ended_at=F("idle_expires_at")
        )
    return len(ids)


def _delete_login_attempt_batch(now: datetime, batch_size: int) -> int:
    ids = list(
        LoginAttempt.objects.select_for_update(skip_locked=True)
        .filter(expires_at__lt=now)
        .order_by("expires_at")
        .values_list("pk", flat=True)[:batch_size]
    )
    if ids:
        LoginAttempt.objects.filter(pk__in=ids).delete()
    return len(ids)


def _lock_token_batch(cutoff: datetime, batch_size: int) -> list[int]:
    """The lowest ids among the tokens of sessions ended before ``cutoff``, locked (only them)."""
    return list(
        RefreshToken.objects.select_for_update(of=("self",))
        .filter(session__ended_at__lt=cutoff)
        .order_by("pk")
        .values_list("pk", flat=True)[:batch_size]
    )


def _delete_token_batch(cutoff: datetime, batch_size: int) -> int:
    ids = _lock_token_batch(cutoff, batch_size)
    if ids:
        # ``replaced_by`` is ``SET_NULL``: the ORM clears it on the tokens that point at these,
        # which are in this same batch (older ids), before deleting them.
        RefreshToken.objects.filter(pk__in=ids).delete()
    return len(ids)


def _delete_session_batch(cutoff: datetime, batch_size: int) -> int:
    has_tokens = Exists(RefreshToken.objects.filter(session_id=OuterRef("pk")))
    ids: list[UUID] = list(
        AuthSession.objects.select_for_update(skip_locked=True)
        .filter(ended_at__lt=cutoff)
        .filter(~has_tokens)
        .order_by("ended_at")
        .values_list("pk", flat=True)[:batch_size]
    )
    if ids:
        AuthSession.objects.filter(pk__in=ids).delete()
    return len(ids)
