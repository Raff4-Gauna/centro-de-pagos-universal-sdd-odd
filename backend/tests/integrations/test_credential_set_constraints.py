"""``CredentialSet``: the constraints of design.md §5 and its composite key (T-INT-02).

Tested on the model, without services (ADR-0002 §2): one set per integration (RN-INT-06); the
``(organization_id, integration_id)`` pair must name an integration of the same organization, also
for a row written by raw SQL that skips the ORM (RN-INT-13, design.md §5.1); the envelope columns
of ADR-0003 §3 (``key_id``, ``format_version``, ``ciphertext`` of at least nonce + tag) are checked
by the database. Nothing here encrypts: the bytes are synthetic (T-INT-05 owns the cipher).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import TenantScopeError
from apps.identity.models import User
from apps.integrations.models import CredentialSet, Integration
from apps.tenancy.models import Organization
from tests.tenancy.locking import PLATFORM, new_org, system_ctx

pytestmark = pytest.mark.django_db

# 12-byte nonce + 16-byte tag + 4 bytes of synthetic "ciphertext": never a real credential.
CIPHERTEXT = b"\x00" * 12 + b"fake" + b"\x01" * 16
MIN_CIPHERTEXT = 28


def new_user() -> User:
    suffix = uuid.uuid4().hex[:12]
    return User.objects.create_user(google_sub=f"sub-{suffix}", email=f"{suffix}@hub.test")


def new_integration(organization: Organization, name: str = "Cuenta 1") -> Integration:
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx), transaction.atomic():
        return Integration.objects.for_tenant(ctx).create(
            provider_code="fake", name=name, environment="test", created_by=new_user()
        )


def insert(integration: Integration, **fields: Any) -> CredentialSet:
    values: dict[str, Any] = {
        "version": 1,
        "key_id": "k1",
        "format_version": 1,
        "ciphertext": CIPHERTEXT,
        "public_fields": {"public_key": "fake-public-1"},
        "secret_field_names": ["access_token"],
        "credentials_updated_at": timezone.now(),
        "updated_by": new_user(),
        **fields,
    }
    ctx = system_ctx(integration.organization_id)
    with tenant_scope(ctx), transaction.atomic():
        return CredentialSet.objects.for_tenant(ctx).create(integration=integration, **values)


def constraint_of(error: pytest.ExceptionInfo[IntegrityError]) -> str:
    return str(error.value.__cause__.diag.constraint_name)  # type: ignore[union-attr]


def raw_insert(organization_id: uuid.UUID, integration_id: uuid.UUID) -> None:
    """A row written without the ORM: only the database stands between it and another tenant."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO integrations_credentialset (id, organization_id, integration_id, version,"
            " key_id, format_version, ciphertext, public_fields, secret_field_names,"
            " credentials_updated_at, updated_by_id, created_at)"
            " VALUES (%s, %s, %s, 1, 'k1', 1, %s, '{}', '[]', now(), %s, now())",
            [uuid.uuid4(), organization_id, integration_id, CIPHERTEXT, new_user().pk],
        )


# --- RN-INT-13: the composite key ---


def test_RN_INT_13_credentialset_mixing_organizations_is_rejected() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    of_b = new_integration(org_b)

    with pytest.raises(IntegrityError) as raised:
        raw_insert(org_a.id, of_b.id)

    assert constraint_of(raised) == "credentialset_integration_same_org"
    assert CredentialSet.objects.unscoped(PLATFORM).count() == 0
    raw_insert(org_b.id, of_b.id)  # the same row with its own organization is accepted
    assert CredentialSet.objects.unscoped(PLATFORM).filter(integration=of_b).count() == 1


def test_RN_INT_13_orm_never_writes_a_set_for_another_organization() -> None:
    org_a, org_b = new_org("A"), new_org("B")
    of_b = new_integration(org_b)

    ctx = system_ctx(org_a.id)
    with tenant_scope(ctx), pytest.raises(IntegrityError) as raised, transaction.atomic():
        CredentialSet.objects.for_tenant(ctx).create(
            integration=of_b,
            version=1,
            key_id="k1",
            format_version=1,
            ciphertext=CIPHERTEXT,
            credentials_updated_at=timezone.now(),
            updated_by=new_user(),
        )
    assert constraint_of(raised) == "credentialset_integration_same_org"


# --- RN-INT-06: one set per integration ---


def test_RN_INT_06_one_set_per_integration() -> None:
    organization = new_org("A")
    first, second = new_integration(organization, "Uno"), new_integration(organization, "Dos")
    insert(first)
    insert(second)

    with pytest.raises(IntegrityError) as raised:
        insert(first, version=2, key_id="k2")

    assert constraint_of(raised) == "credentialset_one_per_integration"
    assert CredentialSet.objects.unscoped(PLATFORM).filter(integration=first).count() == 1


def test_RN_INT_06_a_set_is_deleted_with_its_tenant() -> None:
    """Disconnecting deletes the set (RN-INT-24): no ``NoHardDeleteMixin``, but only its own."""
    org_a, org_b = new_org("A"), new_org("B")
    stored = insert(new_integration(org_a))

    with tenant_scope(system_ctx(org_b.id)), pytest.raises(TenantScopeError):
        stored.delete()
    with tenant_scope(system_ctx(org_a.id)), transaction.atomic():
        stored.delete()
    assert not CredentialSet.objects.unscoped(PLATFORM).exists()


# --- ADR-0003 §3: the envelope columns ---


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"version": 0}, "credentialset_version_positive"),
        ({"version": -1}, "credentialset_version_positive"),
        ({"format_version": 2}, "credentialset_format_v1"),
        ({"format_version": 0}, "credentialset_format_v1"),
        ({"key_id": ""}, "credentialset_key_id_valid"),
        ({"key_id": "K1"}, "credentialset_key_id_valid"),
        ({"key_id": "key_1"}, "credentialset_key_id_valid"),
        ({"ciphertext": b""}, "credentialset_ciphertext_min"),
        ({"ciphertext": b"\x00" * (MIN_CIPHERTEXT - 1)}, "credentialset_ciphertext_min"),
    ],
)
def test_RN_INT_04_envelope_checks(fields: dict[str, Any], constraint: str) -> None:
    integration = new_integration(new_org("A"))

    with pytest.raises(IntegrityError) as raised:
        insert(integration, **fields)

    assert constraint_of(raised) == constraint


@pytest.mark.parametrize(
    "fields",
    [
        {"key_id": "k" * 32},
        {"key_id": "2026-11-rotation"},
        {"ciphertext": b"\x00" * MIN_CIPHERTEXT},
        {"version": 7, "public_fields": {}, "secret_field_names": []},
    ],
    ids=["key-id-32", "key-id-dashes", "ciphertext-28", "empty-public"],
)
def test_RN_INT_04_valid_envelopes_are_accepted(fields: dict[str, Any]) -> None:
    stored = insert(new_integration(new_org("A")), **fields)

    assert CredentialSet.objects.unscoped(PLATFORM).filter(pk=stored.pk).exists()


def test_RN_INT_04_credentialset_repr_has_no_data() -> None:
    stored = insert(new_integration(new_org("A")), key_id="k-repr")

    for text in (str(stored), repr(stored)):
        assert str(stored.pk) in text
        for value in (
            "k-repr",
            "fake-public-1",
            "access_token",
            "fake",
            str(stored.integration_id),
        ):
            assert value not in text


def test_RN_INT_06_defaults_and_rotation_index() -> None:
    integration = new_integration(new_org("A"))
    ctx = system_ctx(integration.organization_id)
    with tenant_scope(ctx), transaction.atomic():
        created = CredentialSet.objects.for_tenant(ctx).create(
            integration=integration,
            version=1,
            key_id="k1",
            format_version=1,
            ciphertext=CIPHERTEXT,
            credentials_updated_at=timezone.now(),
            updated_by=new_user(),
        )
    stored = CredentialSet.objects.unscoped(PLATFORM).get(pk=created.pk)
    assert (stored.public_fields, stored.secret_field_names) == ({}, [])
    assert stored.reencrypted_at is None
    assert bytes(stored.ciphertext) == CIPHERTEXT

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, CredentialSet._meta.db_table)
    assert constraints["credentialset_key_id"]["columns"] == ["key_id"]
    assert constraints["credentialset_key_id"]["index"] is True


def test_AC_TEN_11_credential_sets_fail_closed() -> None:
    insert(new_integration(new_org("A")))

    with pytest.raises(TenantScopeError):
        list(CredentialSet.objects.all())
