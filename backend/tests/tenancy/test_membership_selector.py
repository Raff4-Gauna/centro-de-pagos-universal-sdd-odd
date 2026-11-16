"""The memberships of a user, for ``/api/me`` and "my organizations" (RF-TEN-02, AC-IDA-21).

``selectors.memberships.list_active_memberships(user_id)`` reads them in one query; the
``TenancyMembershipSelector`` of ``services/membership_selector.py`` is SPEC-01's
``MembershipSelectorPort`` and is the one ``IDENTITY_MEMBERSHIP_SELECTOR`` names, so ``GET /api/me``
lists the real memberships: active ones only, of the authenticated person only, by name.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.ports.memberships import MembershipSelectorPort, MembershipSummary
from apps.identity.ports.registry import get_membership_selector
from apps.tenancy.selectors.memberships import MyMembership, list_active_memberships
from apps.tenancy.services.membership_selector import TenancyMembershipSelector
from tests.tenancy.api.probe import add_member, bearer_of, new_org, new_user, revoke

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup() -> dict[str, Any]:
    zeta, alfa, ceta = new_org("Zeta"), new_org("Alfa", OrgStatus.SUSPENDED), new_org("Ceta")
    ana, beto = new_user("ana"), new_user("beto")
    add_member(zeta, ana, Role.OPERATOR)
    add_member(alfa, ana, Role.VIEWER)
    revoke(ceta, add_member(ceta, ana, Role.OWNER))
    add_member(ceta, beto, Role.OWNER)
    return {"zeta": zeta, "alfa": alfa, "ceta": ceta, "ana": ana, "beto": beto}


def test_RF_TEN_02_selector_lists_active_ones_by_name_in_one_query(
    setup: dict[str, Any], django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    alfa, zeta = setup["alfa"], setup["zeta"]
    with django_assert_num_queries(1):
        rows = list_active_memberships(setup["ana"].pk)
    assert rows == [
        MyMembership(alfa.id, "Alfa", OrgStatus.SUSPENDED, Role.VIEWER),
        MyMembership(zeta.id, "Zeta", OrgStatus.ACTIVE, Role.OPERATOR),
    ]
    assert list_active_memberships(uuid.uuid4()) == []


def test_AC_IDA_21_port_returns_the_summaries_of_the_selector(setup: dict[str, Any]) -> None:
    port: MembershipSelectorPort = TenancyMembershipSelector()
    assert port.list_active_memberships(setup["ana"].pk) == [
        MembershipSummary(setup["alfa"].id, "Alfa", "viewer"),
        MembershipSummary(setup["zeta"].id, "Zeta", "operator"),
    ]


def test_AC_IDA_21_me_uses_real_selector(client: Client, setup: dict[str, Any]) -> None:
    assert isinstance(get_membership_selector(), TenancyMembershipSelector)
    response = client.get("/api/me/", headers=bearer_of(setup["ana"]))
    assert response.status_code == 200
    assert response.json()["memberships"] == [
        {"organization_id": str(setup["alfa"].id), "organization_name": "Alfa", "role": "viewer"},
        {"organization_id": str(setup["zeta"].id), "organization_name": "Zeta", "role": "operator"},
    ]
    beto = client.get("/api/me/", headers=bearer_of(setup["beto"])).json()
    assert [m["organization_name"] for m in beto["memberships"]] == ["Ceta"]
