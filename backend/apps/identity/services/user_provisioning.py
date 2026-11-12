"""Who logs in after a valid callback: step 7 of design.md §4.2 (RN-IDA-04, 05, 07, 21, 22).

``provision_user`` gets the ``VerifiedIdentity`` of ``domain/login_rules.py`` and returns the user
to open a session for, or raises ``LoginRejectedError``:

- **Case (a)**, the ``sub`` exists (RN-IDA-04: the ``sub`` is the person). Inactive →
  ``user_inactive``, nothing changes. Active → ``_sync_existing_user`` (RN-IDA-21) and the login
  goes on, with or without memberships (RN-IDA-22). Never asks the invitation port (Q-121): a
  pending invitation is accepted inside the Hub (SPEC-02).
- **New ``sub``** whose email another user holds → ``identity_conflict`` and an operational alert,
  before any invitation is looked at: an invitation does not make a recycled address someone's.
- **Case (b)**, a new ``sub`` with a free email: ``T-IDA-12``.

Everything runs in one ``atomic()`` (a savepoint inside ``login_complete``'s transaction, which also
opens the session): the success events of RN-IDA-21 are recorded inside it and vanish with a
rollback. Rejections are audited by the caller after its rollback (design.md §7.4), with the
``user_id`` the error carries. Nothing here logs the email or the ``sub`` (RNF-IDA-05), and an
``IntegrityError`` is never logged nor turned into text: its message quotes both.
"""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from django.db import IntegrityError, transaction

from apps.common.logging import get_logger
from apps.identity.domain.audit_events import AuditActorType, AuditResult, IdentityAuditAction
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.login_rules import LoginRejectedError, VerifiedIdentity
from apps.identity.models import User
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.selectors.users import get_by_email, get_by_sub

logger = get_logger(__name__)


def provision_user(identity: VerifiedIdentity, *, now: datetime) -> User:
    with transaction.atomic():
        user = get_by_sub(identity.sub, for_update=True)
        if user is not None:
            return _login_existing_user(user, identity, now=now)
        owner = get_by_email(identity.email)
        if owner is not None:
            _reject_identity_conflict(owner)
        return _provision_new_user(identity, now=now)


def _login_existing_user(user: User, identity: VerifiedIdentity, *, now: datetime) -> User:
    if not user.is_active:
        raise LoginRejectedError(IdentityErrorCode.USER_INACTIVE, user_id=user.pk)
    _sync_existing_user(user, identity, now=now)
    return user


def _sync_existing_user(user: User, identity: VerifiedIdentity, *, now: datetime) -> None:
    """Name and avatar follow Google on every login; the email only if no one else has it.

    The new email is checked against the other users first and then written in a savepoint: a user
    who takes it between the check and the ``UPDATE`` makes the unique index refuse it, which is the
    same collision.
    """
    user.display_name = identity.display_name
    user.avatar_url = identity.avatar_url
    user.last_login_at = now
    user.save(update_fields=["display_name", "avatar_url", "last_login_at"])
    if identity.email == user.email:
        return
    if get_by_email(identity.email) is not None or not _try_change_email(user, identity.email):
        _audit(IdentityAuditAction.EMAIL_CHANGE_COLLISION, AuditResult.FAILURE, user, now=now)
        return
    _audit(IdentityAuditAction.EMAIL_CHANGED, AuditResult.SUCCESS, user, now=now)


def _try_change_email(user: User, email: str) -> bool:
    previous = user.email
    try:
        with transaction.atomic():
            user.email = email
            user.save(update_fields=["email"])
    except IntegrityError:
        # Its text quotes the email and the sub: neither logged nor kept.
        user.email = previous
        return False
    return True


def _reject_identity_conflict(owner: User) -> NoReturn:
    """RN-IDA-21, Q-110: a recycled address is not a way into someone else's account.

    The alert names the user whose email was presented (an id, RNF-IDA-05), not the newcomer.
    """
    logger.warning(
        "auth.login_rejected",
        reason=IdentityErrorCode.IDENTITY_CONFLICT.value,
        alert=True,
        existing_user_id=str(owner.pk),
    )
    raise LoginRejectedError(IdentityErrorCode.IDENTITY_CONFLICT)


def _provision_new_user(identity: VerifiedIdentity, *, now: datetime) -> User:
    """Case (b), the first login by invitation, with its race (design.md §4.3): ``T-IDA-12``."""
    raise NotImplementedError("case (b) of RN-IDA-05 arrives with T-IDA-12")


def _audit(action: IdentityAuditAction, result: AuditResult, user: User, *, now: datetime) -> None:
    """No metadata: the addresses are personal data and the audit channel is a log (C-16)."""
    get_audit_port().record(
        AuditEvent(
            action=action,
            result=result,
            actor_type=AuditActorType.USER,
            actor_id=user.pk,
            occurred_at=now,
        )
    )
