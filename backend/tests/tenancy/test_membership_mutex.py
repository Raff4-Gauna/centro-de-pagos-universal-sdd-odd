"""``lock_membership_mutex``: what a membership change reads under the lock (design.md §4.2, §4.3).

The services of T-TEN-20..23 decide on the owners, the actor and the target as they are **under the
lock**, not as the request resolved them (RN-TEN-14, AC-TEN-13/14/27): so every read of this module
takes the mutex and fails outside the transaction that holds it. The suspension check is the one of
``SUSPENDED_ALLOWED_KINDS`` (AC-TEN-28, Q-221). The races are in ``test_AC_TEN_28_lock_races.py``.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import transaction
from django.db.transaction import TransactionManagementError
from django.utils import timezone

from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import EndedReason, MembershipStatus
from apps.tenancy.selectors.locks import (
    LockedMembership,
    active_owner_count,
    actor_membership,
    lock_membership,
    lock_membership_mutex,
)
from tests.tenancy.locking import PLATFORM, add_member, new_org, set_status, system_ctx, user_ctx

pytestmark = pytest.mark.django_db


def change(membership: Membership, **values: object) -> None:
    Membership.objects.unscoped(PLATFORM).filter(pk=membership.pk).update(**values)


def revoke(membership: Membership) -> None:
    change(
        membership,
        status=MembershipStatus.REVOKED.value,
        ended_reason=EndedReason.REVOKED.value,
        ended_at=timezone.now(),
    )


def test_AC_TEN_28_mutex_rejects_a_write_on_a_suspended_org() -> None:
    org = new_org("A")
    ctx = user_ctx(add_member(org, "ana", Role.OWNER))
    set_status(org, OrgStatus.SUSPENDED)

    with pytest.raises(OrganizationSuspended), transaction.atomic():
        lock_membership_mutex(ctx, ActionKind.WRITE)


def test_AC_TEN_28_mutex_lets_reduce_access_through_a_suspended_org() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)
    ctx = user_ctx(add_member(org, "ana", Role.OWNER), OrgStatus.SUSPENDED)

    with transaction.atomic():
        mutex = lock_membership_mutex(ctx, ActionKind.REDUCE_ACCESS)
        assert mutex.organization_status is OrgStatus.SUSPENDED


def test_AC_TEN_28_mutex_lets_a_system_actor_write_on_a_suspended_org() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)

    with transaction.atomic():
        mutex = lock_membership_mutex(system_ctx(org.id), ActionKind.WRITE)
        assert mutex.organization_status is OrgStatus.SUSPENDED


# The test's own transaction would hide a missing one: run outside it.
@pytest.mark.django_db(transaction=True)
def test_mutex_needs_a_transaction() -> None:
    org = new_org("A")

    with pytest.raises(TransactionManagementError):
        lock_membership_mutex(system_ctx(org.id), ActionKind.WRITE)


def test_mutex_of_an_unknown_organization_fails_closed() -> None:
    with transaction.atomic(), pytest.raises(OrganizationNotFound):
        lock_membership_mutex(system_ctx(uuid.uuid4()), ActionKind.WRITE)


def test_RN_TEN_14_counts_the_active_owners_under_the_mutex() -> None:
    org, other = new_org("A"), new_org("B")
    ana = add_member(org, "ana", Role.OWNER)
    revoke(add_member(org, "bea", Role.OWNER))
    add_member(org, "carla", Role.ADMIN)
    add_member(other, "dora", Role.OWNER)

    with transaction.atomic():
        mutex = lock_membership_mutex(user_ctx(ana), ActionKind.WRITE)
        assert active_owner_count(mutex) == 1


def test_RN_TEN_14_rereads_the_actor_role_under_the_mutex() -> None:
    org = new_org("A")
    ana = add_member(org, "ana", Role.OWNER)
    ctx = user_ctx(ana)  # resolved as owner
    change(ana, role=Role.VIEWER.value)  # demoted by someone else since

    with transaction.atomic():
        actor = actor_membership(lock_membership_mutex(ctx, ActionKind.WRITE))

    assert actor == LockedMembership(ana.id, ana.user_id, Role.VIEWER, MembershipStatus.ACTIVE)


def test_RN_TEN_14_a_revoked_actor_is_no_actor() -> None:
    org = new_org("A")
    ana = add_member(org, "ana", Role.OWNER)
    ctx = user_ctx(ana)
    revoke(ana)

    with transaction.atomic():
        assert actor_membership(lock_membership_mutex(ctx, ActionKind.REDUCE_ACCESS)) is None


def test_a_system_actor_has_no_membership() -> None:
    org = new_org("A")

    with transaction.atomic():
        assert actor_membership(lock_membership_mutex(system_ctx(org.id), ActionKind.WRITE)) is None


def test_RN_TEN_14_locks_the_target_as_it_is_now() -> None:
    org = new_org("A")
    ana, bea = add_member(org, "ana", Role.OWNER), add_member(org, "bea", Role.ADMIN)
    revoke(bea)

    with transaction.atomic():
        target = lock_membership(lock_membership_mutex(user_ctx(ana), ActionKind.WRITE), bea.id)

    assert target == LockedMembership(bea.id, bea.user_id, Role.ADMIN, MembershipStatus.REVOKED)


def test_a_target_of_another_organization_is_not_found() -> None:
    org, other = new_org("A"), new_org("B")
    ana, dora = add_member(org, "ana", Role.OWNER), add_member(other, "dora", Role.VIEWER)

    with transaction.atomic():
        mutex = lock_membership_mutex(user_ctx(ana), ActionKind.WRITE)
        assert lock_membership(mutex, dora.id) is None
        assert lock_membership(mutex, uuid.uuid4()) is None


# The test's own transaction would hide a missing one: run outside it.
@pytest.mark.django_db(transaction=True)
def test_the_mutex_is_good_only_inside_its_transaction() -> None:
    org = new_org("A")
    ana = add_member(org, "ana", Role.OWNER)
    with transaction.atomic():
        mutex = lock_membership_mutex(user_ctx(ana), ActionKind.WRITE)

    with pytest.raises(TransactionManagementError):
        active_owner_count(mutex)
    with transaction.atomic(), pytest.raises(TransactionManagementError):
        actor_membership(mutex)  # another transaction: the lock is gone
    with transaction.atomic(), pytest.raises(TransactionManagementError):
        lock_membership(mutex, ana.id)
