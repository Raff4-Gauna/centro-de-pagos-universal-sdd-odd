"""The net itself, on the broken endpoints of ``synthetic.py`` (AC-TEN-12, design.md §9).

Both halves catch each bypass on their own: ``classify`` by reading the view (``guard_errors``) and
``check_endpoint`` by the handler's ``200`` where the guard answers ``400``/``404``. The control,
``GoodViewSet``, passes both: the net does not fail everything.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from django.test import Client

from tests.cross_tenant import synthetic
from tests.cross_tenant.classifier import Endpoint, classify, tenant_endpoints, walk
from tests.cross_tenant.harness import World, check_endpoint, check_exempt
from tests.cross_tenant.registry import Exemption, Registry

URLCONF = synthetic.__name__
ROUTES = walk(URLCONF)


def errors_naming(route: str, registry: Registry = synthetic.REGISTRY) -> list[str]:
    return [error for error in classify(ROUTES, registry) if route in error]


def endpoint_at(route: str) -> Endpoint:
    (endpoint,) = [e for e in tenant_endpoints(ROUTES) if e.route == route]
    return endpoint


def test_AC_TEN_12_the_walker_reads_the_resolver() -> None:
    declared = {str(pattern.pattern) for pattern in synthetic.urlpatterns}

    assert {route.route for route in ROUTES} == declared


def test_AC_TEN_12_new_route_without_case_fails() -> None:
    assert errors_naming(synthetic.UNCASED) == [
        f"GET {synthetic.UNCASED}: tenant-scoped route without a CrossTenantCase"
    ]


@pytest.mark.parametrize("route", [synthetic.PLAIN_DRF, synthetic.PLAIN_DJANGO])
def test_AC_TEN_12_route_neither_tenant_nor_exempt_fails(route: str) -> None:
    (error,) = errors_naming(route)

    assert error.endswith("unclassified: neither a TenantViewSet nor exempt")


def test_AC_TEN_12_an_exempt_route_with_its_reason_passes() -> None:
    route = synthetic.PLAIN_DJANGO
    registry = replace(synthetic.REGISTRY, exemptions=(Exemption(route, "sin organización"),))

    assert errors_naming(route, registry) == []


def test_AC_TEN_12_an_exempt_get_behind_the_login_needs_a_read() -> None:
    route = synthetic.PLAIN_DRF
    without = replace(synthetic.REGISTRY, exemptions=(Exemption(route, "de la persona"),))
    read = Exemption(route, "de la persona", read=lambda organization: f"/{route}")
    with_read = replace(synthetic.REGISTRY, exemptions=(read,))

    (error,) = errors_naming(route, without)

    assert error.endswith("exempt GET behind the login without a read URL")
    assert errors_naming(route, with_read) == []


def test_AC_TEN_12_exemption_needs_a_reason_and_a_route() -> None:
    registry = replace(
        synthetic.REGISTRY,
        exemptions=(Exemption(synthetic.PLAIN_DRF, " "), Exemption("synthetic/gone/", "x")),
    )

    errors = classify(ROUTES, registry)

    assert f"{synthetic.PLAIN_DRF}: exempt without a reason" in errors
    assert "synthetic/gone/: exempt but no such route (stale entry)" in errors


def test_AC_TEN_12_a_tenant_route_cannot_be_exempt() -> None:
    registry = replace(synthetic.REGISTRY, exemptions=(Exemption(synthetic.GOOD, "no"),))

    assert any("cannot be exempt" in error for error in errors_naming(synthetic.GOOD, registry))


def test_AC_TEN_12_a_case_without_its_route_is_stale() -> None:
    case = replace(synthetic.REGISTRY.cases[0], route="synthetic/gone/")
    registry = replace(synthetic.REGISTRY, cases=(*synthetic.REGISTRY.cases, case))

    assert "GET synthetic/gone/: CrossTenantCase without a tenant-scoped route (stale entry)" in (
        classify(ROUTES, registry)
    )


def test_AC_TEN_12_the_control_is_clean_for_the_classifier() -> None:
    assert errors_naming(synthetic.GOOD) == []


@pytest.mark.parametrize(
    ("route", "names"),
    [
        (synthetic.INITKWARGS, "initkwarg 'get_permissions'"),
        (synthetic.REASSIGNED, "check_permissions is not TenantViewSet's"),
        (synthetic.INITIAL, "initial is not TenantViewSet's"),
        (synthetic.DISPATCH, "dispatch is not TenantViewSet's"),
    ],
)
def test_AC_TEN_12_guard_bypass_is_caught_by_the_classifier(route: str, names: str) -> None:
    assert any(names in error for error in errors_naming(route))


@pytest.mark.django_db
@pytest.mark.urls(URLCONF)
def test_AC_TEN_12_the_control_passes_the_harness(xt_client: Client, world: World) -> None:
    endpoint = endpoint_at(synthetic.GOOD)
    case = synthetic.REGISTRY.case_for(synthetic.GOOD, "GET")
    assert case is not None

    assert check_endpoint(xt_client, world, endpoint, case) == []


@pytest.mark.django_db
@pytest.mark.urls(URLCONF)
@pytest.mark.parametrize("route", synthetic.BYPASSES)
def test_AC_TEN_12_guard_bypass_is_caught_by_the_harness(
    xt_client: Client, world: World, route: str
) -> None:
    case = synthetic.REGISTRY.case_for(route, "GET")
    assert case is not None

    failures = check_endpoint(xt_client, world, endpoint_at(route), case)

    assert f"GET {route} [no header]: answered 200, not 400 organization_required" in failures
    assert f"GET {route} [org B]: answered 200, not 404 organization_not_found" in failures


def _exemption(route: str) -> Exemption:
    (exemption,) = [e for e in synthetic.REGISTRY.exemptions if e.route == route]
    return exemption


@pytest.mark.django_db
@pytest.mark.urls(URLCONF)
def test_AC_TEN_12_an_exempt_route_of_the_person_passes(xt_client: Client, world: World) -> None:
    assert check_exempt(xt_client, world, _exemption(synthetic.MINE)) == []


@pytest.mark.django_db
@pytest.mark.urls(URLCONF)
def test_AC_TEN_12_an_exempt_route_that_lists_others_is_caught(
    xt_client: Client, world: World
) -> None:
    failures = check_exempt(xt_client, world, _exemption(synthetic.EVERYONE))

    assert [failure.split(":")[0] for failure in failures] == [
        f"GET {synthetic.EVERYONE} (exempt) [no header]",
        f"GET {synthetic.EVERYONE} (exempt) [org B]",
    ]
    assert all(str(world.org_b.id) in failure for failure in failures)
