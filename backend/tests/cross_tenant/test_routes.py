"""Every registered route, classified and attacked from another organization (AC-TEN-12/33).

The parameters come from walking the resolver at collection time (``classifier.walk``), never
from a list: a route a module adds is classified, and if it is a ``TenantViewSet`` each of its
methods runs the whole harness. ``test_walker.py`` proves the net on broken synthetic endpoints.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.identity.models import User
from config.settings import test as test_settings
from tests.cross_tenant.classifier import (
    Endpoint,
    classify,
    exempt_reads,
    tenant_endpoints,
    walk,
)
from tests.cross_tenant.harness import (
    World,
    check_endpoint,
    check_exempt,
    check_head,
    check_operator,
)
from tests.cross_tenant.registry import CrossTenantCase, Exemption, load
from tests.cross_tenant.urls import BASE_URLCONF, SUITE_URLCONF

PROD_URLCONF = "config.urls"
REGISTRY = load()
ROUTES = walk(SUITE_URLCONF)
ENDPOINTS = tenant_endpoints(ROUTES)
EXEMPT_READS = exempt_reads(ROUTES, REGISTRY)

pytestmark = pytest.mark.urls(SUITE_URLCONF)


def case_of(endpoint: Endpoint) -> CrossTenantCase:
    case = REGISTRY.case_for(endpoint.route, endpoint.method)
    if case is None:
        pytest.fail(f"{endpoint.label}: tenant-scoped route without a CrossTenantCase")
    return case


def by_label(endpoints: list[Endpoint]) -> list[object]:
    return [pytest.param(endpoint, id=endpoint.label) for endpoint in endpoints]


def test_AC_TEN_12_the_suite_walks_every_real_route() -> None:
    walked = {route.route for route in ROUTES}

    assert test_settings.ROOT_URLCONF == BASE_URLCONF
    assert {route.route for route in walk(BASE_URLCONF)} <= walked
    assert {route.route for route in walk(PROD_URLCONF)} <= walked
    assert ENDPOINTS, "no tenant-scoped route was found: the walker is not looking"
    assert EXEMPT_READS, "no exempt route of the person is read: the scope check is not running"


def test_AC_TEN_12_new_route_without_case_fails() -> None:
    """The real URLconf: every route is a covered TenantViewSet or exempt with a reason."""
    assert classify(ROUTES, REGISTRY) == []


@pytest.mark.parametrize("endpoint", by_label(ENDPOINTS))
def test_AC_TEN_12_every_case_runs(xt_client: Client, world: World, endpoint: Endpoint) -> None:
    assert check_endpoint(xt_client, world, endpoint, case_of(endpoint)) == []


@pytest.mark.parametrize("endpoint", by_label([e for e in ENDPOINTS if e.method == "GET"]))
def test_AC_TEN_12_head_is_denied_like_get(
    xt_client: Client, world: World, endpoint: Endpoint
) -> None:
    assert check_head(xt_client, world, endpoint, case_of(endpoint)) == []


@pytest.mark.parametrize("endpoint", by_label(ENDPOINTS))
def test_AC_TEN_33_superuser_body_identical(
    xt_client: Client, world: World, endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``User`` has no such flags (Q-228): set them as if it did; no route may look at them."""
    monkeypatch.setattr(User, "is_superuser", True, raising=False)
    monkeypatch.setattr(User, "is_staff", True, raising=False)

    assert check_operator(xt_client, world, endpoint, case_of(endpoint)) == []


@pytest.mark.parametrize("exemption", [pytest.param(e, id=e.route) for e in EXEMPT_READS])
def test_AC_TEN_12_exempt_route_is_scoped_to_the_person(
    xt_client: Client, world: World, exemption: Exemption
) -> None:
    """Exempt from the active organization is not exempt from isolation (design.md §3.5)."""
    assert check_exempt(xt_client, world, exemption) == []
