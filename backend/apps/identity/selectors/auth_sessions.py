"""Reads of ``auth_sessions`` (design.md §4.4, RN-IDA-07, RN-IDA-20).

Sessions are global entities (spec §9): no ``organization_id`` to filter by, so every read here goes
by primary key, and by the user the token names as well. ``get_request_auth_context`` is what
``HubJWTAuthentication`` asks on every request: one ``SELECT`` by PK joined to ``users``, no cache
and no write, so a revocation or a deactivation committed in the database rejects the very next
request. Whether a deadline has passed is the domain's rule (``session_policy.is_expired``).

The reads of "Seguridad" (RN-IDA-24, design.md §7.2) take the user as a required argument and never
answer about anybody else's session: one that is not the user's is the same as one that does not
exist (AC-IDA-25).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import QuerySet

from apps.identity.domain.session_policy import is_expired
from apps.identity.models import AuthSession, SessionStatus, User


@dataclass(frozen=True, slots=True)
class RequestAuthContext:
    """``request.auth`` of an authenticated request: the person and the session it rides on."""

    user: User
    sid: UUID


def get_request_auth_context(
    *, session_id: UUID, user_id: UUID, now: datetime
) -> RequestAuthContext | None:
    """The context of a live session of an active user, or ``None`` (``401 session_revoked``).

    ``None`` covers a session that is not ``active``, past either deadline, of a deactivated user,
    of another user than ``user_id`` or no longer in the table: the caller learns nothing else.
    """
    session = (
        AuthSession.objects.select_related("user").filter(pk=session_id, user_id=user_id).first()
    )
    if session is None or session.status != SessionStatus.ACTIVE or not session.user.is_active:
        return None
    if is_expired(
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
        now=now,
    ):
        return None
    return RequestAuthContext(user=session.user, sid=session.pk)


def _active_of(user_id: UUID) -> QuerySet[AuthSession]:
    return AuthSession.objects.filter(user_id=user_id, status=SessionStatus.ACTIVE)


def list_active_sessions(*, user_id: UUID, now: datetime) -> QuerySet[AuthSession]:
    """The user's live sessions, last used first: ``active`` and within both deadlines.

    One past a deadline is still ``active`` until a refresh or the purge marks it ``expired``,
    but it can no longer be used, so it is not shown. Lazy: the caller paginates it in the query.
    """
    return (
        _active_of(user_id)
        .filter(idle_expires_at__gt=now, absolute_expires_at__gt=now)
        .order_by("-last_used_at", "-created_at", "pk")
    )


def get_own_session(*, user_id: UUID, session_id: UUID) -> AuthSession | None:
    """The user's ``active`` session ``session_id``; ``None`` if not active, not theirs or gone."""
    return _active_of(user_id).filter(pk=session_id).first()


def list_other_active_session_ids(*, user_id: UUID, keep: UUID) -> list[UUID]:
    """Ids of the user's ``active`` sessions but ``keep``, ascending: the order to lock them in."""
    return list(_active_of(user_id).exclude(pk=keep).order_by("pk").values_list("pk", flat=True))


def list_active_session_ids(*, user_id: UUID) -> list[UUID]:
    """Ids of every ``active`` session of the user, ascending: the order to lock them in."""
    return list(_active_of(user_id).order_by("pk").values_list("pk", flat=True))
