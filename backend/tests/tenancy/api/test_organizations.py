"""``GET /api/organizations/``: my organizations and my role in each (RF-TEN-02, RN-TEN-07/10).

AC-TEN-08: exactly the organizations of the user's ``active`` memberships, with their role, by
name; never one of another user nor a revoked one. The route is exempt from the active organization
(design.md §3.5): it needs no ``X-Organization-Id`` and ignores one. AC-TEN-21: no organization is
created, replaced or deleted through it (``405``; RN-TEN-10).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.api.pagination import PAGE_SIZE
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.models import User
from apps.tenancy.models import Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import (
    HEADER,
    PLATFORM,
    add_member,
    bearer_of,
    new_org,
    new_user,
    revoke,
)

pytestmark = pytest.mark.django_db

ORGANIZATIONS = "/api/organizations/"


def organizations_count() -> int:
    return Organization.objects.unscoped(PLATFORM).count()


def listed(client: Client, user: User, **headers: str) -> list[dict[str, Any]]:
    response = client.get(ORGANIZATIONS, headers={**bearer_of(user), **headers})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert (body["count"], body["next"], body["previous"]) == (len(body["results"]), None, None)
    results: list[dict[str, Any]] = body["results"]
    return results


@pytest.fixture
def setup() -> dict[str, Any]:
    """Ana is ``operator`` in Zeta and ``viewer`` in Alfa (suspended); Beto is in Ceta and Dora."""
    zeta, alfa = new_org("Zeta"), new_org("Alfa", OrgStatus.SUSPENDED)
    ceta, dora = new_org("Ceta"), new_org("Dora")
    ana, beto = new_user("ana"), new_user("beto")
    add_member(zeta, ana, Role.OPERATOR)
    add_member(alfa, ana, Role.VIEWER)
    add_member(ceta, beto, Role.OWNER)
    revoke(dora, add_member(dora, ana, Role.ADMIN))
    return {"zeta": zeta, "alfa": alfa, "ceta": ceta, "dora": dora, "ana": ana, "beto": beto}


def test_AC_TEN_08_exactly_my_orgs_and_roles(client: Client, setup: dict[str, Any]) -> None:
    alfa, zeta = setup["alfa"], setup["zeta"]
    assert listed(client, setup["ana"]) == [
        {"id": str(alfa.id), "name": "Alfa", "status": "suspended", "role": "viewer"},
        {"id": str(zeta.id), "name": "Zeta", "status": "active", "role": "operator"},
    ]
    assert [o["name"] for o in listed(client, setup["beto"])] == ["Ceta"]


def test_AC_TEN_08_header_is_ignored(client: Client, setup: dict[str, Any]) -> None:
    mine = listed(client, setup["ana"])
    for other in ("ceta", "dora", "zeta"):
        assert listed(client, setup["ana"], **{HEADER: str(setup[other].id)}) == mine
    assert listed(client, setup["ana"], **{HEADER: "not-a-uuid"}) == mine


def test_AC_TEN_08_without_memberships_is_an_empty_list(client: Client) -> None:
    assert listed(client, new_user("eva")) == []


def test_AC_TEN_08_is_paginated(client: Client) -> None:
    ana = new_user("ana")
    for index in range(PAGE_SIZE + 1):
        add_member(new_org(f"Org {index:03}"), ana, Role.VIEWER)
    first = client.get(ORGANIZATIONS, headers=bearer_of(ana)).json()
    assert (first["count"], len(first["results"])) == (PAGE_SIZE + 1, PAGE_SIZE)
    assert first["next"] == f"{ORGANIZATIONS}?page=2"
    second = client.get(first["next"], headers=bearer_of(ana)).json()
    assert [o["name"] for o in second["results"]] == [f"Org {PAGE_SIZE:03}"]


def test_AC_TEN_08_anonymous_is_401(client: Client) -> None:
    response = client.get(ORGANIZATIONS)
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_AC_TEN_21_no_org_creation_via_api(
    client: Client, setup: dict[str, Any], method: str
) -> None:
    owner = setup["beto"]  # owner of Ceta: not even an owner creates one
    before = organizations_count()
    send = getattr(client, method)
    for headers in (bearer_of(owner), {**bearer_of(owner), HEADER: str(setup["ceta"].id)}):
        response = send(
            ORGANIZATIONS, data={"name": "Nueva"}, content_type="application/json", headers=headers
        )
        assert response.status_code == 405
        assert response.json()["code"] == "method_not_allowed"
    assert organizations_count() == before
    assert Organization.objects.unscoped(PLATFORM).filter(name="Nueva").exists() is False


def test_AC_TEN_21_anonymous_post_is_401_before_405(client: Client) -> None:
    response = client.post(ORGANIZATIONS, data={}, content_type="application/json")
    assert response.status_code == 401


def test_RF_TEN_02_contract_lists_my_organizations_without_the_header() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    assert list(contract["paths"][ORGANIZATIONS]) == ["get"]
    operation = contract["paths"][ORGANIZATIONS]["get"]
    names = {p["name"] for p in operation.get("parameters", [])}
    assert HEADER not in names
    assert names == {"page", "page_size"}
    body = operation["responses"]["200"]["content"]["application/json"]["schema"]
    page = contract["components"]["schemas"][body["$ref"].rsplit("/", 1)[1]]
    item = page["properties"]["results"]["items"]["$ref"].rsplit("/", 1)[1]
    organization = contract["components"]["schemas"][item]
    assert set(organization["required"]) == {"id", "name", "status", "role"}
    schemas = contract["components"]["schemas"]
    for field, enum in (("role", Role), ("status", OrgStatus)):
        [ref] = organization["properties"][field]["allOf"]
        assert schemas[ref["$ref"].rsplit("/", 1)[1]]["enum"] == [e.value for e in enum]
    assert contract["info"]["version"] == "0.15.0"
