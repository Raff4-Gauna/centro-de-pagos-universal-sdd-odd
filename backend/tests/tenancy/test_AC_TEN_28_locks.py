"""The write lock of the organization and its system context (AC-TEN-28, RN-TEN-18, design.md §3.7).

``ensure_writable`` re-reads the status inside the transaction of the write (``FOR KEY SHARE``),
so a user whose request resolved the organization ``active`` is stopped if it was suspended since. A
``SystemActor`` is never stopped: the server-to-server events of a ``pending`` charge go on.
The lock races (two connections) are in ``test_AC_TEN_28_lock_races.py``.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.transaction import TransactionManagementError

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.common.tenancy.locks import (
    LOCK_TIMEOUT,
    bounded_lock_wait,
    ensure_writable,
    lock_org_for_write,
    system_context,
)
from apps.common.tenancy.querysets import TenantScopeError
from tests.tenancy.locking import add_member, new_org, set_status, system_ctx, user_ctx

pytestmark = pytest.mark.django_db


def lock_timeout() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        return str(cursor.fetchone()[0])


def test_AC_TEN_28_ensure_writable_blocks_user_actor() -> None:
    org = new_org("A")
    ctx = user_ctx(add_member(org, "ana", Role.OWNER))  # resolved while still active
    set_status(org, OrgStatus.SUSPENDED)

    with pytest.raises(OrganizationSuspended), transaction.atomic():
        ensure_writable(ctx)


def test_AC_TEN_28_ensure_writable_lets_a_system_actor_write() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)

    with transaction.atomic():
        assert ensure_writable(system_ctx(org.id)) is OrgStatus.SUSPENDED


def test_AC_TEN_28_ensure_writable_passes_an_active_organization() -> None:
    org = new_org("A")
    ctx = user_ctx(add_member(org, "ana", Role.OPERATOR))

    with transaction.atomic():
        assert ensure_writable(ctx) is OrgStatus.ACTIVE


def test_AC_TEN_28_a_reactivated_organization_is_writable_again() -> None:
    org = new_org("A")
    ctx = user_ctx(add_member(org, "ana", Role.OWNER), OrgStatus.SUSPENDED)  # stale: suspended

    with transaction.atomic():
        assert ensure_writable(ctx) is OrgStatus.ACTIVE


# The test's own transaction would hide a missing one: run outside it.
@pytest.mark.django_db(transaction=True)
def test_lock_org_for_write_needs_a_transaction() -> None:
    org = new_org("A")

    with pytest.raises(TransactionManagementError):
        lock_org_for_write(system_ctx(org.id))


def test_lock_org_for_write_rejects_another_active_tenant() -> None:
    a, b = new_org("A"), new_org("B")

    with tenant_scope(system_ctx(a.id)), transaction.atomic(), pytest.raises(TenantScopeError):
        lock_org_for_write(system_ctx(b.id))


def test_lock_org_for_write_of_an_unknown_organization_fails_closed() -> None:
    with transaction.atomic(), pytest.raises(OrganizationNotFound):
        lock_org_for_write(system_ctx(uuid.uuid4()))


def test_the_lock_wait_is_bounded_and_then_restored() -> None:
    before = lock_timeout()

    with transaction.atomic():
        with bounded_lock_wait():
            assert lock_timeout() == LOCK_TIMEOUT == "5s"
        assert lock_timeout() == before


# The test's own transaction would hide a missing one: run outside it.
@pytest.mark.django_db(transaction=True)
def test_bounded_lock_wait_needs_a_transaction() -> None:
    with pytest.raises(TransactionManagementError), bounded_lock_wait():
        pass


def test_AC_TEN_28_system_context_reads_the_real_status() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)

    ctx = system_context(org.id, SystemReason.WEBHOOK)

    assert ctx.organization_id == org.id
    assert ctx.organization_status is OrgStatus.SUSPENDED
    assert ctx.actor == SystemActor(SystemReason.WEBHOOK)


def test_system_context_of_an_unknown_organization_fails_closed() -> None:
    with pytest.raises(OrganizationNotFound):
        system_context(uuid.uuid4(), SystemReason.CELERY)


def test_system_context_checks_its_arguments() -> None:
    org = new_org("A")

    with pytest.raises(TypeError):
        system_context(str(org.id), SystemReason.CELERY)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        system_context(org.id, "celery")  # type: ignore[arg-type]


def test_the_lock_wait_is_restored_after_an_error_that_keeps_the_transaction() -> None:
    before = lock_timeout()

    with transaction.atomic():
        with pytest.raises(OrganizationNotFound), bounded_lock_wait():
            raise OrganizationNotFound
        assert lock_timeout() == before


def test_the_lock_wait_is_restored_after_a_database_error_of_an_inner_savepoint() -> None:
    """Review of PR #117: the savepoint rolls back after ``set_config``, so it restores nothing."""
    assert lock_timeout() == "0"

    with transaction.atomic():
        with (
            pytest.raises(DatabaseError),
            bounded_lock_wait(),
            transaction.atomic(),  # the savepoint, inside the block
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1 / 0")
        assert lock_timeout() == "0"  # it was left at 5s


def test_the_lock_wait_leaves_an_aborted_transaction_alone() -> None:
    """No savepoint: the error aborted the transaction, and restoring would hide it."""
    with (
        pytest.raises(DatabaseError, match="division by zero"),
        transaction.atomic(),
        bounded_lock_wait(),
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1 / 0")
