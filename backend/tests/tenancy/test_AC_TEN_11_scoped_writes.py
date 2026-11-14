"""Writes and reads that a tenant scope cannot filter fail closed (AC-TEN-11, RN-TEN-02).

``INSERT ... ON CONFLICT``, hand-written SQL and a replaced ``query`` do not carry the filter of
``for_tenant``: under a tenant they raise, and the row of the other organization stays untouched.
"""

from __future__ import annotations

import asyncio
import pickle
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import TenantScopeError, UnscopedReason
from apps.tenancy.models import Organization
from apps.tenancy.models.organization import OrganizationQuerySet

PLATFORM = UnscopedReason.PLATFORM_COMMAND


def ctx_for(organization_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_org(name: str, **fields: Any) -> Organization:
    return Organization.objects.unscoped(PLATFORM).create(
        name=name, created_by_operator="operator@hub.test", **fields
    )


def hijack(other: Organization) -> Organization:
    return Organization(
        id=other.pk,
        name="hijacked",
        created_by_operator="op@hub.test",
        platform_creation_key=other.platform_creation_key,
    )


Write = Callable[[OrganizationQuerySet, Organization], Any]

BULK_WRITES: dict[str, Write] = {
    "update_by_id": lambda qs, other: qs.bulk_create(
        [hijack(other)], update_conflicts=True, unique_fields=["id"], update_fields=["name"]
    ),
    "update_by_key": lambda qs, other: qs.bulk_create(
        [hijack(other)],
        update_conflicts=True,
        unique_fields=["platform_creation_key"],
        update_fields=["name"],
    ),
    "ignore": lambda qs, other: qs.bulk_create([hijack(other)], ignore_conflicts=True),
    "plain_insert": lambda qs, other: qs.bulk_create([hijack(other)]),
    "new_organization": lambda qs, other: qs.bulk_create(
        [Organization(name="new", created_by_operator="op@hub.test")]
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("write", BULK_WRITES.values(), ids=BULK_WRITES.keys())
def test_AC_TEN_11_bulk_create_under_a_tenant_leaves_other_organizations(write: Write) -> None:
    mine, other = new_org("Mine"), new_org("Other", platform_creation_key="key-other")
    ctx = ctx_for(mine.id)

    with tenant_scope(ctx), pytest.raises(TenantScopeError):
        write(Organization.objects.for_tenant(ctx), other)

    other.refresh_from_db()
    assert other.name == "Other"
    assert Organization.objects.unscoped(PLATFORM).count() == 2


# ``abulk_create`` runs on another thread and connection: with the rows committed, a write that
# slipped past the guard would land instead of waiting on the lock of the test transaction.
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_11_abulk_create_under_a_tenant_leaves_other_organizations() -> None:
    mine, other = new_org("Mine"), new_org("Other")
    ctx = ctx_for(mine.id)
    scoped = Organization.objects.for_tenant(ctx)

    with tenant_scope(ctx), pytest.raises(TenantScopeError):
        asyncio.run(
            scoped.abulk_create(
                [hijack(other)], update_conflicts=True, unique_fields=["id"], update_fields=["name"]
            )
        )

    other.refresh_from_db()
    assert other.name == "Other"


@pytest.mark.django_db
def test_AC_TEN_11_bulk_create_on_conflict_is_allowed_unscoped() -> None:
    other = new_org("Other")

    Organization.objects.unscoped(PLATFORM).bulk_create(
        [hijack(other)], update_conflicts=True, unique_fields=["id"], update_fields=["name"]
    )

    other.refresh_from_db()
    assert other.name == "hijacked"


@pytest.mark.django_db
def test_AC_TEN_11_raw_needs_unscoped() -> None:
    mine, _other = new_org("Mine"), new_org("Other")
    ctx = ctx_for(mine.id)
    sql = "SELECT * FROM tenancy_organization"

    with tenant_scope(ctx), pytest.raises(TenantScopeError):
        Organization.objects.for_tenant(ctx).raw(sql)

    assert len(list(Organization.objects.unscoped(PLATFORM).raw(sql))) == 2


@pytest.mark.django_db
def test_AC_TEN_11_replacing_the_query_clears_the_scope() -> None:
    mine, _other = new_org("Mine"), new_org("Other")
    ctx = ctx_for(mine.id)

    with tenant_scope(ctx):
        qs = Organization.objects.for_tenant(ctx)
        qs.query = pickle.loads(pickle.dumps(Organization.objects.all().query))  # noqa: S301
        assert qs.scope is None
        with pytest.raises(TenantScopeError):
            list(qs)
        rescoped = qs.for_tenant(ctx)

        assert list(rescoped) == [mine]
