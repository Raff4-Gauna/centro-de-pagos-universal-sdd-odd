"""``ActionPermission`` and ``TenantViewSet`` (RN-TEN-08/09/18, design.md §3.5, §3.7, §3.8).

After ``ResolveTenant``: the role of the membership read on this request (``403 forbidden``), then
the suspension (``409 organization_suspended`` for a ``WRITE``). Every action of a ``TenantViewSet``
declares its ``ActionSpec`` or the class does not import; an action without one at runtime is
denied.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from drf_spectacular.generators import SchemaGenerator
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.api.authentication import IsAuthenticated
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.api.permissions import DENIED_EVENT, ActionPermission, ResolveTenant
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from tests.tenancy.api import probe
from tests.tenancy.api.probe import PROBE, URLCONF, add_member, as_member, new_org, new_user

pytestmark = [pytest.mark.django_db, pytest.mark.urls(URLCONF)]

READ_SPEC = TENANCY_ACTIONS[TenancyAction.BRANCH_READ]


def call(
    client: Client, method: str, role: Role, status: OrgStatus = OrgStatus.ACTIVE
) -> tuple[Any, list[MutableMapping[str, Any]]]:
    organization = new_org("A", status)
    user = new_user(f"{role.value}-{status.value}")
    add_member(organization, user, role)
    with capture_logs(processors=[merge_contextvars]) as logs:
        response = getattr(client, method)(PROBE, headers=as_member(user, organization.id))
    return response, [entry for entry in logs if entry["event"] == DENIED_EVENT]


# --- Role (RN-TEN-09) and suspension (RN-TEN-18, Q-221) ------------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_RN_TEN_09_every_role_reads(client: Client, role: Role) -> None:
    response, logged = call(client, "get", role)

    assert response.status_code == 200
    assert logged == []


@pytest.mark.parametrize(("role", "expected"), [(Role.OWNER, 201), (Role.ADMIN, 201)])
def test_RN_TEN_09_managers_write(client: Client, role: Role, expected: int) -> None:
    assert call(client, "post", role)[0].status_code == expected


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_RN_TEN_09_role_outside_the_spec_is_forbidden(client: Client, role: Role) -> None:
    response, logged = call(client, "post", role)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    (denial,) = logged
    assert denial["reason"] == "role_not_allowed"
    assert denial["action"] == TenancyAction.BRANCH_CREATE.value
    assert denial["organization_id"]  # the organization was validated: it is bound (RNF-TEN-02)


def test_RN_TEN_18_write_on_a_suspended_org_is_409(client: Client) -> None:
    response, logged = call(client, "post", Role.OWNER, OrgStatus.SUSPENDED)

    assert response.status_code == 409
    assert response.json()["code"] == "organization_suspended"
    assert [denial["reason"] for denial in logged] == ["organization_suspended"]


def test_RN_TEN_18_read_on_a_suspended_org_passes(client: Client) -> None:
    response, _ = call(client, "get", Role.VIEWER, OrgStatus.SUSPENDED)

    assert response.status_code == 200
    assert response.json()["status"] == OrgStatus.SUSPENDED.value


def test_RN_TEN_09_role_is_checked_before_the_suspension(client: Client) -> None:
    """design.md §3.5: ``403`` before ``409``."""
    assert call(client, "post", Role.VIEWER, OrgStatus.SUSPENDED)[0].status_code == 403


def test_RN_TEN_09_undeclared_action_is_forbidden(client: Client) -> None:
    """``OPTIONS`` is DRF's ``metadata`` action: no ``ActionSpec``, so it is denied."""
    response, logged = call(client, "options", Role.OWNER)

    assert response.status_code == 403
    assert [denial["reason"] for denial in logged] == ["undeclared_action"]


def test_RN_TEN_09_unmapped_method_is_405(client: Client) -> None:
    assert call(client, "delete", Role.OWNER)[0].status_code == 405


# --- TenantViewSet: every action declares its ActionSpec -----------------------------------------


def test_RN_TEN_09_viewset_permissions_run_in_order() -> None:
    assert TenantViewSet.permission_classes == [IsAuthenticated, ResolveTenant, ActionPermission]
    assert TenantViewSet.tenant_scoped is True


def test_RN_TEN_09_action_without_spec_fails_at_import() -> None:
    with pytest.raises(ImproperlyConfigured, match="retrieve"):

        class _Missing(TenantViewSet):
            action_specs = {"list": READ_SPEC}  # noqa: RUF012

            def list(self, request: Request) -> Response:
                return Response()

            def retrieve(self, request: Request, pk: str) -> Response:
                return Response()


def test_RN_TEN_09_extra_action_without_spec_fails_at_import() -> None:
    with pytest.raises(ImproperlyConfigured, match="deactivate"):

        class _MissingExtra(TenantViewSet):
            action_specs = {}  # noqa: RUF012

            @action(detail=True, methods=["post"])
            def deactivate(self, request: Request, pk: str) -> Response:
                return Response()


def test_RN_TEN_09_spec_must_be_an_action_spec() -> None:
    with pytest.raises(ImproperlyConfigured, match="list"):

        class _NotASpec(TenantViewSet):
            action_specs = {"list": "branch.read"}  # type: ignore[dict-item]  # noqa: RUF012

            def list(self, request: Request) -> Response:
                return Response()


def test_RN_TEN_09_base_without_actions_is_valid() -> None:
    class _Abstract(TenantViewSet):
        pass

    assert _Abstract.action_specs == {}


def test_RN_TEN_03_schema_requires_the_organization_header() -> None:
    """design.md §6: every operation of a ``TenantViewSet`` declares ``X-Organization-Id``."""
    schema = SchemaGenerator(patterns=probe.urlpatterns).get_schema(request=None, public=True)

    operations = schema["paths"][PROBE]
    assert set(operations) == {"get", "post"}
    for operation in operations.values():
        (header,) = [p for p in operation["parameters"] if p["in"] == "header"]
        assert (header["name"], header["required"]) == ("X-Organization-Id", True)
        assert header["schema"] == {"type": "string", "format": "uuid"}
