"""The organization of each request (RF-TEN-01, RN-TEN-03/06/08/20, design.md §3.5).

``ResolveTenant`` end to end on ``ProbeViewSet`` (AC-TEN-03, AC-TEN-04, AC-TEN-06, AC-TEN-33):
the Hub's Bearer, the ``X-Organization-Id`` header and one query for the active membership,
on every request.
RNF-TEN-07 (one query) and RNF-TEN-02 (the denial log) are measured here too. The role and the
suspension (``ActionPermission``) are ``test_action_permission.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator, MutableMapping
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import clear_tenant, current_tenant
from apps.common.tenancy.errors import OrganizationNotFound
from apps.identity.models import User
from apps.tenancy.api.permissions import DENIED_EVENT, ResolveTenant
from apps.tenancy.models import Organization
from apps.tenancy.selectors.resolution import find_active_membership
from tests.tenancy.api.probe import (
    HEADER,
    PROBE,
    URLCONF,
    add_member,
    as_member,
    constant_part,
    new_org,
    new_user,
    revoke,
)

pytestmark = [pytest.mark.django_db, pytest.mark.urls(URLCONF)]


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


@pytest.fixture
def org_b() -> Organization:
    return new_org("B")


@pytest.fixture
def ana(org_a: Organization) -> User:
    """A member of A only."""
    user = new_user("ana")
    add_member(org_a, user, Role.ADMIN)
    return user


@pytest.fixture
def no_tenant_left() -> Iterator[None]:
    """For the tests that call the permission without a request: clear what it activated."""
    yield
    clear_tenant()


def not_found_of_unknown(client: Client, user: User) -> dict[str, Any]:
    response = client.get(PROBE, headers=as_member(user, uuid.uuid4()))
    assert response.status_code == 404
    return constant_part(response)


# --- The happy path ------------------------------------------------------------------------------


def test_RF_TEN_01_member_gets_the_validated_tenant(
    client: Client, ana: User, org_a: Organization
) -> None:
    response = client.get(PROBE, headers=as_member(ana, org_a.id))

    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == str(org_a.id)
    assert body["role"] == Role.ADMIN.value
    assert body["status"] == OrgStatus.ACTIVE.value
    assert body["context_var_is_tenant"] is True
    assert body["logged_organization_id"] == str(org_a.id)  # RNF-TEN-02: the validated one
    assert current_tenant() is None  # the middleware cleared it when the request ended


def test_RN_TEN_08_role_is_read_on_every_request(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    """Two organizations, two roles: each request carries the role of the one it names."""
    user = new_user("bea")
    add_member(org_a, user, Role.VIEWER)
    add_member(org_b, user, Role.OWNER)

    role_in_a = client.get(PROBE, headers=as_member(user, org_a.id)).json()["role"]
    role_in_b = client.get(PROBE, headers=as_member(user, org_b.id)).json()["role"]

    assert (role_in_a, role_in_b) == (Role.VIEWER.value, Role.OWNER.value)


# --- AC-TEN-06: no header ------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
def test_AC_TEN_06_missing_header(client: Client, ana: User, value: str | None) -> None:
    headers = as_member(ana, None)
    if value is not None:
        headers[HEADER] = value

    response = client.get(PROBE, headers=headers)

    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "organization_required"
    assert set(body) == {"type", "title", "status", "code", "detail", "request_id"}  # no data


def test_AC_TEN_06_anonymous_is_401_before_the_header(client: Client) -> None:
    response = client.get(PROBE)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


# --- AC-TEN-03: another organization is the same as none -----------------------------------------


def test_AC_TEN_03_foreign_equals_nonexistent(
    client: Client, ana: User, org_b: Organization
) -> None:
    add_member(org_b, new_user("beto"), Role.OWNER)  # B exists and has members, not Ana
    foreign = client.get(PROBE, headers=as_member(ana, org_b.id))

    assert foreign.status_code == 404
    body = constant_part(foreign)
    assert body["code"] == "organization_not_found"
    assert body["title"] == "Organización no encontrada"
    assert body == not_found_of_unknown(client, ana)
    assert str(org_b.id) not in foreign.content.decode()


@pytest.mark.parametrize("value", ["not-a-uuid", "{1}", "' OR 1=1 --", "x" * 300])
def test_AC_TEN_03_malformed_header_equals_nonexistent(
    client: Client, ana: User, value: str
) -> None:
    headers = as_member(ana, None)
    headers[HEADER] = value

    response = client.get(PROBE, headers=headers)

    assert response.status_code == 404
    assert constant_part(response) == not_found_of_unknown(client, ana)
    assert value not in response.content.decode()  # the input is never echoed


# --- AC-TEN-04: a revoked membership with a live JWT ---------------------------------------------


def test_AC_TEN_04_revoked_membership_with_valid_jwt(client: Client, org_a: Organization) -> None:
    user = new_user("carla")
    membership = add_member(org_a, user, Role.ADMIN)
    headers = as_member(user, org_a.id)
    assert client.get(PROBE, headers=headers).status_code == 200

    revoke(org_a, membership)
    response = client.get(PROBE, headers=headers)  # same Bearer: the session is still live

    assert response.status_code == 404
    assert constant_part(response) == not_found_of_unknown(client, user)


def test_AC_TEN_04_a_new_membership_after_revocation_is_used(
    client: Client, org_a: Organization
) -> None:
    """RN-TEN-21: re-inviting creates a new membership; the resolution reads only the active one."""
    user = new_user("dani")
    revoke(org_a, add_member(org_a, user, Role.ADMIN))
    current = add_member(org_a, user, Role.VIEWER)

    body = client.get(PROBE, headers=as_member(user, org_a.id)).json()

    assert (body["membership_id"], body["role"]) == (str(current.pk), Role.VIEWER.value)


# --- AC-TEN-33: superuser or staff without membership --------------------------------------------


def test_AC_TEN_33_superuser_without_membership(
    client: Client, ana: User, org_b: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``User`` has no such flags (Q-228): set them as if it did; the resolution must not look."""
    operator = new_user("operator")
    add_member(new_org("C"), operator, Role.OWNER)  # a member elsewhere, not of B
    monkeypatch.setattr(User, "is_superuser", True, raising=False)
    monkeypatch.setattr(User, "is_staff", True, raising=False)

    response = client.get(PROBE, headers=as_member(operator, org_b.id))

    assert response.status_code == 404
    assert constant_part(response) == not_found_of_unknown(client, ana)


# --- Fail closed on a row the constraints should have stopped ------------------------------------


@pytest.mark.parametrize(
    ("constraint", "table", "column"),
    [
        ("membership_role_valid", "tenancy_membership", "role"),
        ("org_status_valid", "tenancy_organization", "status"),
    ],
)
def test_RN_TEN_03_unknown_role_or_status_is_not_found(
    client: Client, ana: User, org_a: Organization, constraint: str, table: str, column: str
) -> None:
    """``Role(row.role)`` and ``OrgStatus``: a value outside the enum never becomes a context."""
    with connection.cursor() as cursor:  # rolled back with the test's transaction
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # fire the deferred FK checks first
        cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
        cursor.execute(f"UPDATE {table} SET {column} = 'root'")  # noqa: S608

    with capture_logs() as logs:
        response = client.get(PROBE, headers=as_member(ana, org_a.id))

    assert response.status_code == 404
    assert constant_part(response) == not_found_of_unknown(client, ana)
    assert "tenancy.resolution_invalid_row" in [entry["event"] for entry in logs]


# --- RNF-TEN-07: one query, whatever the number of memberships -----------------------------------


@pytest.mark.parametrize("other_organizations", [0, 5])
def test_RNF_TEN_07_one_query_per_request(
    org_a: Organization,
    other_organizations: int,
    django_assert_num_queries: Any,
    no_tenant_left: None,
) -> None:
    user = new_user("eva")
    add_member(org_a, user, Role.OPERATOR)
    for index in range(other_organizations):
        add_member(new_org(f"other-{index}"), user, Role.OWNER)
    request = Request(APIRequestFactory().get(PROBE, headers={HEADER: str(org_a.id)}))
    request.user = user

    with django_assert_num_queries(1):
        assert ResolveTenant().has_permission(request, view=None)  # type: ignore[arg-type]

    assert current_tenant() is not None
    assert current_tenant() is request.tenant  # type: ignore[attr-defined]


def test_RNF_TEN_07_selector_reads_only_the_active_membership(
    org_a: Organization, org_b: Organization
) -> None:
    user = new_user("fede")
    membership = add_member(org_a, user, Role.OWNER)
    add_member(org_b, user, Role.VIEWER)

    found = find_active_membership(user_id=user.pk, organization_id=org_a.id)

    assert found is not None
    assert (found.membership_id, found.role) == (membership.pk, Role.OWNER)
    assert found.organization_status is OrgStatus.ACTIVE
    assert find_active_membership(user_id=user.pk, organization_id=uuid.uuid4()) is None


# --- RNF-TEN-02: every denial is logged, with what was asked -------------------------------------


def denials(logs: Iterable[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == DENIED_EVENT]


@pytest.mark.parametrize(
    ("value", "reason", "logged_id"),
    [
        (None, "organization_header_missing", False),
        ("not-a-uuid", "organization_header_malformed", False),
        ("foreign", "no_active_membership", True),
    ],
)
def test_RNF_TEN_02_denial_is_logged(
    client: Client,
    ana: User,
    org_b: Organization,
    value: str | None,
    reason: str,
    logged_id: bool,
) -> None:
    headers = as_member(ana, None)
    if value is not None:
        headers[HEADER] = str(org_b.id) if value == "foreign" else value

    with capture_logs(processors=[merge_contextvars]) as logs:
        response = client.get(PROBE, headers=headers)

    (denial,) = denials(logs)
    assert denial["log_level"] == "warning"
    assert denial["reason"] == reason
    assert denial["user_id"] == str(ana.pk)
    assert denial["request_id"] == response.json()["request_id"]
    assert denial["requested_organization_id"] == (str(org_b.id) if logged_id else None)
    assert "organization_id" not in denial  # only a validated organization is bound (C-16)
    assert "not-a-uuid" not in str(logs)  # the raw header never reaches a log


def test_RNF_TEN_02_permission_raises_the_constant_error(
    ana: User, org_b: Organization, no_tenant_left: None
) -> None:
    request = Request(APIRequestFactory().get(PROBE, headers={HEADER: str(org_b.id)}))
    request.user = ana

    with pytest.raises(OrganizationNotFound):
        ResolveTenant().has_permission(request, view=None)  # type: ignore[arg-type]

    assert current_tenant() is None
    assert not hasattr(request, "tenant")
