"""Suspending while a write is in flight, and what the locks serialize (design.md §3.7, §4.2, §11).

Two threads, each with its own connection and transaction (``transaction=True``: the other one has
to see committed rows), as in ``tests/identity/test_revocation_concurrency.py``. The first one takes
its lock and stops inside its transaction; the second one starts, and the test waits until
PostgreSQL shows it blocked on a lock (``pg_stat_activity``) before letting the first one go, so
the order is forced, not hoped for. Where the second one must **not** wait, it has to finish while
the first one still holds its lock.

The suspension is the operator's ``SELECT ... FOR UPDATE`` plus ``UPDATE`` (design.md §3.7; its
command is T-TEN-19). A write takes ``FOR KEY SHARE`` (``ensure_writable``) and a membership change
``FOR NO KEY UPDATE`` (``lock_membership_mutex``): both conflict with the suspension, not with each
other, and two membership changes wait for each other (RN-TEN-14).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest
from django.db import OperationalError, connection, transaction

from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.tenancy import locks
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationSuspended
from apps.tenancy.models import Organization
from apps.tenancy.selectors.locks import active_owner_count, lock_membership_mutex
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.locking import PLATFORM, add_member, new_org, new_widget, user_ctx, widget_name
from tests.testapps.tenant_probe.models import Widget

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


class Held(threading.Thread):
    """Runs ``lock`` in a transaction, stops until released, then runs ``then`` and commits."""

    def __init__(self, lock: Callable[[], Any], then: Callable[[], Any] = lambda: None) -> None:
        super().__init__(daemon=True)
        self.lock, self.then = lock, then
        self.reached, self.go_on = threading.Event(), threading.Event()
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            with transaction.atomic():
                self.lock()
                self.reached.set()
                assert self.go_on.wait(PATIENCE)
                self.then()
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            self.reached.set()
            connection.close()


class Second(threading.Thread):
    def __init__(self, action: Callable[[], Any]) -> None:
        super().__init__(daemon=True)
        self.action = action
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            with transaction.atomic():
                self.action()
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            connection.close()


def suspend(organization: Organization) -> Callable[[], None]:
    """The operator's side: lock the row ``FOR UPDATE`` (it waits for every lock of the row)."""

    def lock() -> None:
        row = Organization.objects.unscoped(PLATFORM).select_for_update().get(pk=organization.pk)
        row.status = OrgStatus.SUSPENDED.value
        row.save(update_fields=["status"])

    return lock


def rename(ctx: TenantContext, widget: Widget) -> Callable[[], None]:
    def write() -> None:
        with tenant_scope(ctx):
            locks.ensure_writable(ctx)
            Widget.objects.for_tenant(ctx).filter(pk=widget.pk).update(name="after")

    return write


def mutex(ctx: TenantContext) -> Callable[[], int]:
    return lambda: active_owner_count(lock_membership_mutex(ctx, ActionKind.WRITE))


def status(organization: Organization) -> str:
    return str(
        Organization.objects.unscoped(PLATFORM)
        .values_list("status", flat=True)
        .get(pk=organization.pk)
    )


def blocks_behind(first: Held, second: Second) -> None:
    """``second`` waits on the lock of ``first``; then ``first`` goes on and both finish."""
    first.start()
    try:
        assert first.reached.wait(PATIENCE), "the first one never took its lock"
        second.start()
        assert wait_for_a_blocked_backend(), "the second one did not wait for the first"
    finally:
        first.go_on.set()
        first.join(PATIENCE)
        if second.ident is not None:
            second.join(PATIENCE)
    assert not first.is_alive()
    assert not second.is_alive()
    assert first.error is None


def runs_beside(first: Held, second: Second) -> None:
    """``second`` begins and commits while ``first`` still holds its lock."""
    first.start()
    try:
        assert first.reached.wait(PATIENCE), "the first one never took its lock"
        second.start()
        second.join(PATIENCE)
        assert not second.is_alive(), "the second one waited for the first"
    finally:
        first.go_on.set()
        first.join(PATIENCE)
    assert (first.error, second.error) == (None, None)


@pytest.fixture
def owner_ctx() -> tuple[Organization, TenantContext]:
    org = new_org("A")
    return org, user_ctx(add_member(org, "ana", Role.OWNER))


def test_AC_TEN_28_suspend_waits_for_write_in_flight(
    owner_ctx: tuple[Organization, TenantContext],
) -> None:
    org, ctx = owner_ctx
    widget = new_widget(org)
    write = rename(ctx, widget)
    writer = Held(lambda: locks.ensure_writable(ctx), then=write)
    suspension = Second(suspend(org))

    blocks_behind(writer, suspension)

    assert suspension.error is None
    assert (widget_name(widget), status(org)) == ("after", OrgStatus.SUSPENDED.value)


def test_AC_TEN_28_write_after_the_suspension_sees_it(
    owner_ctx: tuple[Organization, TenantContext],
) -> None:
    org, ctx = owner_ctx  # resolved while still active
    widget = new_widget(org)
    suspension = Held(suspend(org))
    writer = Second(rename(ctx, widget))

    blocks_behind(suspension, writer)

    assert isinstance(writer.error, OrganizationSuspended)
    assert (widget_name(widget), status(org)) == ("before", OrgStatus.SUSPENDED.value)


def test_AC_TEN_28_membership_change_after_the_suspension_sees_it(
    owner_ctx: tuple[Organization, TenantContext],
) -> None:
    org, ctx = owner_ctx
    suspension = Held(suspend(org))
    change = Second(mutex(ctx))

    blocks_behind(suspension, change)

    assert isinstance(change.error, OrganizationSuspended)


def test_writes_do_not_wait_for_each_other(owner_ctx: tuple[Organization, TenantContext]) -> None:
    org, ctx = owner_ctx
    widget = new_widget(org)

    runs_beside(Held(lambda: locks.ensure_writable(ctx)), Second(rename(ctx, widget)))

    assert widget_name(widget) == "after"


def test_a_write_does_not_wait_for_a_membership_change(
    owner_ctx: tuple[Organization, TenantContext],
) -> None:
    org, ctx = owner_ctx
    widget = new_widget(org)

    runs_beside(Held(mutex(ctx)), Second(rename(ctx, widget)))

    assert widget_name(widget) == "after"


def test_RN_TEN_14_membership_changes_wait_for_each_other(
    owner_ctx: tuple[Organization, TenantContext],
) -> None:
    _org, ctx = owner_ctx
    second = Second(mutex(ctx))

    blocks_behind(Held(mutex(ctx)), second)

    assert second.error is None


def test_the_wait_for_the_lock_is_bounded(
    owner_ctx: tuple[Organization, TenantContext], monkeypatch: pytest.MonkeyPatch
) -> None:
    org, ctx = owner_ctx
    widget = new_widget(org)
    monkeypatch.setattr(locks, "LOCK_TIMEOUT", "200ms")  # 5 s in production: the test is short
    suspension = Held(suspend(org))
    writer = Second(rename(ctx, widget))
    suspension.start()
    try:
        assert suspension.reached.wait(PATIENCE)
        writer.start()
        writer.join(PATIENCE)
        assert not writer.is_alive(), "the writer waited past its lock timeout"
    finally:
        suspension.go_on.set()
        suspension.join(PATIENCE)

    assert isinstance(writer.error, OperationalError)
    assert "lock timeout" in str(writer.error)
    assert widget_name(widget) == "before"
