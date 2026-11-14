"""No write path moves a row to another organization or reaches its rows (AC-TEN-07, RN-TEN-04).

``update``, ``_update`` and ``bulk_update`` (and the ``a*`` variants) never change the organization
of a row, under any scope. ``save_base()`` and a ``pre_save`` receiver skip ``save()``; the
``UPDATE``/``INSERT`` underneath check the active tenant again. They raise inside ``save_base()``,
which marks the transaction for rollback: a savepoint keeps the test transaction usable.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.db.models.signals import pre_save

from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import TenantQuerySet, TenantScopeError, UnscopedReason
from apps.tenancy.models import Organization
from tests.testapps.tenant_probe.models import Widget

PLATFORM = UnscopedReason.PLATFORM_COMMAND
Rows = tuple[TenantContext, TenantContext, Widget, Widget]


def ctx_for(organization_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_ctx(name: str) -> TenantContext:
    org = Organization.objects.unscoped(PLATFORM).create(
        name=name, created_by_operator="operator@hub.test"
    )
    return ctx_for(org.id)


def new_widget(ctx: TenantContext, name: str) -> Widget:
    with tenant_scope(ctx):
        return Widget.objects.for_tenant(ctx).create(name=name)


def snapshot() -> list[tuple[Any, ...]]:
    return sorted(
        Widget.objects.unscoped(PLATFORM).values_list("pk", "organization_id", "name"), key=str
    )


@pytest.fixture
def rows() -> Rows:
    a, b = new_ctx("A"), new_ctx("B")
    return a, b, new_widget(a, "mine"), new_widget(b, "theirs")


def move_by_bulk_update(qs: TenantQuerySet[Widget], mine: Widget, b: uuid.UUID) -> Any:
    widget = qs.get(pk=mine.pk)
    widget.organization_id = b
    return qs.bulk_update([widget], ["organization"])


def move_by_bulk_update_attname(qs: TenantQuerySet[Widget], mine: Widget, b: uuid.UUID) -> Any:
    widget = qs.get(pk=mine.pk)
    widget.organization_id = b
    return qs.bulk_update([widget], ["organization_id"])


Move = Callable[[TenantQuerySet[Widget], Widget, uuid.UUID], Any]
MOVES: dict[str, Move] = {
    "update_id": lambda qs, _mine, b: qs.update(organization_id=b),
    "update_instance": lambda qs, _mine, b: qs.update(
        organization=Organization.objects.unscoped(PLATFORM).get(pk=b)
    ),
    "_update": lambda qs, _mine, b: qs._update([(Widget._meta.get_field("organization"), None, b)]),
    "bulk_update": move_by_bulk_update,
    "bulk_update_attname": move_by_bulk_update_attname,
}


@pytest.mark.django_db
@pytest.mark.parametrize("move", MOVES.values(), ids=MOVES.keys())
@pytest.mark.parametrize("scope", ["tenant", "unscoped"])
def test_AC_TEN_07_update_never_moves_a_row(rows: Rows, move: Move, scope: str) -> None:
    a, b, mine, _theirs = rows
    before = snapshot()

    qs = Widget.objects.for_tenant(a) if scope == "tenant" else Widget.objects.unscoped(PLATFORM)

    with tenant_scope(a), pytest.raises(TenantScopeError, match="cannot change the organization"):
        move(qs, mine, b.organization_id)

    assert snapshot() == before


# The ``a*`` variants run on another thread and connection: committed rows make a write that slipped
# past the guard land instead of waiting on the lock of the test transaction.
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_07_async_update_never_moves_a_row(rows: Rows) -> None:
    a, b, mine, _theirs = rows
    scoped = Widget.objects.for_tenant(a)
    before = snapshot()
    moved = Widget(id=mine.pk, organization_id=b.organization_id, name="mine")

    with pytest.raises(TenantScopeError, match="update cannot change the organization"):
        asyncio.run(scoped.aupdate(organization_id=b.organization_id))
    with pytest.raises(TenantScopeError, match="bulk_update cannot change the organization"):
        asyncio.run(scoped.abulk_update([moved], ["organization"]))

    assert snapshot() == before


@pytest.mark.django_db
def test_AC_TEN_07_update_of_other_fields_still_works(rows: Rows) -> None:
    a, _b, mine, _theirs = rows
    scoped = Widget.objects.for_tenant(a)

    with tenant_scope(a):
        scoped.update(name="renamed")
        widget = scoped.get(pk=mine.pk)
        widget.name = "bulk"
        scoped.bulk_update([widget], ["name"])

    assert scoped.get(pk=mine.pk).name == "bulk"


@pytest.mark.django_db
def test_AC_TEN_07_save_base_never_writes_another_org(rows: Rows) -> None:
    a, b, _mine, theirs = rows
    before = snapshot()

    with tenant_scope(a):
        forged = Widget(id=theirs.pk, organization_id=b.organization_id, name="hijacked")
        forged._state.adding = False  # as if read: Django tries the UPDATE first
        with (
            pytest.raises(TenantScopeError, match="save for another organization"),
            transaction.atomic(),
        ):
            forged.save_base()
        # Only the UPDATE runs: rejected there, before its filter could hide the row.
        with (
            pytest.raises(TenantScopeError, match="save for another organization"),
            transaction.atomic(),
        ):
            forged.save_base(force_update=True)
        new = Widget(organization_id=b.organization_id, name="new in B")
        with (
            pytest.raises(TenantScopeError, match="save for another organization"),
            transaction.atomic(),
        ):
            new.save_base(force_insert=True)
        own_org = Widget(id=theirs.pk, organization_id=a.organization_id, name="hijacked")
        own_org._state.adding = False
        # The UPDATE filters by the active organization and finds nothing; the INSERT hits the pk.
        with pytest.raises(IntegrityError), transaction.atomic():
            own_org.save_base()

    assert snapshot() == before


def test_AC_TEN_07_save_base_without_tenant_raises() -> None:
    """No ``django_db`` mark: a call that reached the database would fail with another error."""
    forged = Widget(id=uuid.uuid4(), organization_id=uuid.uuid4(), name="x")
    forged._state.adding = False

    with pytest.raises(TenantScopeError, match="save without an active tenant"):
        forged.save_base()
    with pytest.raises(TenantScopeError, match="save without an active tenant"):
        forged.save_base(force_insert=True)


@pytest.fixture
def hijacking_receiver(rows: Rows) -> Iterator[None]:
    _a, b, _mine, theirs = rows

    def hijack(sender: type[Widget], instance: Widget, **kwargs: Any) -> None:
        instance.organization_id = b.organization_id
        instance.pk = theirs.pk

    pre_save.connect(hijack, sender=Widget, weak=False)
    try:
        yield
    finally:
        pre_save.disconnect(hijack, sender=Widget)


@pytest.mark.django_db
@pytest.mark.usefixtures("hijacking_receiver")
def test_AC_TEN_07_pre_save_receiver_never_writes_another_org(rows: Rows) -> None:
    a, _b, mine, _theirs = rows
    before = snapshot()

    with tenant_scope(a):
        widget = Widget.objects.for_tenant(a).get(pk=mine.pk)
        widget.name = "hijacked"
        with (
            pytest.raises(TenantScopeError, match="save for another organization"),
            transaction.atomic(),
        ):
            widget.save()

    assert snapshot() == before
