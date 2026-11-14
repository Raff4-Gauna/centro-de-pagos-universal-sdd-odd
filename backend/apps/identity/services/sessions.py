"""A person ends their own sessions from "Seguridad" (RF-IDA-07, RN-IDA-24, design.md §6.2, §7.4).

``revoke_own_session`` ends one session of the user, the current one included; ``revoke_other_
sessions`` ends every ``active`` one but the current, so only the device in hand stays logged in
(AC-IDA-33). Both go through ``session_lifecycle.revoke`` (``UPDATE … WHERE status='active'``), so
the next request with that session's JWT answers ``401 session_revoked`` (AC-IDA-26).

**Isolation** (AC-IDA-25): the session is looked up by the user *and* its id; one of somebody else,
already ended or that never existed is ``SessionNotFoundError``, the same ``404`` for all.

**Locks.** A refresh locks the token and then its session (``refresh.py``), a logout only the
session. Revoking here locks only sessions, never a token: each ``UPDATE`` takes the row lock of one
session until the transaction ends, so it waits behind a refresh of that session or makes it wait,
and neither can hold what the other waits for. ``revoke_other_sessions`` takes them in ascending id,
one at a time, so two "cerrar las demás" of one person (two devices) cannot deadlock either; a
command that ends several sessions (``deactivate_user``) should take them in the same order.

**Two "cerrar las demás" at once** from two devices of the same person (accepted behaviour): each
one keeps its own session and revokes the other's, so both can end and leave the person with no
session at all; the next request of each device answers ``401 session_revoked`` and it logs in
again. Nothing is lost but the sessions, which is what both asked for.

**Audit** (design.md §7.4): one ``identity.session_revoked`` per session that moved, actor the user,
inside the caller's transaction. A session that another request ended first is not audited twice.
**Logs**: ids and the reason only, never a token (RN-IDA-16); ``sid``, as any key holding
"session" is redacted (C-06).
"""

from __future__ import annotations

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
from apps.identity.models import RevokeReason
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.selectors.auth_sessions import get_own_session, list_other_active_session_ids
from apps.identity.services.session_lifecycle import revoke

REVOKED_EVENT = "auth.session_revoked"
REVOKED_OTHERS_EVENT = "auth.other_sessions_revoked"

logger = get_logger(__name__)


class SessionNotFoundError(Exception):
    """Not an ``active`` session of this user: foreign, ended or unknown alike (AC-IDA-25)."""


def revoke_own_session(*, user_id: UUID, session_id: UUID, now: datetime) -> None:
    with transaction.atomic():
        if get_own_session(user_id=user_id, session_id=session_id) is None:
            raise SessionNotFoundError
        # False only if a concurrent request ended it first: the person's intent holds all the same.
        moved = _revoke(user_id, session_id, SessionRevocationReason.USER_REVOKED, now=now)
    if moved:
        logger.info(
            REVOKED_EVENT,
            reason=SessionRevocationReason.USER_REVOKED.value,
            sid=str(session_id),
            user_id=str(user_id),
        )


def revoke_other_sessions(*, user_id: UUID, current_session_id: UUID, now: datetime) -> int:
    """End every ``active`` session of the user but ``current_session_id``; how many moved."""
    with transaction.atomic():
        revoked = sum(
            _revoke(user_id, session_id, SessionRevocationReason.REVOKED_OTHERS, now=now)
            for session_id in list_other_active_session_ids(
                user_id=user_id, keep=current_session_id
            )
        )
    logger.info(
        REVOKED_OTHERS_EVENT,
        reason=SessionRevocationReason.REVOKED_OTHERS.value,
        revoked=revoked,
        sid=str(current_session_id),
        user_id=str(user_id),
    )
    return revoked


def _revoke(
    user_id: UUID, session_id: UUID, reason: SessionRevocationReason, *, now: datetime
) -> bool:
    if not revoke(session_id, reason=RevokeReason(reason.value), now=now):
        return False
    get_audit_port().record(
        AuditEvent(
            action=IdentityAuditAction.SESSION_REVOKED,
            result=AuditResult.SUCCESS,
            reason=reason.value,
            actor_type=AuditActorType.USER,
            actor_id=user_id,
            occurred_at=now,
            metadata={"sid": str(session_id)},
        )
    )
    return True
