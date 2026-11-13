"""Who logs in after a valid callback: step 7 of design.md §4.2 (RN-IDA-04, 05, 07, 21, 22).

``provision_user`` gets the ``VerifiedIdentity`` of ``domain/login_rules.py`` and returns the user
to open a session for, or raises ``LoginRejectedError``:

- **Case (a)**, the ``sub`` exists (RN-IDA-04: the ``sub`` is the person). Inactive →
  ``user_inactive``, nothing changes. Active → ``_sync_existing_user`` (RN-IDA-21) and the login
  goes on, with or without memberships (RN-IDA-22). Never asks the invitation port (Q-121): a
  pending invitation is accepted inside the Hub (SPEC-02).
- **New ``sub``** whose email another user holds → ``identity_conflict`` and an operational alert,
  before any invitation is looked at: an invitation does not make a recycled address someone's.
- **Case (b)**, a new ``sub`` with a free email (RN-IDA-06): the user is inserted, then the valid
  invitations of that exact email are asked for (and locked by the port) and all of them accepted.
  None → ``not_invited``; one that can no longer be accepted → ``not_invited`` too. Either way the
  rollback takes the user away.

**The race** (design.md §4.3, AC-IDA-02). The user is inserted *before* the invitations are locked,
so the second callback of the same person waits on the unique index until the first one commits and
then gets a unique violation: its attempt is rolled back and the whole provisioning runs once more,
now finding the user (case (a)) or the owner of the email (``identity_conflict``).

**What a refused write means** (Q-126). Only a unique violation is the race or the collision. The
CHECK ``users_email_normalized`` failing means PostgreSQL does not lowercase the address as Python
did: the Hub cannot store that email, so the login is refused as ``google_auth_failed``, like every
other unusable email (``domain/login_rules.py``), in both cases and without a retry or a collision
event. Anything else is a bug and leaves as ``UserProvisioningError``.

Everything runs in one ``atomic()`` (a savepoint inside ``login_complete``'s transaction, which also
opens the session): the success events are recorded inside it and vanish with a rollback.
Rejections are audited by the caller after its rollback (design.md §7.4), with the ``user_id`` the
error carries. Nothing here logs the email or the ``sub`` (RNF-IDA-05), and an ``IntegrityError`` is
never logged, turned into text nor left as the cause of another error: its message quotes both.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, auto
from typing import NoReturn
from uuid import UUID

from django.db import IntegrityError, transaction
from psycopg import errors as pg_errors

from apps.common.logging import get_logger
from apps.identity.domain.audit_events import AuditActorType, AuditResult, IdentityAuditAction
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.login_rules import LoginRejectedError, VerifiedIdentity
from apps.identity.models import User
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.invitations import InvitationsNoLongerValid
from apps.identity.ports.registry import get_audit_port, get_invitation_port
from apps.identity.selectors.users import get_by_email, get_by_sub

logger = get_logger(__name__)

EMAIL_CHECK = "users_email_normalized"
# Detail of a rejection (RNF-IDA-04); its one ``auth.login_rejected`` is ``login_complete``'s.
IDENTITY_CONFLICT_EVENT = "auth.identity_conflict"
EMAIL_NOT_STORABLE_EVENT = "auth.email_not_storable"
# The first attempt and the one retry of design.md §4.3.
ATTEMPTS = 2


class UserProvisioningError(Exception):
    """Provisioning could not finish and no rule explains it. Its text carries no personal data."""


class _LostRaceError(Exception):
    """Another callback inserted a user with this ``sub`` or email first."""


class _Write(Enum):
    DONE = auto()
    TAKEN = auto()  # a unique index refused it
    UNSTORABLE_EMAIL = auto()  # ``users_email_normalized`` refused it
    FAILED = auto()


def provision_user(identity: VerifiedIdentity, *, now: datetime) -> User:
    for _ in range(ATTEMPTS):
        try:
            with transaction.atomic():
                return _provision_once(identity, now=now)
        except _LostRaceError:
            continue
    # Lost twice and still no user to find: not the race of §4.3. Fails without a second retry.
    raise UserProvisioningError("user provisioning lost the race again after its retry")


def _provision_once(identity: VerifiedIdentity, *, now: datetime) -> User:
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
    same collision. An address PostgreSQL cannot store refuses the login (Q-126) and the rollback
    undoes the name, the avatar and ``last_login_at`` written above.
    """
    user.display_name = identity.display_name
    user.avatar_url = identity.avatar_url
    user.last_login_at = now
    user.save(update_fields=["display_name", "avatar_url", "last_login_at"])
    if identity.email == user.email:
        return
    taken = get_by_email(identity.email) is not None
    outcome = _Write.TAKEN if taken else _change_email(user, identity.email)
    if outcome is _Write.DONE:
        _audit(IdentityAuditAction.EMAIL_CHANGED, AuditResult.SUCCESS, user, now=now)
    elif outcome is _Write.TAKEN:
        _audit(IdentityAuditAction.EMAIL_CHANGE_COLLISION, AuditResult.FAILURE, user, now=now)
    elif outcome is _Write.UNSTORABLE_EMAIL:
        _reject_unstorable_email(user_id=user.pk)
    else:
        raise UserProvisioningError("the email of a user could not be updated")


def _change_email(user: User, email: str) -> _Write:
    previous = user.email
    try:
        with transaction.atomic():
            user.email = email
            user.save(update_fields=["email"])
    except IntegrityError as error:
        user.email = previous
        return _classify(error)
    return _Write.DONE


def _classify(error: IntegrityError) -> _Write:
    """Which constraint refused the write, from the driver's error and never from its text.

    The message quotes the email and the ``sub``. Callers read the outcome and raise outside their
    ``except``, so the ``IntegrityError`` is not chained to what they raise either.
    """
    cause = error.__cause__
    if isinstance(cause, pg_errors.UniqueViolation):
        return _Write.TAKEN
    if isinstance(cause, pg_errors.CheckViolation) and cause.diag.constraint_name == EMAIL_CHECK:
        return _Write.UNSTORABLE_EMAIL
    return _Write.FAILED


def _reject_unstorable_email(*, user_id: UUID | None) -> NoReturn:
    """Q-126: PostgreSQL does not lowercase this address as Python did, so it cannot be kept."""
    logger.warning(
        EMAIL_NOT_STORABLE_EVENT,
        outcome="rejected",
        reason=IdentityErrorCode.GOOGLE_AUTH_FAILED.value,
        detail="email_not_storable",
        user_id=None if user_id is None else str(user_id),
    )
    raise LoginRejectedError(IdentityErrorCode.GOOGLE_AUTH_FAILED, user_id=user_id)


def _reject_identity_conflict(owner: User) -> NoReturn:
    """RN-IDA-21, Q-110: a recycled address is not a way into someone else's account.

    The alert names the user whose email was presented (an id, RNF-IDA-05), not the newcomer.
    """
    logger.warning(
        IDENTITY_CONFLICT_EVENT,
        outcome="rejected",
        reason=IdentityErrorCode.IDENTITY_CONFLICT.value,
        alert=True,
        existing_user_id=str(owner.pk),
    )
    raise LoginRejectedError(IdentityErrorCode.IDENTITY_CONFLICT)


def _provision_new_user(identity: VerifiedIdentity, *, now: datetime) -> User:
    """Case (b): the user and every valid invitation of the email, all or nothing (RN-IDA-06).

    The rejections leave through the ``atomic()`` of ``provision_user``, which takes the user away;
    so does any other error of the port. One event per accepted invitation, with its organization
    (Q-117, Q-120).
    """
    user = _insert_user(identity, now=now)
    port = get_invitation_port()
    invitations = port.find_valid_invitations(identity.email, now=now)
    if not invitations:
        raise LoginRejectedError(IdentityErrorCode.NOT_INVITED)
    try:
        port.accept_invitations(invitations, user.pk, now=now)
    except InvitationsNoLongerValid:
        raise LoginRejectedError(IdentityErrorCode.NOT_INVITED) from None
    for invitation in invitations:
        _audit(
            IdentityAuditAction.USER_CREATED_BY_INVITATION,
            AuditResult.SUCCESS,
            user,
            now=now,
            organization_id=invitation.organization_id,
        )
    return user


def _insert_user(identity: VerifiedIdentity, *, now: datetime) -> User:
    """In a savepoint, so a refused ``INSERT`` does not break the transaction. No manager (C-01) nor
    ``create_user``: the identity is normalized by ``evaluate_identity`` and reaches the CHECK."""
    user = User(
        google_sub=identity.sub,
        email=identity.email,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        last_login_at=now,
    )
    try:
        with transaction.atomic():
            user.save(force_insert=True)
            return user
    except IntegrityError as error:
        outcome = _classify(error)
    if outcome is _Write.TAKEN:
        raise _LostRaceError
    if outcome is _Write.UNSTORABLE_EMAIL:
        _reject_unstorable_email(user_id=None)
    raise UserProvisioningError("a new user could not be inserted")


def _audit(
    action: IdentityAuditAction,
    result: AuditResult,
    user: User,
    *,
    now: datetime,
    organization_id: UUID | None = None,
) -> None:
    """No metadata: the addresses are personal data and the audit channel is a log (C-16)."""
    get_audit_port().record(
        AuditEvent(
            action=action,
            result=result,
            actor_type=AuditActorType.USER,
            actor_id=user.pk,
            organization_id=organization_id,
            occurred_at=now,
        )
    )
