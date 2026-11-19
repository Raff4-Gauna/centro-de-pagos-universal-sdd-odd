"""``GET``/``POST /api/branches/``: list and create the branches of the active organization.

RF-TEN-06, design.md §6. AC-TEN-07: the organization of a new branch is the active one, never one
named in the body (``organization_id`` → ``400 unknown_field`` and nothing anywhere). AC-TEN-16:
operator and viewer list but do not create. AC-TEN-30: an inactive branch is listed, marked, and
there is no route to delete one. AC-TEN-38 (Q-226, Q-227): a name (without case) or a code taken
by an active branch of the same organization is ``409 conflict``; an inactive one frees both, and
another organization may always use them.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.test import Client
from django.utils import timezone

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import tenant_scope
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Branch, Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import (
    PLATFORM,
    add_member,
    as_member,
    new_org,
    new_user,
    platform_ctx,
)

pytestmark = pytest.mark.django_db

BRANCHES = "/api/branches/"


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


@pytest.fixture
def org_b() -> Organization:
    return new_org("B")


def member(organization: Organization, role: Role) -> User:
    user = new_user(f"{role.value}-{organization.name}")
    add_member(organization, user, role)
    return user


def seed(organization: Organization, name: str, code: str = "", *, active: bool = True) -> Branch:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        deactivated_at = None if active else timezone.now()
        return Branch.objects.for_tenant(ctx).create(
            name=name, code=code, is_active=active, deactivated_at=deactivated_at
        )


def names_in(organization: Organization) -> list[tuple[str, str, bool]]:
    rows = Branch.objects.unscoped(PLATFORM).filter(organization_id=organization.id)
    return sorted(rows.values_list("name", "code", "is_active"))


def post(client: Client, user: User, organization: Organization, body: Any) -> Any:
    return client.post(
        BRANCHES,
        data=json.dumps(body),
        content_type="application/json",
        headers=as_member(user, organization.id),
    )


def listed(client: Client, user: User, organization: Organization, query: str = "") -> Any:
    response = client.get(f"{BRANCHES}{query}", headers=as_member(user, organization.id))
    assert response.status_code == 200, response.content
    return response.json()


def codes_of(response: Any) -> dict[str, str]:
    return {error["field"]: error["code"] for error in response.json()["errors"]}


# --- AC-TEN-07 ---


def test_AC_TEN_07_org_in_body_creates_nothing_in_b(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    admin = member(org_a, Role.ADMIN)

    response = post(client, admin, org_a, {"name": "Centro", "organization_id": str(org_b.id)})

    assert response.status_code == 400
    assert codes_of(response) == {"organization_id": "unknown_field"}
    assert names_in(org_b) == []
    assert names_in(org_a) == []


@pytest.mark.parametrize("key", ["organization", "id", "is_active", "deactivated_at", "nme"])
def test_AC_TEN_07_any_other_key_is_rejected(client: Client, org_a: Organization, key: str) -> None:
    response = post(client, member(org_a, Role.OWNER), org_a, {"name": "Centro", key: "x"})

    assert response.status_code == 400
    assert codes_of(response) == {key: "unknown_field"}
    assert names_in(org_a) == []


def test_AC_TEN_07_created_in_the_active_org_only(
    client: Client, org_a: Organization, org_b: Organization, recorded: RecordingSink
) -> None:
    owner = member(org_a, Role.OWNER)

    response = post(client, owner, org_a, {"name": "  Centro ", "code": " C01 ", "address": " "})

    assert response.status_code == 201
    body = response.json()
    branch = Branch.objects.unscoped(PLATFORM).get(pk=body["id"])
    assert branch.organization_id == org_a.id
    assert body == {
        "id": str(branch.pk),
        "name": "Centro",
        "code": "C01",
        "address": "",
        "is_active": True,
        "deactivated_at": None,
    }
    assert names_in(org_b) == []
    [event] = recorded.events
    assert event.action == TenancyAuditAction.BRANCH_CREATED
    assert event.organization_id == org_a.id
    assert event.actor.id == owner.pk
    assert event.metadata == {"branch_id": str(branch.pk)}


# --- AC-TEN-16 ---


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_16_viewer_cannot_create_branch(
    client: Client, org_a: Organization, role: Role, recorded: RecordingSink
) -> None:
    user = member(org_a, role)

    response = post(client, user, org_a, {"name": "Centro"})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert names_in(org_a) == []
    assert recorded.events == []
    assert listed(client, user, org_a)["count"] == 0  # reading is still theirs


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_AC_TEN_16_owner_and_admin_create(client: Client, org_a: Organization, role: Role) -> None:
    response = post(client, member(org_a, role), org_a, {"name": "Centro"})

    assert response.status_code == 201
    assert names_in(org_a) == [("Centro", "", True)]


def test_AC_TEN_28_suspended_lists_but_does_not_create(client: Client) -> None:
    suspended = new_org("S", OrgStatus.SUSPENDED)
    seed(suspended, "Centro")
    owner = member(suspended, Role.OWNER)

    response = post(client, owner, suspended, {"name": "Norte"})

    assert response.status_code == 409
    assert response.json()["code"] == "organization_suspended"
    assert [b["name"] for b in listed(client, owner, suspended)["results"]] == ["Centro"]


# --- AC-TEN-30 ---


def test_AC_TEN_30_inactive_listed(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    seed(org_a, "Norte", active=False)
    seed(org_a, "Centro", "C01")
    seed(org_b, "Otra de B")
    viewer = member(org_a, Role.VIEWER)

    body = listed(client, viewer, org_a)

    assert (body["count"], body["next"], body["previous"]) == (2, None, None)
    assert [(b["name"], b["code"], b["is_active"]) for b in body["results"]] == [
        ("Centro", "C01", True),
        ("Norte", "", False),
    ]
    assert [b["name"] for b in listed(client, viewer, org_a, "?is_active=true")["results"]] == [
        "Centro"
    ]
    assert [b["name"] for b in listed(client, viewer, org_a, "?is_active=false")["results"]] == [
        "Norte"
    ]


def test_AC_TEN_30_is_active_filter_is_validated(client: Client, org_a: Organization) -> None:
    response = client.get(
        f"{BRANCHES}?is_active=yes", headers=as_member(member(org_a, Role.OWNER), org_a.id)
    )

    assert response.status_code == 400
    assert codes_of(response) == {"is_active": "invalid_choice"}


@pytest.mark.parametrize("method", ["delete", "put"])
def test_AC_TEN_30_no_delete_route(client: Client, org_a: Organization, method: str) -> None:
    seed(org_a, "Centro")
    response = getattr(client, method)(
        BRANCHES, headers=as_member(member(org_a, Role.OWNER), org_a.id)
    )

    assert response.status_code == 405
    assert names_in(org_a) == [("Centro", "", True)]


# --- AC-TEN-38 ---


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"name": "centro"}, "nombre"),
        ({"name": " CENTRO  "}, "nombre"),
        ({"name": "Sur", "code": "C01"}, "código"),
        ({"name": "Sur", "code": " C01 "}, "código"),
    ],
)
def test_AC_TEN_38_name_case_insensitive_and_code(
    client: Client, org_a: Organization, body: dict[str, str], detail: str, recorded: RecordingSink
) -> None:
    seed(org_a, "Centro", "C01")

    response = post(client, member(org_a, Role.ADMIN), org_a, body)

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert detail in response.json()["detail"]
    assert names_in(org_a) == [("Centro", "C01", True)]
    assert recorded.events == []


def test_AC_TEN_38_code_is_exact_and_empty_never_collides(
    client: Client, org_a: Organization
) -> None:
    seed(org_a, "Centro", "C01")
    admin = member(org_a, Role.ADMIN)

    assert post(client, admin, org_a, {"name": "Sur", "code": "c01"}).status_code == 201
    assert post(client, admin, org_a, {"name": "Este"}).status_code == 201
    assert post(client, admin, org_a, {"name": "Oeste", "code": ""}).status_code == 201


def test_AC_TEN_38_inactive_frees_values(client: Client, org_a: Organization) -> None:
    seed(org_a, "Centro", "C01", active=False)

    response = post(client, member(org_a, Role.ADMIN), org_a, {"name": "centro", "code": "C01"})

    assert response.status_code == 201
    assert names_in(org_a) == [("Centro", "C01", False), ("centro", "C01", True)]


def test_AC_TEN_38_other_org_accepts(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    seed(org_b, "Centro", "C01")

    response = post(client, member(org_a, Role.OWNER), org_a, {"name": "Centro", "code": "C01"})

    assert response.status_code == 201
    assert names_in(org_a) == [("Centro", "C01", True)]


# --- RF-TEN-06: the body ---


@pytest.mark.parametrize(
    ("body", "codes"),
    [
        ({}, {"name": "required"}),
        ({"name": "   "}, {"name": "blank"}),
        ({"name": None}, {"name": "invalid"}),
        ({"name": 7}, {"name": "invalid"}),
        ({"name": "x" * 121}, {"name": "max_length"}),
        ({"name": "Centro", "code": "x" * 33}, {"code": "max_length"}),
        ({"name": "Centro", "address": "x" * 256}, {"address": "max_length"}),
        (
            {"code": ["C01"], "status": "x"},
            {"name": "required", "code": "invalid", "status": "unknown_field"},
        ),
    ],
)
def test_RF_TEN_06_create_validates_the_body(
    client: Client, org_a: Organization, body: dict[str, Any], codes: dict[str, str]
) -> None:
    response = post(client, member(org_a, Role.OWNER), org_a, body)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert codes_of(response) == codes
    assert names_in(org_a) == []


def test_RF_TEN_06_body_must_be_an_object(client: Client, org_a: Organization) -> None:
    response = post(client, member(org_a, Role.OWNER), org_a, ["Centro"])

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert names_in(org_a) == []


def test_RF_TEN_06_list_is_paginated(client: Client, org_a: Organization) -> None:
    for n in range(3):
        seed(org_a, f"Sucursal {n}")

    body = listed(client, member(org_a, Role.OPERATOR), org_a, "?page_size=2")

    assert (body["count"], len(body["results"])) == (3, 2)
    assert body["next"] == "/api/branches/?page=2&page_size=2"


def test_RF_TEN_06_contract_declares_the_routes() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    branches = contract["paths"]["/api/branches/"]

    assert set(branches) == {"get", "post"}
    assert branches["get"]["operationId"] == "branches_list"
    assert branches["post"]["operationId"] == "branches_create"
    request = contract["components"]["schemas"]["BranchCreateRequest"]
    assert request["required"] == ["name"]
    assert set(request["properties"]) == {"name", "code", "address"}
    headers = [p["name"] for p in branches["post"]["parameters"] if p["in"] == "header"]
    assert headers == ["X-Organization-Id"]
