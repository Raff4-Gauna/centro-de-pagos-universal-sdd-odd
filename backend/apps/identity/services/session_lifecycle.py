"""Opening a session and moving it out of ``active`` (design.md §5, RN-IDA-10, RN-IDA-11).

Every transition is one ``UPDATE … WHERE status='active'`` and returns whether it moved the row:
two callers racing (a logout and a reuse, a purge and a refresh) cannot both end the session, and a
terminal one never returns. Auditing is the caller's job, which knows why it ends the session.
Sessions and tokens are global entities (spec §9): the raw managers here filter by primary key.

The refresh token in clear exists only in what ``open_session`` and ``issue_refresh_token`` return;
the table keeps its SHA-256 (AC-IDA-14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import F

from apps.identity.domain.secrets_format import generate_refresh_token, hash_secret
from apps.identity.domain.session_policy import absolute_expiry, idle_expiry
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User
from apps.identity.models.auth_session import CLIENT_HINT_LENGTH


@dataclass(frozen=True)
class OpenedSession:
    session: AuthSession
    refresh_token: str = field(repr=False)


def open_session(
    user: User, *, now: datetime, client_browser: str = "", client_os: str = ""
) -> OpenedSession:
    """A new ``active`` session of ``user`` from ``now`` with its first refresh token."""
    absolute = absolute_expiry(now)
    with transaction.atomic():
        session = AuthSession.objects.create(
            user=user,
            created_at=now,
            last_used_at=now,
            idle_expires_at=idle_expiry(now, absolute),
            absolute_expires_at=absolute,
            client_browser=client_browser[:CLIENT_HINT_LENGTH],
            client_os=client_os[:CLIENT_HINT_LENGTH],
        )
        refresh_token = issue_refresh_token(session, now=now)
    return OpenedSession(session=session, refresh_token=refresh_token)


def issue_refresh_token(session: AuthSession, *, now: datetime) -> str:
    """A new live token of ``session``; the database refuses it while another one is unused.

    Precondition: ``session`` is ``active`` and within its deadlines. This does not look; its caller
    has just created the session (``open_session``) or checked it under its lock (``refresh``).
    """
    raw = generate_refresh_token(session.pk)
    RefreshToken.objects.create(session=session, token_hash=hash_secret(raw), issued_at=now)
    return raw


def revoke(session_id: UUID, *, reason: RevokeReason, now: datetime) -> bool:
    """End an active session for ``reason``; ``False`` if it was not active (or does not exist)."""
    moved = AuthSession.objects.filter(pk=session_id, status=SessionStatus.ACTIVE).update(
        status=SessionStatus.REVOKED, ended_at=now, revoke_reason=reason
    )
    return moved == 1


def expire(session_id: UUID, *, now: datetime) -> bool:
    """Mark ``expired`` an active session already past its deadline, ended at that deadline.

    The idle deadline never passes the absolute one (a constraint), so it is the earlier of the two.
    A session still alive at ``now`` is left as it is.
    """
    moved = AuthSession.objects.filter(
        pk=session_id, status=SessionStatus.ACTIVE, idle_expires_at__lte=now
    ).update(status=SessionStatus.EXPIRED, ended_at=F("idle_expires_at"))
    return moved == 1
