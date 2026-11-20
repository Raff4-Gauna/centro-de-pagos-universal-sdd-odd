"""``GET /api/memberships/``: the members of the active organization (RF-TEN-04, design.md §6).

AC-TEN-34 (Q-218): operator and viewer get ``403`` and no email. AC-TEN-02 (RN-TEN-05): another
organization's members are never listed. Each row carries what the UI may offer on it
(``allowed_actions``, ``assignable_roles``), consistent with the matrix and the role rules.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.tenancy.models import Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.membership_setup import MEMBERSHIPS, member
from tests.tenancy.api.probe import as_member, new_org, revoke

pytestmark = pytest.mark.django_db

CHANGE, REVOKE, LEAVE = "member.change_role", "member.revoke", "member.leave"


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def listed(client: Client, user: Any, organization: Organization, query: str = "") -> Any:
    response = client.get(f"{MEMBERSHIPS}{query}", headers=as_member(user, organization.id))
    assert response.status_code == 200, response.content
    return response.json()


def rows_by_role(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["role"]: row for row in body["results"]}


# --- AC-TEN-34 ---


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_34_viewer_cannot_list(client: Client, org_a: Organization, role: Role) -> None:
    member(org_a, Role.OWNER, "colega")
    user, _ = member(org_a, role)

    response = client.get(MEMBERSHIPS, headers=as_member(user, org_a.id))

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert "@" not in response.content.decode()


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_AC_TEN_34_owner_and_admin_list(client: Client, org_a: Organization, role: Role) -> None:
    user, mine = member(org_a, role)
    other, theirs = member(org_a, Role.VIEWER)

    body = listed(client, user, org_a)

    # The selector orders by (created_at, id). Two rows can share created_at on
    # a coarse clock (Windows), so the expected order follows the same rule
    # instead of assuming creation order.
    expected = sorted([mine, theirs], key=lambda m: (m.created_at, str(m.pk)))
    assert body["count"] == 2
    assert [row["id"] for row in body["results"]] == [str(m.pk) for m in expected]
    by_id = {row["id"]: row for row in body["results"]}
    assert by_id[str(theirs.pk)]["user"] == {"id": str(other.pk), "email": other.email, "name": ""}


# --- AC-TEN-02 ---


def test_AC_TEN_02_other_org_members_are_not_listed(client: Client, org_a: Organization) -> None:
    org_b = new_org("B")
    owner, _ = member(org_a, Role.OWNER)
    stranger, theirs = member(org_b, Role.ADMIN)

    response = client.get(MEMBERSHIPS, headers=as_member(owner, org_a.id))

    assert response.status_code == 200
    text = response.content.decode()
    assert response.json()["count"] == 1
    assert str(theirs.pk) not in text
    assert stranger.email not in text


def test_RF_TEN_04_status_filter(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, gone = member(org_a, Role.ADMIN)
    revoke(org_a, gone)

    active = listed(client, owner, org_a)
    revoked = listed(client, owner, org_a, "?status=revoked")

    assert [row["role"] for row in active["results"]] == ["owner"]
    [row] = revoked["results"]
    assert (row["id"], row["status"], row["ended_reason"]) == (str(gone.pk), "revoked", "revoked")
    assert (row["allowed_actions"], row["assignable_roles"]) == ([], [])
    bad = client.get(f"{MEMBERSHIPS}?status=left", headers=as_member(owner, org_a.id))
    assert bad.status_code == 400
    assert bad.json()["code"] == "validation_error"


def test_RF_TEN_04_list_is_not_cached(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = client.get(MEMBERSHIPS, headers=as_member(owner, org_a.id))

    assert response["Cache-Control"] == "no-store"


# --- allowed_actions / assignable_roles (AC-TEN-13, 15, 16) ---


def test_AC_TEN_15_admin_sees_no_action_on_an_owner(client: Client, org_a: Organization) -> None:
    member(org_a, Role.OWNER)
    admin, _ = member(org_a, Role.ADMIN)
    member(org_a, Role.OPERATOR)

    rows = rows_by_role(listed(client, admin, org_a))

    assert (rows["owner"]["allowed_actions"], rows["owner"]["assignable_roles"]) == ([], [])
    assert rows["operator"]["allowed_actions"] == [CHANGE, REVOKE]
    assert rows["operator"]["assignable_roles"] == ["admin", "viewer"]
    assert rows["admin"]["allowed_actions"] == [CHANGE, LEAVE]  # its own row: demote or leave
    assert rows["admin"]["assignable_roles"] == ["operator", "viewer"]


def test_AC_TEN_13_the_last_owner_has_no_way_out(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    member(org_a, Role.ADMIN)

    rows = rows_by_role(listed(client, owner, org_a))

    assert (rows["owner"]["allowed_actions"], rows["owner"]["assignable_roles"]) == ([], [])
    assert rows["admin"]["allowed_actions"] == [CHANGE, REVOKE]
    assert rows["admin"]["assignable_roles"] == ["owner", "operator", "viewer"]


def test_AC_TEN_27_with_two_owners_one_may_step_down(client: Client, org_a: Organization) -> None:
    owner, mine = member(org_a, Role.OWNER)
    _, theirs = member(org_a, Role.OWNER, "otra-owner")

    rows = {row["id"]: row for row in listed(client, owner, org_a)["results"]}

    assert rows[str(mine.pk)]["allowed_actions"] == [CHANGE, LEAVE]
    assert rows[str(mine.pk)]["assignable_roles"] == ["admin", "operator", "viewer"]
    assert rows[str(theirs.pk)]["allowed_actions"] == [CHANGE, REVOKE]


def test_AC_TEN_28_suspended_lists_without_writes(client: Client) -> None:
    suspended = new_org("S", OrgStatus.SUSPENDED)
    owner, _ = member(suspended, Role.OWNER)
    member(suspended, Role.ADMIN)

    rows = rows_by_role(listed(client, owner, suspended))

    assert rows["admin"]["allowed_actions"] == [REVOKE]  # reduces access (Q-221)
    assert rows["admin"]["assignable_roles"] == []


def test_RF_TEN_04_contract_lists_memberships() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operation = contract["paths"][MEMBERSHIPS]["get"]
    schemas = contract["components"]["schemas"]

    [header] = [p for p in operation["parameters"] if p["in"] == "header"]
    assert (header["name"], header["required"]) == ("X-Organization-Id", True)
    page = operation["responses"]["200"]["content"]["application/json"]["schema"]
    rows = schemas[page["$ref"].rsplit("/", 1)[1]]["properties"]["results"]["items"]
    row = schemas[rows["$ref"].rsplit("/", 1)[1]]
    assert set(row["required"]) == {
        "id",
        "user",
        "role",
        "status",
        "ended_reason",
        "created_at",
        "allowed_actions",
        "assignable_roles",
    }
    assert schemas["MembershipStatusEnum"]["enum"] == ["active", "revoked"]
    assert contract["info"]["version"] == "0.16.0"
