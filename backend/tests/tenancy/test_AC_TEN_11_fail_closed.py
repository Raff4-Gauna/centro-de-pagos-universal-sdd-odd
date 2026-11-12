"""A query without an organization fails closed (AC-TEN-11, RN-TEN-02, design.md §3.4).

The terminal methods are listed here by hand, not read from the implementation: a guard dropped
from the queryset makes its case fail. They run without database access (no ``django_db``
mark), so a call that slipped past the guard would fail with pytest-django's database error, not
with ``TenantScopeError``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.db import IntegrityError, transaction

from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantScopeError, UnscopedReason
from apps.tenancy.models import Organization
from apps.tenancy.models.organization import OrganizationQuerySet

Query = Callable[[OrganizationQuerySet], Any]


def ctx_for(organization_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_org(name: str = "Acme", **fields: Any) -> Organization:
    return Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND).create(
        name=name, created_by_operator="operator@hub.test", **fields
    )


def drain(qs: OrganizationQuerySet) -> list[Organization]:
    async def collect() -> list[Organization]:
        return [org async for org in qs.aiterator()]

    return asyncio.run(collect())


TERMINAL: dict[str, Query] = {
    "iter": lambda qs: list(qs),
    "len": len,
    "bool": bool,
    "index": lambda qs: qs[0],
    "slice": lambda qs: list(qs[:5]),
    "first": lambda qs: qs.first(),
    "last": lambda qs: qs.order_by("name").last(),
    "earliest": lambda qs: qs.earliest("created_at"),
    "latest": lambda qs: qs.latest("created_at"),
    "values": lambda qs: list(qs.values("id")),
    "values_list": lambda qs: list(qs.values_list("id", flat=True)),
    "dates": lambda qs: list(qs.dates("created_at", "day")),
    "iterator": lambda qs: list(qs.iterator()),
    "aiterator": drain,
    "count": lambda qs: qs.count(),
    "acount": lambda qs: asyncio.run(qs.acount()),
    "exists": lambda qs: qs.exists(),
    "contains": lambda qs: qs.contains(Organization(id=uuid.uuid4())),
    "aggregate": lambda qs: qs.aggregate(),
    "explain": lambda qs: qs.explain(),
    "get": lambda qs: qs.get(pk=uuid.uuid4()),
    "aget": lambda qs: asyncio.run(qs.aget(pk=uuid.uuid4())),
    "in_bulk": lambda qs: qs.in_bulk([uuid.uuid4()]),
    "create": lambda qs: qs.create(name="x", created_by_operator="op@hub.test"),
    "bulk_create": lambda qs: qs.bulk_create([Organization(name="x")]),
    "bulk_update": lambda qs: qs.bulk_update([Organization(id=uuid.uuid4())], ["name"]),
    "get_or_create": lambda qs: qs.get_or_create(name="x"),
    "update_or_create": lambda qs: qs.update_or_create(name="x"),
    "update": lambda qs: qs.update(name="x"),
    "delete": lambda qs: qs.delete(),
    "raw": lambda qs: qs.raw("SELECT * FROM tenancy_organization"),
    "union": lambda qs: Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND).union(qs),
}


@pytest.mark.parametrize("call", TERMINAL.values(), ids=TERMINAL.keys())
def test_AC_TEN_11_every_terminal_method_raises(call: Query) -> None:
    with pytest.raises(TenantScopeError):
        call(Organization.objects.all())


@pytest.mark.parametrize(
    "call",
    [
        lambda: Organization.objects.count(),
        lambda: Organization.objects.get(pk=uuid.uuid4()),
        lambda: Organization.objects.create(name="x", created_by_operator="op@hub.test"),
        lambda: list(Organization.objects.filter(name="x")),
        lambda: Organization.objects.exists(),
    ],
    ids=["count", "get", "create", "filter", "exists"],
)
def test_AC_TEN_11_manager_shortcuts_raise(call: Callable[[], Any]) -> None:
    with pytest.raises(TenantScopeError):
        call()


def test_AC_TEN_11_clone_keeps_scope() -> None:
    org_id = uuid.uuid4()
    scoped = Organization.objects.for_tenant(ctx_for(org_id))
    chained = scoped.filter(name="Acme").exclude(status="x").order_by("name").distinct()

    assert chained.scope == ctx_for(org_id)
    assert scoped.select_for_update().scope == ctx_for(org_id)
    # The organization filter itself travels with the clone (compiled, never executed).
    sql = str(chained.query)
    assert str(org_id) in sql or org_id.hex in sql
    rows = scoped.values("id")
    assert isinstance(rows, OrganizationQuerySet)
    assert rows.scope == ctx_for(org_id)
    unscoped = Organization.objects.unscoped(UnscopedReason.SYSTEM_FANOUT).filter(name="Acme")
    assert unscoped.scope is UnscopedReason.SYSTEM_FANOUT
    # A scope is never inherited backwards: a fresh queryset of the manager is unscoped again.
    assert Organization.objects.filter(name="Acme").scope is None


def test_AC_TEN_11_repr_does_not_query() -> None:
    assert "unscoped" in repr(Organization.objects.all())


def test_AC_TEN_11_for_tenant_requires_a_tenant_context() -> None:
    with pytest.raises(TypeError):
        Organization.objects.for_tenant(uuid.uuid4())  # type: ignore[arg-type]


def test_AC_TEN_11_unscoped_requires_a_reason() -> None:
    with pytest.raises(TypeError):
        Organization.objects.unscoped("platform_command")  # type: ignore[arg-type]


def test_AC_TEN_11_for_tenant_must_match_the_active_tenant() -> None:
    with tenant_scope(ctx_for(uuid.uuid4())), pytest.raises(TenantScopeError):
        Organization.objects.for_tenant(ctx_for(uuid.uuid4()))


@pytest.mark.django_db
def test_AC_TEN_11_for_tenant_returns_only_its_organization() -> None:
    mine, other = new_org("Mine"), new_org("Other")

    with tenant_scope(ctx_for(mine.id)):
        found = list(Organization.objects.for_tenant(ctx_for(mine.id)))
        missing = Organization.objects.for_tenant(ctx_for(mine.id)).filter(pk=other.pk).exists()

    assert found == [mine]
    assert missing is False


@pytest.mark.django_db
def test_hard_delete_is_forbidden() -> None:
    org = new_org()

    with pytest.raises(HardDeleteForbidden):
        org.delete()
    with pytest.raises(HardDeleteForbidden):
        Organization.objects.for_tenant(ctx_for(org.id)).delete()
    with pytest.raises(HardDeleteForbidden):
        Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND).delete()

    assert Organization.objects.for_tenant(ctx_for(org.id)).count() == 1


@pytest.mark.django_db
def test_organization_defaults_and_plain_base_manager() -> None:
    org = new_org()

    assert org.status == OrgStatus.ACTIVE
    assert org.timezone == "America/Argentina/Buenos_Aires"
    assert (org.legal_name, org.tax_id, org.platform_creation_key) == ("", "", None)
    # Django internals (forward FKs, refresh_from_db) use the base manager, which stays plain.
    assert not isinstance(Organization._base_manager.all(), OrganizationQuerySet)
    org.refresh_from_db()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"status": "deleted"}, "org_status_valid"),
        ({"name": ""}, "org_name_not_blank"),
        ({"tax_id": "20-1234567"}, "org_tax_id_digits"),
        ({"tax_id": "2012345678"}, "org_tax_id_digits"),
    ],
)
def test_organization_constraints(fields: dict[str, str], constraint: str) -> None:
    values = {"name": "Acme", **fields}
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        new_org(**values)


@pytest.mark.django_db
def test_organization_platform_creation_key_is_unique() -> None:
    new_org(platform_creation_key="op-key-1")
    new_org("Second")
    new_org("Third")  # several organizations without a key: NULL is not a duplicate

    with pytest.raises(IntegrityError), transaction.atomic():
        new_org("Again", platform_creation_key="op-key-1")
