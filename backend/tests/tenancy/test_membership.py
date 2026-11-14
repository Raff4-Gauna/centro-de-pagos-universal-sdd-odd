"""The ``tenancy_membership`` table (design.md §5): RN-TEN-07, RN-TEN-21, RNF-TEN-05.

The invariants live in PostgreSQL as the final net (ADR-0002 §2): these tests write through
``for_tenant(ctx).create``, which checks no business rule, so what stops a bad row is the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantScopeError, UnscopedReason
from apps.identity.models import User
from apps.tenancy.models import Membership, Organization
from apps.tenancy.models.membership import EndedReason, MembershipStatus

PLATFORM = UnscopedReason.PLATFORM_COMMAND
ENDED_AT = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
TABLE = "tenancy_membership"


def ctx_for(organization: Organization) -> TenantContext:
    return TenantContext(
        organization_id=organization.id,
        organization_status=OrgStatus.ACTIVE,
        actor=SystemActor(SystemReason.PLATFORM_COMMAND),
    )


def new_org(name: str) -> TenantContext:
    organization = Organization.objects.unscoped(PLATFORM).create(
        name=name, created_by_operator="operator@hub.test"
    )
    return ctx_for(organization)


def new_user(name: str) -> User:
    return User.objects.create_user(google_sub=f"sub-{name}", email=f"{name}@hub.test")


def add(ctx: TenantContext, user: User, **values: Any) -> Membership:
    with tenant_scope(ctx):
        return Membership.objects.for_tenant(ctx).create(
            user=user, **{"role": Role.OPERATOR, **values}
        )


def assert_rejected(constraint: str, ctx: TenantContext, user: User, **values: Any) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        add(ctx, user, **values)


def revoked(reason: EndedReason = EndedReason.REVOKED) -> dict[str, Any]:
    return {"status": MembershipStatus.REVOKED, "ended_reason": reason, "ended_at": ENDED_AT}


@pytest.fixture
def org() -> TenantContext:
    return new_org("A")


@pytest.fixture
def ana() -> User:
    return new_user("ana")


# --- RN-TEN-07: at most one active membership per organization and user -------------------------


@pytest.mark.django_db
def test_RN_TEN_07_one_active_per_org_and_user(org: TenantContext, ana: User) -> None:
    add(org, ana, role=Role.VIEWER)

    assert_rejected("membership_one_active_per_org_user", org, ana, role=Role.ADMIN)

    with tenant_scope(org):
        assert Membership.objects.for_tenant(org).filter(user=ana).count() == 1


@pytest.mark.django_db
def test_RN_TEN_07_two_orgs_are_allowed(org: TenantContext, ana: User) -> None:
    other = new_org("B")

    add(org, ana, role=Role.OPERATOR)
    add(other, ana, role=Role.VIEWER)

    rows = Membership.objects.unscoped(PLATFORM).filter(user=ana).values_list("organization_id")
    assert {organization_id for (organization_id,) in rows} == {
        org.organization_id,
        other.organization_id,
    }


@pytest.mark.django_db
def test_RN_TEN_07_two_users_in_one_org_are_allowed(org: TenantContext, ana: User) -> None:
    add(org, ana)
    add(org, new_user("bea"))

    with tenant_scope(org):
        assert Membership.objects.for_tenant(org).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(Role))
def test_RN_TEN_07_each_role_is_accepted(org: TenantContext, ana: User, role: Role) -> None:
    assert add(org, ana, role=role).role == role


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["superuser", "", "Owner"])
def test_RN_TEN_07_role_outside_the_four_is_rejected(
    org: TenantContext, ana: User, role: str
) -> None:
    assert_rejected("membership_role_valid", org, ana, role=role)


@pytest.mark.django_db
def test_RN_TEN_07_a_new_membership_is_active(org: TenantContext, ana: User) -> None:
    membership = add(org, ana)

    assert membership.status == MembershipStatus.ACTIVE
    assert membership.ended_reason is None
    assert membership.ended_at is None


# --- RN-TEN-21: revoked is kept, coherent and never blocks a new membership ---------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"ended_reason": EndedReason.REVOKED}, id="active-with-reason"),
        pytest.param({"ended_at": ENDED_AT}, id="active-with-end"),
        pytest.param(
            {"status": MembershipStatus.REVOKED, "ended_at": ENDED_AT}, id="revoked-without-reason"
        ),
        pytest.param(
            {"status": MembershipStatus.REVOKED, "ended_reason": EndedReason.LEFT},
            id="revoked-without-end",
        ),
        pytest.param(
            {"status": MembershipStatus.REVOKED, "ended_reason": "expired", "ended_at": ENDED_AT},
            id="revoked-with-unknown-reason",
        ),
    ],
)
def test_RN_TEN_21_end_fields_are_coherent(
    org: TenantContext, ana: User, values: dict[str, Any]
) -> None:
    assert_rejected("membership_end_coherent", org, ana, **values)


@pytest.mark.django_db
@pytest.mark.parametrize("reason", list(EndedReason))
def test_RN_TEN_21_revoked_or_left_is_accepted(
    org: TenantContext, ana: User, reason: EndedReason
) -> None:
    membership = add(org, ana, ended_by=ana, **revoked(reason))

    assert membership.ended_reason == reason


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["suspended", "pending", ""])
def test_RN_TEN_21_status_outside_active_and_revoked_is_rejected(
    org: TenantContext, ana: User, status: str
) -> None:
    # Every unknown status also breaks ``membership_end_coherent``; PostgreSQL reports one of them.
    assert_rejected("membership_(status_valid|end_coherent)", org, ana, status=status)


@pytest.mark.django_db
def test_RN_TEN_21_revoked_is_kept_and_a_new_one_is_allowed(org: TenantContext, ana: User) -> None:
    add(org, ana, role=Role.ADMIN, **revoked())
    add(org, ana, role=Role.VIEWER, **revoked(EndedReason.LEFT))

    add(org, ana, role=Role.OPERATOR)

    with tenant_scope(org):
        rows = Membership.objects.for_tenant(org).filter(user=ana)
        assert sorted(rows.values_list("status", flat=True)) == ["active", "revoked", "revoked"]


@pytest.mark.django_db
def test_RN_TEN_21_a_membership_is_never_deleted(org: TenantContext, ana: User) -> None:
    membership = add(org, ana)

    with tenant_scope(org):
        with pytest.raises(HardDeleteForbidden):
            membership.delete()
        with pytest.raises(HardDeleteForbidden):
            Membership.objects.for_tenant(org).delete()
        assert Membership.objects.for_tenant(org).filter(pk=membership.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["user", "ended_by", "invited_by"])
def test_RN_TEN_21_a_user_with_memberships_is_never_deleted(
    org: TenantContext, ana: User, field: str
) -> None:
    holder = ana if field == "user" else new_user("bea")
    add(org, holder, **({} if field == "user" else {field: ana}))

    with pytest.raises(ProtectedError):
        ana.delete()

    assert User.objects.filter(pk=ana.pk).exists()


# --- Isolation (RN-TEN-01, AC-TEN-11): a ``TenantModel`` like any other -------------------------


@pytest.mark.django_db
def test_RN_TEN_07_membership_fails_closed(org: TenantContext, ana: User) -> None:
    with pytest.raises(TenantScopeError):
        Membership.objects.filter(user=ana).exists()
    with pytest.raises(TenantScopeError, match="without an active tenant"):
        Membership(organization_id=org.organization_id, user=ana, role=Role.OWNER).save()

    assert not Membership.objects.unscoped(PLATFORM).exists()


@pytest.mark.django_db
def test_RN_TEN_07_membership_is_written_only_in_the_active_org(
    org: TenantContext, ana: User
) -> None:
    other = new_org("B")

    with tenant_scope(org), pytest.raises(TenantScopeError, match="another organization"):
        Membership.objects.for_tenant(org).create(
            organization_id=other.organization_id, user=ana, role=Role.OWNER
        )

    assert not Membership.objects.unscoped(PLATFORM).exists()


# --- Schema (RNF-TEN-05): constraints and the partial index of design.md §5 ---------------------


def table_constraints() -> dict[str, dict[str, Any]]:
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, TABLE)


@pytest.mark.django_db
def test_RNF_TEN_05_constraints_are_the_ones_of_the_design() -> None:
    names = set(table_constraints())

    assert {
        "membership_one_active_per_org_user",
        "membership_role_valid",
        "membership_status_valid",
        "membership_end_coherent",
        "membership_active_user_org",
    } <= names


@pytest.mark.django_db
def test_RNF_TEN_05_resolution_index_is_partial_and_covers_the_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = %s AND indexname = %s",
            [TABLE, "membership_active_user_org"],
        )
        (definition,) = cursor.fetchone()

    assert "(user_id, organization_id) INCLUDE (role)" in definition
    assert "WHERE ((status)::text = 'active'::text)" in definition


@pytest.mark.django_db
def test_RN_TEN_07_one_active_is_a_partial_unique_on_org_and_user() -> None:
    constraint = table_constraints()["membership_one_active_per_org_user"]

    assert constraint["unique"] is True
    assert constraint["columns"] == ["organization_id", "user_id"]


def test_RN_TEN_07_ids_are_uuids() -> None:
    field = Membership._meta.pk
    assert field is not None
    assert field.get_internal_type() == "UUIDField"
    assert isinstance(field.default(), uuid.UUID)
