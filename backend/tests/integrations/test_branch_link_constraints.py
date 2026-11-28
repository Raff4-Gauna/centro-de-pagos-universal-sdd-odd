"""``BranchLink``: the constraints of design.md §5 and its composite keys (T-INT-03).

Tested on the model, without services (ADR-0002 §2): at most one link per ``Branch`` +
integration in any state (Q-429, AC-INT-43); an informed Store reference once per integration
(Q-432 a)); the origin ``none`` exactly when there is no reference (RN-INT-23, Q-424); the date
follows ``is_active``; and the two composite keys keep the branch and the integration in the link's
organization, also for a row written by raw SQL (RN-INT-13, AC-INT-34, design.md §5.1).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantScopeError
from apps.identity.models import User
from apps.integrations.models import BranchLink, Integration
from apps.tenancy.models import Branch, Organization
from tests.tenancy.locking import PLATFORM, new_org, system_ctx

pytestmark = pytest.mark.django_db

INACTIVE: dict[str, Any] = {"is_active": False, "deactivated_at": timezone.now()}


def new_user() -> User:
    suffix = uuid.uuid4().hex[:12]
    return User.objects.create_user(google_sub=f"sub-{suffix}", email=f"{suffix}@hub.test")


def new_branch(organization: Organization, name: str = "Centro") -> Branch:
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx), transaction.atomic():
        return Branch.objects.for_tenant(ctx).create(name=name)


def new_integration(organization: Organization, name: str = "Cuenta 1") -> Integration:
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx), transaction.atomic():
        return Integration.objects.for_tenant(ctx).create(
            provider_code="fake", name=name, environment="test", created_by=new_user()
        )


def insert(branch: Branch, integration: Integration, **fields: Any) -> BranchLink:
    values: dict[str, Any] = {"store_origin": "none", "created_by": new_user(), **fields}
    ctx = system_ctx(integration.organization_id)
    with tenant_scope(ctx), transaction.atomic():
        return BranchLink.objects.for_tenant(ctx).create(
            branch=branch, integration=integration, **values
        )


def constraint_of(error: pytest.ExceptionInfo[IntegrityError]) -> str:
    return str(error.value.__cause__.diag.constraint_name)  # type: ignore[union-attr]


def raw_insert(organization_id: uuid.UUID, branch_id: uuid.UUID, integration_id: uuid.UUID) -> None:
    """A row written without the ORM: only the database stands between it and another tenant."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO integrations_branchlink (id, organization_id, branch_id, integration_id,"
            " store_ref, store_origin, data, is_active, created_by_id, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, '', 'none', '{}', true, %s, now(), now())",
            [uuid.uuid4(), organization_id, branch_id, integration_id, new_user().pk],
        )


def link_count() -> int:
    return BranchLink.objects.unscoped(PLATFORM).count()


# --- RN-INT-13: the composite keys (AC-INT-34) ---


@pytest.mark.parametrize(
    ("foreign", "constraint"),
    [
        ("branch", "branch_link_branch_same_org"),
        ("integration", "branch_link_integration_same_org"),
    ],
)
def test_AC_INT_34_link_mixing_organizations_is_rejected(foreign: str, constraint: str) -> None:
    org_a, org_b = new_org("A"), new_org("B")
    branch_a, integration_a = new_branch(org_a), new_integration(org_a)
    branch_b, integration_b = new_branch(org_b), new_integration(org_b)
    branch, integration = (
        (branch_b, integration_a) if foreign == "branch" else (branch_a, integration_b)
    )

    with pytest.raises(IntegrityError) as raised:
        raw_insert(org_a.id, branch.id, integration.id)

    assert constraint_of(raised) == constraint
    assert link_count() == 0
    raw_insert(org_a.id, branch_a.id, integration_a.id)  # all three of A: accepted
    assert link_count() == 1


def test_AC_INT_34_orm_never_links_a_branch_of_another_organization() -> None:
    org_a, org_b = new_org("A"), new_org("B")

    with pytest.raises(IntegrityError) as raised:
        insert(new_branch(org_b), new_integration(org_a))

    assert constraint_of(raised) == "branch_link_branch_same_org"
    assert link_count() == 0


# --- Q-429: one link per pair, in any state (AC-INT-43) ---


@pytest.mark.parametrize("first", [{}, INACTIVE], ids=["active", "inactive"])
def test_AC_INT_43_second_link_same_pair_is_rejected(first: dict[str, Any]) -> None:
    organization = new_org("A")
    branch, integration = new_branch(organization), new_integration(organization)
    insert(branch, integration, **first)

    with pytest.raises(IntegrityError) as raised:
        insert(branch, integration)
    assert constraint_of(raised) == "branch_link_one_per_pair"

    with pytest.raises(IntegrityError) as raised:
        raw_insert(organization.id, branch.id, integration.id)
    assert constraint_of(raised) == "branch_link_one_per_pair"
    assert link_count() == 1


def test_AC_INT_43_other_pairs_are_free() -> None:
    organization = new_org("A")
    centro, sur = new_branch(organization, "Centro"), new_branch(organization, "Sur")
    uno, dos = new_integration(organization, "Uno"), new_integration(organization, "Dos")

    for branch, integration in ((centro, uno), (centro, dos), (sur, uno), (sur, dos)):
        insert(branch, integration)

    assert link_count() == 4


def test_AC_INT_43_one_per_pair_is_the_cash_register_target() -> None:
    """``(organization_id, branch_id, integration_id)`` unique: the register points at it."""
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, BranchLink._meta.db_table)

    target = constraints["branch_link_one_per_pair"]
    assert target["unique"] is True
    assert target["columns"] == ["organization_id", "branch_id", "integration_id"]
    for name, columns in (
        ("branch_link_org_branch_active", ["organization_id", "branch_id", "is_active"]),
        ("branch_link_org_integ_active", ["organization_id", "integration_id", "is_active"]),
    ):
        assert constraints[name]["index"] is True
        assert constraints[name]["columns"] == columns


# --- Q-432 a): the Store reference, once per integration ---


def test_Q_432_store_ref_unique_per_integration() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    centro, sur = new_branch(org_a, "Centro"), new_branch(org_a, "Sur")
    uno, dos = new_integration(org_a, "Uno"), new_integration(org_a, "Dos")
    insert(centro, uno, store_ref="store-1", store_origin="created")

    with pytest.raises(IntegrityError) as raised:
        insert(sur, uno, store_ref="store-1", store_origin="imported")
    assert constraint_of(raised) == "branch_link_unique_store_ref"

    # Another integration, or another organization, may hold the same reference.
    insert(sur, dos, store_ref="store-1", store_origin="manual")
    insert(new_branch(org_b), new_integration(org_b), store_ref="store-1", store_origin="manual")
    # An inactive link still holds its reference: reactivating it gives back the same Store.
    insert(new_branch(org_a, "Este"), uno, store_ref="store-2", store_origin="manual", **INACTIVE)
    with pytest.raises(IntegrityError) as raised:
        insert(new_branch(org_a, "Oeste"), uno, store_ref="store-2", store_origin="manual")
    assert constraint_of(raised) == "branch_link_unique_store_ref"


def test_Q_432_links_without_reference_never_collide() -> None:
    organization = new_org("A")
    integration = new_integration(organization)

    insert(new_branch(organization, "Centro"), integration)
    insert(new_branch(organization, "Sur"), integration)

    assert link_count() == 2


# --- RN-INT-23: origin and reference; activity ---


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"store_origin": "none", "store_ref": "store-1"}, "branch_link_store_ref_coherent"),
        ({"store_origin": "created", "store_ref": ""}, "branch_link_store_ref_coherent"),
        ({"store_origin": "imported", "store_ref": ""}, "branch_link_store_ref_coherent"),
        ({"store_origin": "manual", "store_ref": ""}, "branch_link_store_ref_coherent"),
        ({"store_origin": "guessed", "store_ref": "store-1"}, "branch_link_store_origin_valid"),
        ({"is_active": False}, "branch_link_active_coherent"),
        ({"deactivated_at": timezone.now()}, "branch_link_active_coherent"),
    ],
)
def test_RN_INT_23_store_origin_none_has_no_ref(fields: dict[str, Any], constraint: str) -> None:
    organization = new_org("A")

    with pytest.raises(IntegrityError) as raised:
        insert(new_branch(organization), new_integration(organization), **fields)

    assert constraint_of(raised) == constraint


def test_RN_INT_23_defaults_and_valid_origins() -> None:
    organization = new_org("A")
    integration = new_integration(organization)

    stored = insert(new_branch(organization, "Centro"), integration)
    for origin in ("created", "imported", "manual"):
        insert(new_branch(organization, origin), integration, store_ref=origin, store_origin=origin)

    row = BranchLink.objects.unscoped(PLATFORM).get(pk=stored.pk)
    assert (row.store_ref, row.store_origin, row.data) == ("", "none", {})
    assert (row.is_active, row.deactivated_at) == (True, None)
    assert link_count() == 4


def test_RN_INT_13_links_fail_closed_are_never_deleted_and_repr_is_the_pk() -> None:
    organization = new_org("A")
    link = insert(
        new_branch(organization),
        new_integration(organization),
        store_ref="s-9",
        store_origin="manual",
        data={"address": "Calle 1"},
    )

    with pytest.raises(TenantScopeError):
        list(BranchLink.objects.all())
    with tenant_scope(system_ctx(organization.id)), pytest.raises(HardDeleteForbidden):
        link.delete()
    with pytest.raises(HardDeleteForbidden):
        BranchLink.objects.for_tenant(system_ctx(organization.id)).delete()
    for text in (str(link), repr(link)):
        assert str(link.pk) in text
        assert "s-9" not in text
        assert "Calle 1" not in text
    assert link_count() == 1
