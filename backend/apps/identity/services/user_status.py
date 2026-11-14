"""The platform operator deactivates or reactivates a person (RF-IDA-08, RN-IDA-07, RN-IDA-23).

Only the management commands ``deactivate_user`` and ``reactivate_user`` call this: there is no
HTTP endpoint for it (AC-IDA-32, Q-116). The operator is whoever has a shell on the server, not a
user of the API; ``PlatformOperator`` carries the name given with ``--operator`` and the user of the
operating system, and every audit event names them as the actor (design.md §6.5, §7.4).

``deactivate_user``, in one transaction: the user row ``FOR UPDATE``, ``is_active=false`` and
``deactivated_at=now``, then every ``active`` session revoked (``user_deactivated``), so the next
request with any JWT of that person answers ``401 session_revoked`` (AC-IDA-27). ``reactivate_user``
clears both fields and leaves the sessions as they are: a revoked one never comes back, the person
logs in again. Repeating either on a user already in that state changes nothing and audits nothing,
as the bootstrap command does on a repetition (SPEC-02 design.md §4.5); the caller reports it.

**Locks.** The user row first, then the sessions one at a time in ascending id, as "cerrar las
demás" does (``sessions.py``). A login locks the same user row before it opens a session
(``user_provisioning``), so it either sees the user inactive or commits its session before the list
of sessions to revoke is read: none is left ``active`` to come back with a reactivation. A refresh
locks a token and then its session and only reads the user, so it waits behind a revocation or
makes it wait, never both (``tests/identity/test_revocation_concurrency.py``).

**Logs**: ids, the outcome and the count; never the email (RNF-IDA-05) nor the operator's note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.common.logging import get_logger
from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
    SessionRevocationReason,
)
from apps.identity.domain.emails import normalize_email
from apps.identity.models import RevokeReason, User
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.selectors.auth_sessions import list_active_session_ids
from apps.identity.selectors.users import get_by_email, get_by_id
from apps.identity.services.session_lifecycle import revoke

DEACTIVATED_EVENT = "identity.user_deactivated"
REACTIVATED_EVENT = "identity.user_reactivated"
MAX_OPERATOR = 150
MAX_NOTE = 200

logger = get_logger(__name__)


class UserNotFoundError(Exception):
    """No user has that id or email; it carries neither."""


@dataclass(frozen=True)
class PlatformOperator:
    """Who runs the command: the declared ``--operator`` and the user of the operating system."""

    name: str
    os_user: str

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > MAX_OPERATOR:
            raise ValueError(f"the operator must have between 1 and {MAX_OPERATOR} characters")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True)
class UserTarget:
    """The user to act on, by exactly one of its id or its email (normalized here, Q-107)."""

    user_id: UUID | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("give exactly one of user_id and email")
        if self.email is not None:
            object.__setattr__(self, "email", normalize_email(self.email))


@dataclass(frozen=True)
class StatusChange:
    user_id: UUID
    changed: bool
    revoked_sessions: int = 0


def clean_note(note: str | None) -> str | None:
    """The operator's ``--reason``: stripped, ``None`` if blank, at most ``MAX_NOTE`` characters."""
    if note is None or not note.strip():
        return None
    if len(note.strip()) > MAX_NOTE:
        raise ValueError(f"the reason must have at most {MAX_NOTE} characters")
    return note.strip()


def deactivate_user(
    *, target: UserTarget, operator: PlatformOperator, note: str | None, now: datetime
) -> StatusChange:
    note = clean_note(note)
    with transaction.atomic():
        user = _locked(target)
        if not user.is_active:
            outcome = StatusChange(user_id=user.pk, changed=False)
        else:
            user.is_active = False
            user.deactivated_at = now
            user.save(update_fields=["is_active", "deactivated_at"])
            revoked = sum(
                _revoke(user.pk, session_id, operator, now=now)
                for session_id in list_active_session_ids(user_id=user.pk)
            )
            _audit(
                IdentityAuditAction.USER_DEACTIVATED,
                user,
                operator,
                note,
                now=now,
                revoked_sessions=revoked,
            )
            outcome = StatusChange(user_id=user.pk, changed=True, revoked_sessions=revoked)
    logger.info(
        DEACTIVATED_EVENT,
        result="deactivated" if outcome.changed else "already_inactive",
        revoked=outcome.revoked_sessions,
        user_id=str(outcome.user_id),
    )
    return outcome


def reactivate_user(
    *, target: UserTarget, operator: PlatformOperator, note: str | None, now: datetime
) -> StatusChange:
    """Back to active; its sessions stay ended (RN-IDA-07)."""
    note = clean_note(note)
    with transaction.atomic():
        user = _locked(target)
        if user.is_active:
            outcome = StatusChange(user_id=user.pk, changed=False)
        else:
            user.is_active = True
            user.deactivated_at = None
            user.save(update_fields=["is_active", "deactivated_at"])
            _audit(IdentityAuditAction.USER_REACTIVATED, user, operator, note, now=now)
            outcome = StatusChange(user_id=user.pk, changed=True)
    logger.info(
        REACTIVATED_EVENT,
        result="reactivated" if outcome.changed else "already_active",
        user_id=str(outcome.user_id),
    )
    return outcome


def _locked(target: UserTarget) -> User:
    user = None
    if target.user_id is not None:
        user = get_by_id(target.user_id, for_update=True)
    elif target.email is not None:
        user = get_by_email(target.email, for_update=True)
    if user is None:
        raise UserNotFoundError
    return user


def _actor(operator: PlatformOperator) -> dict[str, object]:
    return {"operator": operator.name, "os_user": operator.os_user}


def _audit(
    action: IdentityAuditAction,
    user: User,
    operator: PlatformOperator,
    note: str | None,
    *,
    now: datetime,
    **extra: object,
) -> None:
    get_audit_port().record(
        AuditEvent(
            action=action,
            result=AuditResult.SUCCESS,
            reason=note,
            actor_type=AuditActorType.PLATFORM_OPERATOR,
            occurred_at=now,
            metadata={"user_id": str(user.pk), **_actor(operator), **extra},
        )
    )


def _revoke(user_id: UUID, session_id: UUID, operator: PlatformOperator, *, now: datetime) -> bool:
    if not revoke(session_id, reason=RevokeReason.USER_DEACTIVATED, now=now):
        return False  # another request ended it between the list and this UPDATE
    get_audit_port().record(
        AuditEvent(
            action=IdentityAuditAction.SESSION_REVOKED,
            result=AuditResult.SUCCESS,
            reason=SessionRevocationReason.USER_DEACTIVATED.value,
            actor_type=AuditActorType.PLATFORM_OPERATOR,
            occurred_at=now,
            metadata={"sid": str(session_id), "user_id": str(user_id), **_actor(operator)},
        )
    )
    return True
