"""The lock of the membership changes of an organization (RN-TEN-14/18, design.md §4.2, §4.3).

Changing a role, revoking, leaving and inviting decide on the owners, the actor and the target as
they are **now**, not as the request resolved them: two owners who demote each other must not both
succeed (AC-TEN-14). ``lock_membership_mutex(ctx, kind)`` locks the organization row
``FOR NO KEY UPDATE``. Every membership change of the organization takes the same lock, so they run
one after the other; a business write (``FOR KEY SHARE``, ``common/tenancy/locks.py``) does not wait
for it, and the operator's suspension (``FOR UPDATE``) waits for both. The lock order is fixed:
organization first, then the membership or invitation row, never the other way (no deadlocks).

Under the lock, the status is the real one: ``suspended`` rejects a ``WRITE`` of a user or an API
key with ``organization_suspended``; ``READ``/``REDUCE_ACCESS`` and a ``SystemActor`` go on
(``SUSPENDED_ALLOWED_KINDS``, Q-221). The reads the decision needs take the ``MembershipMutex``:

- ``active_owner_count(mutex)``: the owners who count for "last owner" (RN-TEN-14);
- ``actor_membership(mutex)``: the actor's membership re-read (a role changed since the request
  resolved it is the one that rules; ``None`` if it was revoked, or for a system actor);
- ``lock_membership(mutex, membership_id)``: the target, locked; ``None`` if it is of another
  organization or does not exist (the service answers ``404``), any status otherwise (``revoked``
  is the service's ``409 invalid_transition``).

Each of them fails with ``TransactionManagementError`` outside the transaction that took the lock,
where it would decide on rows another transaction may be changing. Known limits: a mutex taken in a
savepoint that was rolled back lost its lock and still passes this check, and so does one kept
from an earlier call of the same ``@transaction.atomic`` function (Django reuses that block).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from django.db import connection
from django.db.transaction import TransactionManagementError

from apps.common.authz.actions import SUSPENDED_ALLOWED_KINDS, ActionKind
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, SystemActor, TenantContext, UserActor
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.common.tenancy.locks import bounded_lock_wait, require_transaction
from apps.tenancy.models import Membership, Organization
from apps.tenancy.models.membership import MembershipStatus

_FIELDS = ("id", "user_id", "role", "status")


@dataclass(frozen=True, slots=True)
class LockedMembership:
    membership_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    status: MembershipStatus


@dataclass(frozen=True, slots=True)
class MembershipMutex:
    """Proof that this transaction holds the lock; built only by ``lock_membership_mutex``."""

    ctx: TenantContext
    organization_status: OrgStatus
    _transaction: Any = field(repr=False, compare=False)


def lock_membership_mutex(ctx: TenantContext, kind: ActionKind) -> MembershipMutex:
    if not isinstance(kind, ActionKind):
        raise TypeError("kind must be an ActionKind")
    require_transaction("lock_membership_mutex")
    with bounded_lock_wait():
        status = (
            Organization.objects.for_tenant(ctx)
            .select_for_update(no_key=True)
            .values_list("status", flat=True)
            .first()
        )
    if status is None:
        raise OrganizationNotFound
    organization_status = OrgStatus(status)
    if (
        organization_status is OrgStatus.SUSPENDED
        and kind not in SUSPENDED_ALLOWED_KINDS
        and not isinstance(ctx.actor, SystemActor)
    ):
        raise OrganizationSuspended
    return MembershipMutex(ctx, organization_status, _outermost_transaction())


def active_owner_count(mutex: MembershipMutex) -> int:
    _require_held(mutex)
    return (
        Membership.objects.for_tenant(mutex.ctx)
        .filter(role=Role.OWNER.value, status=MembershipStatus.ACTIVE.value)
        .count()
    )


def actor_membership(mutex: MembershipMutex) -> LockedMembership | None:
    _require_held(mutex)
    actor = mutex.ctx.actor
    if not isinstance(actor, UserActor):
        return None
    row = (
        Membership.objects.for_tenant(mutex.ctx)
        .filter(pk=actor.membership_id, user_id=actor.user_id, status=MembershipStatus.ACTIVE.value)
        .values_list(*_FIELDS)
        .first()
    )
    return None if row is None else _locked(row)


def lock_membership(mutex: MembershipMutex, membership_id: uuid.UUID) -> LockedMembership | None:
    """The target row, ``FOR NO KEY UPDATE`` (its key never changes) after the organization."""
    _require_held(mutex)
    with bounded_lock_wait():
        row = (
            Membership.objects.for_tenant(mutex.ctx)
            .select_for_update(no_key=True)
            .filter(pk=membership_id)
            .values_list(*_FIELDS)
            .first()
        )
    return None if row is None else _locked(row)


def _locked(row: tuple[Any, ...]) -> LockedMembership:
    membership_id, user_id, role, status = row
    return LockedMembership(membership_id, user_id, Role(role), MembershipStatus(status))


def _outermost_transaction() -> Any:
    """The ``atomic`` block that opened this transaction: a row lock lasts as long as it does."""
    return connection.atomic_blocks[0]


def _require_held(mutex: MembershipMutex) -> None:
    if not isinstance(mutex, MembershipMutex):
        raise TypeError("a MembershipMutex is required")
    if not connection.in_atomic_block or _outermost_transaction() is not mutex._transaction:
        raise TransactionManagementError("the membership mutex is held only in its transaction")
