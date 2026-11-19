"""``Branch``: the constraints of design.md §5 and the service that creates one (RF-TEN-06).

The constraints are the final net even if a service fails (ADR-0002 §2), so they are tested on the
model, without the service: a name collides without case among active branches (Q-226), an informed
code collides exactly among active ones (Q-227), an inactive branch frees both (AC-TEN-38), and
``(organization_id, id)`` is unique, the target of SPEC-04/05's composite keys (RN-TEN-15). The
service tests cover what only the service decides: the conflict as ``409``, the lock and the audit.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationSuspended
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantScopeError
from apps.tenancy.api.serializers.branches import BranchCreateSerializer
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Branch, Organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.branches import CREATE_FIELDS, BranchConflict, create_branch
from tests.tenancy.locking import PLATFORM, add_member, new_org, set_status, system_ctx, user_ctx

pytestmark = pytest.mark.django_db


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def insert(organization: Organization, name: str, code: str = "", *, active: bool = True) -> Branch:
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx), transaction.atomic():
        return Branch.objects.for_tenant(ctx).create(name=name, code=code, is_active=active)


def constraint_of(error: pytest.ExceptionInfo[IntegrityError]) -> str:
    return str(error.value.__cause__.diag.constraint_name)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("name", "code", "constraint"),
    [
        ("centro", "", "branch_unique_active_name"),
        ("CENTRO", "", "branch_unique_active_name"),
        ("Sur", "C01", "branch_unique_active_code"),
    ],
)
def test_AC_TEN_38_constraints_reject_among_active(name: str, code: str, constraint: str) -> None:
    organization = new_org("A")
    insert(organization, "Centro", "C01")

    with pytest.raises(IntegrityError) as raised:
        insert(organization, name, code)

    assert constraint_of(raised) == constraint


def test_AC_TEN_38_constraints_free_inactive_and_other_org() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    insert(org_a, "Centro", "C01", active=False)

    insert(org_a, "centro", "C01")
    insert(org_a, "Sur", "c01")
    insert(org_a, "Este")
    insert(org_a, "Oeste")  # two empty codes never collide (Q-227)
    insert(org_b, "Centro", "C01")

    assert Branch.objects.unscoped(PLATFORM).count() == 6


def test_RN_TEN_19_name_not_blank_and_no_hard_delete() -> None:
    organization = new_org("A")
    with pytest.raises(IntegrityError) as raised:
        insert(organization, "")
    assert raised.value.__cause__.diag.constraint_name == "branch_name_not_blank"  # type: ignore[union-attr]

    branch = insert(organization, "Centro")
    with tenant_scope(system_ctx(organization.id)), pytest.raises(HardDeleteForbidden):
        branch.delete()
    with pytest.raises(HardDeleteForbidden):
        Branch.objects.for_tenant(system_ctx(organization.id)).delete()
    assert Branch.objects.unscoped(PLATFORM).filter(pk=branch.pk).exists()


def test_RN_TEN_15_org_id_pair_is_a_unique_target() -> None:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Branch._meta.db_table)

    target = constraints["branch_org_id_uniq"]
    assert target["unique"] is True
    assert target["columns"] == ["organization_id", "id"]


def test_AC_TEN_11_branches_fail_closed() -> None:
    insert(new_org("A"), "Centro")

    with pytest.raises(TenantScopeError):
        list(Branch.objects.all())


# --- services/branches.py ---


def create(ctx: TenantContext, **fields: object) -> Branch:
    with tenant_scope(ctx):
        return create_branch(ctx, fields)


def test_AC_TEN_38_service_turns_the_constraint_into_conflict(recorded: RecordingSink) -> None:
    organization = new_org("A")
    ctx = user_ctx(add_member(organization, "admin", Role.ADMIN))
    create(ctx, name="Centro", code="C01")
    recorded.clear()

    with transaction.atomic():  # the savepoint leaves the transaction usable
        with pytest.raises(BranchConflict) as raised:
            create(ctx, name="centro")
        assert Branch.objects.unscoped(PLATFORM).count() == 1

    assert raised.value.get_codes() == "conflict"
    assert recorded.events == []


def test_AC_TEN_28_service_rechecks_the_status(recorded: RecordingSink) -> None:
    """The resolution read ``active``; the operator suspended it before the write."""
    organization = new_org("A")
    ctx = user_ctx(add_member(organization, "owner", Role.OWNER), OrgStatus.ACTIVE)
    set_status(organization, OrgStatus.SUSPENDED)

    with pytest.raises(OrganizationSuspended):
        create(ctx, name="Centro")

    assert Branch.objects.unscoped(PLATFORM).count() == 0
    assert recorded.events == []


def test_RN_TEN_04_service_writes_in_the_context_org(recorded: RecordingSink) -> None:
    org_a = new_org("A")
    owner = add_member(org_a, "owner", Role.OWNER)

    branch = create(user_ctx(owner), name="Centro")

    assert branch.organization_id == org_a.id
    [event] = recorded.events
    assert (event.action, event.organization_id) == (TenancyAuditAction.BRANCH_CREATED, org_a.id)
    assert AUDIT_TRIGGERS[TenancyAuditAction.BRANCH_CREATED] is create_branch


def test_RN_TEN_04_service_never_takes_the_organization() -> None:
    ctx = system_ctx(new_org("A").id)
    with pytest.raises(ValidationError) as raised:
        create(ctx, name="Centro", organization_id=uuid.uuid4())

    assert raised.value.get_codes() == {"organization_id": ["unknown_field"]}
    assert Branch.objects.unscoped(PLATFORM).count() == 0


def test_RF_TEN_06_schema_follows_the_service() -> None:
    fields = BranchCreateSerializer().fields

    assert set(fields) == set(CREATE_FIELDS)
    limits = {
        name: field.max_length for name, field in fields.items() if isinstance(field, CharField)
    }
    assert limits == dict(CREATE_FIELDS)
    assert [name for name, field in fields.items() if field.required] == ["name"]
