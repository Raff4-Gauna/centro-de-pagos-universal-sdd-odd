"""``Integration``: the constraints and indexes of design.md §5 (T-INT-01).

The constraints are the final net even if a service fails (ADR-0002 §2), so they are tested on the
model, without services: the name collides without case among the active integrations of one
organization (RN-INT-01, Q-426); the account ``(provider_code, environment, account_id)`` is
reserved across organizations while the integration is not disconnected (RN-INT-19, Q-403, Q-423);
the webhook route key is unique in the whole platform (RN-INT-27); the connection status, its
``reason``, the activity status and its dates, and the unconfirmed-account mark stay coherent
(RN-INT-19, RN-INT-21, Q-430). The service tests cover the ``409`` and what the connection test
decides.
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
from apps.integrations.models import Integration
from apps.tenancy.models import Organization
from tests.tenancy.locking import PLATFORM, new_org, system_ctx

pytestmark = pytest.mark.django_db

NOW = timezone.now()
INACTIVE: dict[str, Any] = {"status": "inactive", "deactivated_at": NOW}
DISCONNECTED: dict[str, Any] = {
    "status": "disconnected",
    "deactivated_at": NOW,
    "disconnected_at": NOW,
}
CONNECTED_X: dict[str, Any] = {"connection_status": "connected", "account_id": "X"}


def creator() -> User:
    suffix = uuid.uuid4().hex[:12]
    return User.objects.create_user(google_sub=f"sub-{suffix}", email=f"{suffix}@hub.test")


def insert(organization: Organization, name: str = "Cuenta 1", **fields: Any) -> Integration:
    values: dict[str, Any] = {
        "provider_code": "fake",
        "environment": "test",
        "created_by": creator(),
        **fields,
    }
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx), transaction.atomic():
        return Integration.objects.for_tenant(ctx).create(name=name, **values)


def constraint_of(error: pytest.ExceptionInfo[IntegrityError]) -> str:
    return str(error.value.__cause__.diag.constraint_name)  # type: ignore[union-attr]


def db_constraints() -> dict[str, dict[str, Any]]:
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, Integration._meta.db_table)


# --- RN-INT-01: name (AC-INT-28) ---


@pytest.mark.parametrize("name", ["Cuenta 1", "cuenta 1", "CUENTA 1"])
def test_AC_INT_28_active_name_unique_case_insensitive_constraint(name: str) -> None:
    org_a, org_b = new_org("A"), new_org("B")
    insert(org_a, "Cuenta 1", **CONNECTED_X)
    insert(org_a, "Cuenta 2", connection_status="connected", account_id="Y")
    insert(org_b, "Cuenta 1")  # another organization never collides

    with pytest.raises(IntegrityError) as raised:
        insert(org_a, name)

    assert constraint_of(raised) == "integration_unique_active_name"
    assert Integration.objects.unscoped(PLATFORM).filter(organization=org_a).count() == 2


def test_AC_INT_28_inactive_name_does_not_block() -> None:
    organization = new_org("A")
    first = insert(organization, "Cuenta 1", **INACTIVE)
    insert(organization, "Cuenta 9", **DISCONNECTED)

    insert(organization, "cuenta 1")
    insert(organization, "Cuenta 9")

    ctx = system_ctx(organization.id)
    first.status, first.deactivated_at = "active", None
    with tenant_scope(ctx), pytest.raises(IntegrityError) as raised, transaction.atomic():
        first.save()
    assert constraint_of(raised) == "integration_unique_active_name"
    assert Integration.objects.unscoped(PLATFORM).get(pk=first.pk).status == "inactive"


# --- RN-INT-19: the account is reserved across organizations (AC-INT-29, AC-INT-38) ---


@pytest.mark.parametrize("held", [{}, INACTIVE], ids=["active", "inactive"])
@pytest.mark.parametrize("same_org", [False, True], ids=["other-org", "same-org"])
def test_AC_INT_29_account_reserved_across_organizations(
    held: dict[str, Any], same_org: bool
) -> None:
    org_a, org_b = new_org("A"), new_org("B")
    insert(org_b if not same_org else org_a, "Cuenta B", **CONNECTED_X, **held)

    with pytest.raises(IntegrityError) as raised:
        insert(org_a, "Cuenta A", **CONNECTED_X)

    assert constraint_of(raised) == "integration_account_reserved"
    # An unconfirmed account (Q-430) or one with a failed last check still holds the reservation.
    with pytest.raises(IntegrityError) as raised:
        insert(
            org_a,
            "Cuenta A",
            account_id="X",
            connection_status="connection_error",
            connection_reason="provider_unreachable",
            account_unconfirmed=True,
        )
    assert constraint_of(raised) == "integration_account_reserved"


@pytest.mark.parametrize(
    "fields",
    [
        {"environment": "production", **CONNECTED_X},
        {"provider_code": "other", **CONNECTED_X},
        {"connection_status": "unverified", "account_id": None},  # unknown account reserves nothing
    ],
    ids=["production", "other-provider", "unknown-account"],
)
def test_AC_INT_29_other_environment_is_free(fields: dict[str, Any]) -> None:
    insert(new_org("B"), "Cuenta B", **CONNECTED_X)
    insert(new_org("B2"), "Sin cuenta")

    created = insert(new_org("A"), "Cuenta A", **fields)

    assert Integration.objects.unscoped(PLATFORM).filter(pk=created.pk).exists()


def test_AC_INT_38_disconnected_does_not_reserve_account() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    held = insert(org_b, "Cuenta B", **CONNECTED_X)

    ctx = system_ctx(org_b.id)
    held.status, held.deactivated_at, held.disconnected_at = "disconnected", NOW, NOW
    held.connection_status = "unverified"
    with tenant_scope(ctx), transaction.atomic():
        held.save()

    created = insert(org_a, "Cuenta A", **CONNECTED_X)

    # The disconnected one keeps its account id (Q-427), without reserving it.
    stored = Integration.objects.unscoped(PLATFORM).get(pk=held.pk)
    assert (stored.account_id, created.account_id) == ("X", "X")


# --- RN-INT-27: the webhook route key (AC-INT-41) ---


def test_AC_INT_41_webhook_route_key_unique() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    first, second = insert(org_a, "Uno"), insert(org_a, "Dos")

    assert first.webhook_route_key != second.webhook_route_key
    assert len(first.webhook_route_key) >= 43  # token_urlsafe(32): 256 bits, not guessable

    with pytest.raises(IntegrityError) as raised:
        insert(org_b, "Uno", webhook_route_key=first.webhook_route_key)
    assert constraint_of(raised) == "integration_webhook_route_key_uniq"


def test_RN_INT_27_str_and_repr_carry_only_the_pk() -> None:
    integration = insert(new_org("A"), "Cuenta secreta", **CONNECTED_X)

    for text in (str(integration), repr(integration)):
        assert str(integration.pk) in text
        assert integration.webhook_route_key not in text
        assert "Cuenta secreta" not in text


# --- RN-INT-21: connection status, reason, activity status and its dates ---


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        (
            {"connection_status": "unverified", "connection_reason": "provider_unreachable"},
            "integration_reason_coherent",
        ),
        (
            {**CONNECTED_X, "connection_reason": "provider_unreachable"},
            "integration_reason_coherent",
        ),
        ({"connection_status": "connection_error"}, "integration_reason_coherent"),
        ({"connection_status": "credentials_invalid"}, "integration_reason_coherent"),
        ({"connection_status": "connected"}, "integration_connected_has_account"),
        (
            {"connection_status": "expired", "connection_reason": "auth_invalid"},
            "integration_connection_status_valid",
        ),
        ({"status": "archived", "deactivated_at": NOW}, "integration_status_valid"),
        ({"environment": "staging"}, "integration_environment_valid"),
        ({"name": ""}, "integration_name_not_blank"),
        ({"account_id": ""}, "integration_account_not_blank"),
        ({"status": "inactive"}, "integration_active_coherent"),
        ({"deactivated_at": NOW}, "integration_active_coherent"),
        ({"status": "disconnected", "deactivated_at": NOW}, "integration_disconnected_coherent"),
        ({**INACTIVE, "disconnected_at": NOW}, "integration_disconnected_coherent"),
        (
            {
                **DISCONNECTED,
                "connection_status": "connection_error",
                "connection_reason": "provider_unreachable",
            },
            "integration_disconnected_coherent",
        ),
    ],
)
def test_RN_INT_21_reason_and_status_coherent(fields: dict[str, Any], constraint: str) -> None:
    organization = new_org("A")

    with pytest.raises(IntegrityError) as raised:
        insert(organization, **fields)

    assert constraint_of(raised) == constraint


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {**CONNECTED_X},
        {"connection_status": "connection_error", "connection_reason": "provider_unreachable"},
        {
            "account_id": "X",
            "connection_status": "credentials_invalid",
            "connection_reason": "auth_invalid",
            **INACTIVE,
        },
        {**DISCONNECTED, "account_id": "X"},
    ],
    ids=["new", "connected", "unreachable", "invalid-inactive", "disconnected-keeps-account"],
)
def test_RN_INT_21_coherent_rows_are_accepted(fields: dict[str, Any]) -> None:
    created = insert(new_org("A"), **fields)

    assert Integration.objects.unscoped(PLATFORM).filter(pk=created.pk).exists()


# --- RN-INT-19 / Q-430: unconfirmed account ---


@pytest.mark.parametrize(
    "fields",
    [
        {"connection_status": "connection_error", "connection_reason": "provider_unreachable"},
        {**CONNECTED_X},
        {**DISCONNECTED, "account_id": "X"},
    ],
    ids=["no-account", "connected", "disconnected"],
)
def test_RN_INT_19_unconfirmed_coherent(fields: dict[str, Any]) -> None:
    organization = new_org("A")

    with pytest.raises(IntegrityError) as raised:
        insert(organization, account_unconfirmed=True, **fields)
    assert constraint_of(raised) == "integration_unconfirmed_coherent"

    unconfirmed = {"connection_status": "connection_error", "connection_reason": "other_account"}
    insert(organization, "Sin confirmar", account_id="X", account_unconfirmed=True, **unconfirmed)
    insert(
        organization,
        "Inactiva",
        account_id="Y",
        account_unconfirmed=True,
        **unconfirmed,
        **INACTIVE,
    )


# --- Defaults, tenant base and the composite-key target ---


def test_RN_INT_21_defaults_of_a_new_integration() -> None:
    created = insert(new_org("A"))
    stored = Integration.objects.unscoped(PLATFORM).get(pk=created.pk)

    assert (stored.status, stored.connection_status) == ("active", "unverified")
    assert stored.connection_reason is None
    assert stored.account_id is None
    assert stored.account_unconfirmed is False
    assert stored.configuration == {}
    assert (stored.deactivated_at, stored.disconnected_at, stored.connection_checked_at) == (
        None,
        None,
        None,
    )


def test_RN_INT_13_org_id_pair_is_a_unique_target_and_listing_index() -> None:
    constraints = db_constraints()

    target = constraints["integration_org_id_uniq"]
    assert target["unique"] is True
    assert target["columns"] == ["organization_id", "id"]
    listing = constraints["integration_org_status_name"]
    assert listing["index"] is True
    assert listing["columns"] == ["organization_id", "status", "name"]


def test_AC_TEN_11_integrations_fail_closed_and_are_never_deleted() -> None:
    organization = new_org("A")
    integration = insert(organization)

    with pytest.raises(TenantScopeError):
        list(Integration.objects.all())
    with tenant_scope(system_ctx(organization.id)), pytest.raises(HardDeleteForbidden):
        integration.delete()
    with pytest.raises(HardDeleteForbidden):
        Integration.objects.for_tenant(system_ctx(organization.id)).delete()
    assert Integration.objects.unscoped(PLATFORM).filter(pk=integration.pk).exists()


def test_RN_INT_01_save_never_writes_another_organization() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    integration = insert(org_a)

    integration.name = "Otra"
    with tenant_scope(system_ctx(org_b.id)), pytest.raises(TenantScopeError):
        integration.save()
    assert Integration.objects.unscoped(PLATFORM).get(pk=integration.pk).name == "Cuenta 1"
