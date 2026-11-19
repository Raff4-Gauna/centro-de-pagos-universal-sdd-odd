"""``services/organizations.py``: edit the active organization (RF-TEN-03, RN-TEN-18, §3.7).

The service validates on its own, for any caller and not only the API's serializer, and writes
under the organization's locks: ``ensure_writable`` (``FOR KEY SHARE``) re-reads the status, so a
suspension that came after the request was resolved wins (AC-TEN-28), and ``lock_organization``
(``FOR NO KEY UPDATE``) puts two edits one after the other. Threads as in
``test_AC_TEN_28_lock_races.py``: the order is forced by waiting on ``pg_stat_activity``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from django.db import transaction
from django.db.transaction import TransactionManagementError
from pytest_django import DjangoAssertNumQueries
from rest_framework.exceptions import ValidationError

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Organization
from apps.tenancy.selectors.organizations import get_organization, lock_organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.organizations import clean_changes, update_organization
from tests.tenancy.locking import PLATFORM, add_member, new_org, set_status, system_ctx, user_ctx
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second, blocks_behind, suspend


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def name_of(organization: Organization) -> str:
    row = Organization.objects.unscoped(PLATFORM).values_list("name", flat=True)
    return str(row.get(pk=organization.pk))


def edit(ctx: TenantContext, **changes: object) -> Organization:
    with tenant_scope(ctx):
        return update_organization(ctx, changes)


def test_RF_TEN_03_clean_changes_normalizes() -> None:
    assert clean_changes(
        {"name": " Acme ", "legal_name": " ", "tax_id": "30-71234567-1", "timezone": "UTC"}
    ) == {"name": "Acme", "legal_name": "", "tax_id": "30712345671", "timezone": "UTC"}
    assert clean_changes({}) == {}


@pytest.mark.parametrize(
    ("changes", "codes"),
    [
        ({"status": "suspended"}, {"status": "unknown_field"}),
        ({"name": None}, {"name": "invalid"}),
        ({"name": 7}, {"name": "invalid"}),
        ({"name": "  "}, {"name": "blank"}),
        ({"name": "x" * 121}, {"name": "max_length"}),
        ({"legal_name": "x" * 201}, {"legal_name": "max_length"}),
        ({"tax_id": "20123456785"}, {"tax_id": "invalid"}),
        ({"timezone": "Mars/Base"}, {"timezone": "invalid"}),
        ({"id": "x", "name": ""}, {"id": "unknown_field", "name": "blank"}),
    ],
)
def test_RF_TEN_03_clean_changes_rejects(changes: dict[str, object], codes: dict[str, str]) -> None:
    with pytest.raises(ValidationError) as raised:
        clean_changes(changes)
    assert raised.value.get_codes() == {field: [code] for field, code in codes.items()}


def test_RF_TEN_09_update_is_the_trigger_of_organization_updated() -> None:
    assert AUDIT_TRIGGERS[TenancyAuditAction.ORGANIZATION_UPDATED] is update_organization


@pytest.mark.django_db
def test_AC_TEN_28_suspended_after_the_resolution_is_not_edited(recorded: RecordingSink) -> None:
    acme = new_org("Acme")
    ctx = user_ctx(add_member(acme, "owner", Role.OWNER))  # resolved while it was active
    set_status(acme, OrgStatus.SUSPENDED)

    with pytest.raises(OrganizationSuspended):
        edit(ctx, name="Otra")
    assert name_of(acme) == "Acme"
    assert recorded.events == []


@pytest.mark.django_db
def test_RF_TEN_03_an_invalid_value_takes_no_lock(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    acme = new_org("Acme")
    ctx = user_ctx(add_member(acme, "owner", Role.OWNER))
    with pytest.raises(ValidationError), django_assert_num_queries(0):
        edit(ctx, name="")


@pytest.mark.django_db
def test_RF_TEN_03_the_event_names_fields_not_values(recorded: RecordingSink) -> None:
    acme = new_org("Acme")
    ctx = user_ctx(add_member(acme, "owner", Role.OWNER))
    edit(ctx, tax_id="20123456786", name="Acme")

    [event] = recorded.events
    assert event.metadata == {"changed_fields": ["tax_id"]}
    assert "20123456786" not in repr(event)


@pytest.mark.django_db
def test_RF_TEN_03_selectors_read_only_the_context_organization() -> None:
    acme, other = new_org("Acme"), new_org("Otra")
    ctx = system_ctx(acme.id)

    assert get_organization(ctx).pk == acme.pk
    assert get_organization(system_ctx(other.id)).pk == other.pk
    with transaction.atomic():
        assert lock_organization(ctx).pk == acme.pk


@pytest.mark.django_db(transaction=True)
def test_RF_TEN_03_the_lock_needs_a_transaction() -> None:
    """Outside one, the row lock would end with its own statement and protect nothing."""
    ctx = system_ctx(new_org("Acme").id)
    with pytest.raises(TransactionManagementError):
        lock_organization(ctx)


@pytest.mark.django_db
def test_RF_TEN_03_a_deleted_organization_is_not_found() -> None:
    ctx = system_ctx(uuid.uuid4())
    with pytest.raises(OrganizationNotFound):
        get_organization(ctx)
    with transaction.atomic(), pytest.raises(OrganizationNotFound):
        lock_organization(ctx)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_28_an_edit_in_flight_commits_before_the_suspension() -> None:
    acme = new_org("Acme")
    ctx = user_ctx(add_member(acme, "owner", Role.OWNER))
    # The first edit holds its locks until released; the second one runs in the same transaction.
    first = Held(lambda: edit(ctx, legal_name="Acme SA"), then=lambda: edit(ctx, name="Antes"))
    second = Second(suspend(acme))

    blocks_behind(first, second)

    assert second.error is None
    assert name_of(acme) == "Antes"
    status = Organization.objects.unscoped(PLATFORM).values_list("status", flat=True)
    assert status.get(pk=acme.pk) == "suspended"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_28_an_edit_after_the_suspension_is_rejected() -> None:
    acme = new_org("Acme")
    ctx = user_ctx(add_member(acme, "owner", Role.OWNER))
    first = Held(suspend(acme))
    second = Second(lambda: edit(ctx, name="Otra"))

    blocks_behind(first, second)

    assert isinstance(second.error, OrganizationSuspended)
    assert name_of(acme) == "Acme"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_TEN_03_two_edits_run_one_after_the_other(recorded: RecordingSink) -> None:
    acme = new_org("Acme")
    owner = user_ctx(add_member(acme, "owner", Role.OWNER))
    admin = user_ctx(add_member(acme, "admin", Role.ADMIN))
    first = Held(lambda: edit(owner, name="Nueva"))
    second = Second(lambda: edit(admin, name="Nueva", legal_name="Nueva SA"))

    blocks_behind(first, second)

    assert second.error is None
    changed = [event.metadata["changed_fields"] for event in recorded.events]
    assert changed == [["name"], ["legal_name"]]  # the second one saw the first one's name
