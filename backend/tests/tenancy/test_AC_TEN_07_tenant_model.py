"""``TenantModel`` writes only in the active organization (AC-TEN-07 guard, AC-TEN-11, RN-TEN-04).

On ``Widget`` of the test app ``tenant_probe``. ``save()`` and ``delete()`` use the base manager,
which has no scope: these tests check their own guard, and that the row of the other organization
stays as it was. The same for ``Organization.save()`` with a changed ``pk``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.db import DatabaseError, transaction
from django.db.models.constants import OnConflict

from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import TenantScopeError, UnscopedReason
from apps.tenancy.models import Organization
from tests.testapps.tenant_probe.models import Widget

PLATFORM = UnscopedReason.PLATFORM_COMMAND


def ctx_for(organization_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_org(name: str) -> Organization:
    return Organization.objects.unscoped(PLATFORM).create(
        name=name, created_by_operator="operator@hub.test"
    )


def new_widget(ctx: TenantContext, name: str) -> Widget:
    with tenant_scope(ctx):
        return Widget.objects.for_tenant(ctx).create(name=name)


def stored(widget: Widget) -> dict[str, Any]:
    return dict(
        Widget.objects.unscoped(PLATFORM).values("organization_id", "name").get(pk=widget.pk)
    )


@pytest.fixture
def orgs() -> tuple[TenantContext, TenantContext]:
    return ctx_for(new_org("A").id), ctx_for(new_org("B").id)


@pytest.mark.django_db
def test_AC_TEN_07_save_rejects_other_org(orgs: tuple[TenantContext, TenantContext]) -> None:
    a, b = orgs

    with tenant_scope(a), pytest.raises(TenantScopeError, match="another organization"):
        Widget(organization_id=b.organization_id, name="sneaky").save()

    assert not Widget.objects.unscoped(PLATFORM).exists()


@pytest.mark.django_db
def test_AC_TEN_07_save_takes_the_active_organization(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, _b = orgs

    with tenant_scope(a):
        widget = Widget(name="mine")
        widget.save()

    assert stored(widget) == {"organization_id": a.organization_id, "name": "mine"}


@pytest.mark.django_db
def test_AC_TEN_07_create_under_a_tenant_takes_its_organization(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, b = orgs
    scoped = Widget.objects.for_tenant(a)
    other = Organization.objects.unscoped(PLATFORM).get(pk=b.organization_id)

    # No tenant active: the queryset itself rejects it, before ``save()`` would.
    with pytest.raises(TenantScopeError, match="create for another organization"):
        scoped.create(organization_id=b.organization_id, name="by id")
    with pytest.raises(TenantScopeError, match="create for another organization"):
        scoped.create(organization=other, name="by instance")
    with tenant_scope(a):
        created = scoped.create(name="mine")
        got, _ = scoped.get_or_create(name="again")

    assert stored(created)["organization_id"] == a.organization_id
    assert stored(got)["organization_id"] == a.organization_id
    assert not Widget.objects.unscoped(PLATFORM).filter(organization_id=b.organization_id).exists()


@pytest.mark.django_db
def test_AC_TEN_07_bulk_create_under_a_tenant_takes_its_organization(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, b = orgs
    scoped = Widget.objects.for_tenant(a)

    with pytest.raises(TenantScopeError, match="bulk_create for another organization"):
        scoped.bulk_create([Widget(name="ok"), Widget(organization_id=b.organization_id, name="x")])
    (widget,) = scoped.bulk_create([Widget(name="mine")])

    assert stored(widget)["organization_id"] == a.organization_id
    assert Widget.objects.unscoped(PLATFORM).count() == 1


@pytest.mark.django_db
def test_AC_TEN_07_save_with_a_changed_pk_leaves_other_org(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, b = orgs
    mine, theirs = new_widget(a, "mine"), new_widget(b, "theirs")

    with tenant_scope(a):
        loaded = Widget.objects.for_tenant(a).get(pk=mine.pk)
        loaded.pk, loaded.name = theirs.pk, "hijacked"
        with pytest.raises(TenantScopeError, match="changed pk"):
            loaded.save()
        # Never read: no saved pk to compare. The UPDATE filters by organization and finds nothing
        # (the savepoint keeps the test transaction usable after the error).
        forged = Widget(id=theirs.pk, organization_id=a.organization_id, name="hijacked")
        with pytest.raises(DatabaseError, match="did not affect any rows"), transaction.atomic():
            forged.save(force_update=True)
        forged._state.adding = False  # as if read: Django tries the UPDATE without force_update
        with pytest.raises(DatabaseError, match="did not affect any rows"), transaction.atomic():
            forged.save(update_fields=["name"])

    assert stored(theirs) == {"organization_id": b.organization_id, "name": "theirs"}
    assert stored(mine) == {"organization_id": a.organization_id, "name": "mine"}


@pytest.mark.django_db
def test_organization_id_is_immutable(orgs: tuple[TenantContext, TenantContext]) -> None:
    a, b = orgs
    theirs = new_widget(b, "theirs")
    moved = Widget.objects.unscoped(PLATFORM).get(pk=theirs.pk)

    with tenant_scope(a):
        moved.organization_id = a.organization_id
        with pytest.raises(TenantScopeError, match="changed organization"):
            moved.save()

    assert stored(theirs) == {"organization_id": b.organization_id, "name": "theirs"}


@pytest.mark.django_db
def test_AC_TEN_07_delete_never_reaches_another_org(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, b = orgs
    mine, theirs = new_widget(a, "mine"), new_widget(b, "theirs")
    loaded_theirs = Widget.objects.unscoped(PLATFORM).get(pk=theirs.pk)

    with tenant_scope(a):
        loaded = Widget.objects.for_tenant(a).get(pk=mine.pk)
        loaded.pk = theirs.pk
        with pytest.raises(TenantScopeError, match="changed pk"):
            loaded.delete()
        forged = Widget(id=theirs.pk, organization_id=a.organization_id, name="x")
        with pytest.raises(TenantScopeError, match="delete of another organization"):
            forged.delete()
        with pytest.raises(TenantScopeError, match="delete of another organization"):
            loaded_theirs.delete()
        Widget.objects.for_tenant(a).get(pk=mine.pk).delete()

    assert list(Widget.objects.unscoped(PLATFORM).values_list("pk", flat=True)) == [theirs.pk]


@pytest.mark.django_db
def test_AC_TEN_11_insert_on_conflict_under_a_tenant_raises(
    orgs: tuple[TenantContext, TenantContext],
) -> None:
    a, b = orgs
    theirs = new_widget(b, "theirs")
    scoped = Widget.objects.for_tenant(a)
    fields = Widget._meta.concrete_fields
    hijack = Widget(id=theirs.pk, organization_id=a.organization_id, name="hijacked")

    with pytest.raises(TenantScopeError, match="on conflict"):
        scoped._insert(
            [hijack],
            fields=fields,
            on_conflict=OnConflict.UPDATE,
            update_fields=[Widget._meta.get_field("name")],
            unique_fields=[Widget._meta.pk],
        )
    with pytest.raises(TenantScopeError, match="on conflict"):
        scoped._insert([hijack], fields=fields, on_conflict=OnConflict.IGNORE)
    foreign = Widget(organization_id=b.organization_id, name="foreign")
    with pytest.raises(TenantScopeError, match="_insert for another organization"):
        scoped._insert([foreign], fields=fields)

    assert stored(theirs) == {"organization_id": b.organization_id, "name": "theirs"}
    assert Widget.objects.unscoped(PLATFORM).count() == 1


def test_AC_TEN_11_tenant_model_without_scope_raises() -> None:
    """No ``django_db`` mark: a call that reached the database would fail with another error."""
    ctx = ctx_for(uuid.uuid4())
    widget = Widget(id=uuid.uuid4(), organization_id=ctx.organization_id, name="x")

    with pytest.raises(TenantScopeError, match="without for_tenant"):
        list(Widget.objects.filter(name="x"))
    with pytest.raises(TenantScopeError, match="without for_tenant"):
        Widget.objects.create(name="x")
    with pytest.raises(TenantScopeError, match="save without an active tenant"):
        widget.save()
    with pytest.raises(TenantScopeError, match="delete without an active tenant"):
        widget.delete()
    with pytest.raises(TenantScopeError, match="save without an active tenant"):
        Widget.objects.for_tenant(ctx).create(name="x")


@pytest.mark.django_db
def test_AC_TEN_07_organization_save_with_a_changed_pk_leaves_the_other() -> None:
    mine, other = new_org("Mine"), new_org("Other")

    loaded = Organization.objects.unscoped(PLATFORM).get(pk=mine.pk)
    loaded.pk, loaded.name = other.pk, "hijacked"
    with pytest.raises(TenantScopeError, match="changed pk"):
        loaded.save()
    with tenant_scope(ctx_for(mine.id)):
        forged = Organization(id=other.pk, name="hijacked", created_by_operator="op@hub.test")
        with pytest.raises(TenantScopeError, match="save of another organization"):
            forged.save(force_update=True)
        own = Organization.objects.for_tenant(ctx_for(mine.id)).get()
        own.name = "Renamed"
        own.save()

    names = dict(Organization.objects.unscoped(PLATFORM).values_list("pk", "name"))
    assert names == {mine.pk: "Renamed", other.pk: "Other"}
