"""``resolve_branch_filter``: the branch of the selector is a filter, not a boundary (RN-TEN-16).

No business route filters by branch yet (charges and reports do, later), so the tests mount
``FilteredViewSet``, a ``branch.read`` list that answers the branch the filter resolved. AC-TEN-09:
a ``branch_id`` of another organization is ``404 not_found``, the body of one that does not exist.
AC-TEN-32 (Q-204): every role, operator included, filters by any branch of the active organization;
an inactive one still filters (its history stays, RN-TEN-19). Without ``branch_id``: all branches.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.test import Client
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.common.authz.roles import Role
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.api.filters import resolve_branch_filter
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Organization
from tests.tenancy.api.probe import as_member, new_org
from tests.tenancy.api.test_branches import codes_of, member, seed

pytestmark = [pytest.mark.django_db, pytest.mark.urls(__name__)]

FILTERED = "/api/filtered/"


class FilteredViewSet(TenantViewSet):
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
    }

    def list(self, request: Request) -> Response:
        branch = resolve_branch_filter(request, self.tenant)
        if branch is None:
            return Response({"branch": None})
        return Response({"branch": {"id": str(branch.pk), "name": branch.name}})


router = SimpleRouter()
router.register("api/filtered", FilteredViewSet, basename="filtered")
urlpatterns = router.urls


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def filtered(client: Client, headers: dict[str, str], branch_id: object) -> Any:
    return client.get(f"{FILTERED}?branch_id={branch_id}", headers=headers)


def test_AC_TEN_09_foreign_branch_filter_is_404(client: Client, org_a: Organization) -> None:
    seed(org_a, "Centro")
    foreign = seed(new_org("B"), "Centro de B")
    headers = as_member(member(org_a, Role.OWNER), org_a.id)

    response = filtered(client, headers, foreign.pk)
    unknown = filtered(client, headers, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "Centro de B" not in response.content.decode()
    assert str(foreign.pk) not in response.content.decode()
    body, other = dict(response.json()), dict(unknown.json())
    body.pop("request_id"), other.pop("request_id")
    assert body == other


@pytest.mark.parametrize("value", ["not-a-uuid", "-" * 36, ""])
def test_AC_TEN_09_malformed_branch_id_is_400(
    client: Client, org_a: Organization, value: str
) -> None:
    response = filtered(client, as_member(member(org_a, Role.VIEWER), org_a.id), value)

    assert response.status_code == 400
    assert codes_of(response) == {"branch_id": "invalid"}


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER, Role.ADMIN])
def test_AC_TEN_32_operator_filters_any_branch(
    client: Client, org_a: Organization, role: Role
) -> None:
    centro, norte = seed(org_a, "Centro"), seed(org_a, "Norte", active=False)
    headers = as_member(member(org_a, role), org_a.id)

    for branch in (centro, norte):
        response = filtered(client, headers, branch.pk)
        assert response.status_code == 200
        assert response.json() == {"branch": {"id": str(branch.pk), "name": branch.name}}


def test_RN_TEN_16_without_branch_id_is_every_branch(client: Client, org_a: Organization) -> None:
    seed(org_a, "Centro")

    response = client.get(FILTERED, headers=as_member(member(org_a, Role.OPERATOR), org_a.id))

    assert response.status_code == 200
    assert response.json() == {"branch": None}
