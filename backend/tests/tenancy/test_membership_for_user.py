"""``Membership.for_user(user_id)``: the scope of "my organizations" (RF-TEN-02, design.md §3.4).

A model scope (``ModelScope``): the filter by user is the scope, across organizations, so it reads
only. Every write, ``raw`` and a combination with another scope fail closed before the database
(AC-TEN-11), like a queryset without a scope.
"""

from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.common.authz.roles import Role
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import TenantScopeError, UnscopedReason
from apps.common.tenancy.scopes import ModelScope
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import EndedReason, MembershipStatus
from tests.tenancy.api.probe import add_member, new_org, new_user, platform_ctx

pytestmark = pytest.mark.django_db


def test_RF_TEN_02_for_user_reads_the_memberships_of_one_user_across_organizations() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    ana, beto = new_user("ana"), new_user("beto")
    mine = {add_member(org_a, ana, Role.OPERATOR).pk, add_member(org_b, ana, Role.VIEWER).pk}
    add_member(org_a, beto, Role.OWNER)

    rows = Membership.objects.for_user(ana.pk)

    assert {m.pk for m in rows} == mine
    assert rows.filter(status=MembershipStatus.ACTIVE.value).count() == 2
    assert rows.scope == ModelScope("for_user", ana.pk)


def test_RF_TEN_02_for_user_needs_a_uuid() -> None:
    with pytest.raises(TypeError):
        Membership.objects.for_user(str(uuid.uuid4()))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "write",
    [
        lambda qs, org: qs.create(organization=org, user_id=uuid.uuid4(), role="viewer"),
        lambda qs, org: qs.update(role=Role.ADMIN.value),
        lambda qs, org: qs.bulk_update([], ["role"]),
        lambda qs, org: qs.get_or_create(organization=org, role="viewer"),
        lambda qs, org: qs.update_or_create(organization=org, defaults={"role": "viewer"}),
        lambda qs, org: qs.bulk_create([]),
        lambda qs, org: qs.raw("SELECT * FROM tenancy_membership"),
        lambda qs, org: qs.delete(),
        lambda qs, org: qs._raw_delete(qs.db),
    ],
    ids=[
        "create",
        "update",
        "bulk_update",
        "get_or_create",
        "update_or_create",
        "bulk_create",
        "raw",
        "delete",
        "_raw_delete",
    ],
)
def test_AC_TEN_11_for_user_is_read_only(write: object) -> None:
    org = new_org("A")
    ana = new_user("ana")
    add_member(org, ana, Role.OWNER)
    with pytest.raises(TenantScopeError, match="read-only"):
        write(Membership.objects.for_user(ana.pk), org)  # type: ignore[operator]
    assert Membership.objects.for_user(ana.pk).get().role == Role.OWNER.value


def test_AC_TEN_11_for_user_does_not_mix_with_other_scopes() -> None:
    org = new_org("A")
    ana, beto = new_user("ana"), new_user("beto")
    mine = Membership.objects.for_user(ana.pk)
    with pytest.raises(TenantScopeError):
        list(mine | Membership.objects.for_user(beto.pk))
    with pytest.raises(TenantScopeError):
        list(mine | Membership.objects.for_tenant(platform_ctx(org)))
    with pytest.raises(TenantScopeError):
        list(mine.union(Membership.objects.unscoped(UnscopedReason.PLATFORM_COMMAND)))
    assert list(mine | Membership.objects.for_user(ana.pk)) == []


def test_RF_TEN_02_for_user_keeps_the_revoked_ones_for_the_caller_to_filter() -> None:
    org = new_org("A")
    ana = new_user("ana")
    membership = add_member(org, ana, Role.ADMIN)
    with_tenant = platform_ctx(org)
    with tenant_scope(with_tenant):
        Membership.objects.for_tenant(with_tenant).filter(pk=membership.pk).update(
            status=MembershipStatus.REVOKED.value,
            ended_reason=EndedReason.LEFT.value,
            ended_at=timezone.now(),
        )
    assert Membership.objects.for_user(ana.pk).get().status == MembershipStatus.REVOKED.value
