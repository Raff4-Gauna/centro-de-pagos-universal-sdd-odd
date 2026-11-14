"""AC-IDA-32, SPEC-01's part (RN-IDA-23, Q-106, Q-116): no HTTP way to provision or deactivate.

Creating organizations and owners and deactivating or reactivating users are management commands
only (``deactivate_user``, ``reactivate_user``; the bootstrap is ``T-TEN-18``'s, with its own test).
Here: the published contract and every route of the public URLconf, whatever the schema shows, have
no operation for either; and Django's admin is not installed, so it cannot answer in prod.

The rule on organizations leaves room for what SPEC-02 publishes (design.md §6 of 02): reading them
and ``PATCH /api/organizations/current/``, never ``POST``, ``PUT`` or ``DELETE`` (AC-TEN-21/29).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.conf import settings
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.conftest import RunDjango
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT

# Path segments that would name a user-status or provisioning endpoint.
FORBIDDEN_SEGMENTS = frozenset(
    {
        "activate",
        "admin",
        "bootstrap",
        "deactivate",
        "disable",
        "enable",
        "owner",
        "owners",
        "reactivate",
        "user",
        "users",
    }
)
ORGANIZATIONS = "/api/organizations"
ORGANIZATION_METHODS = frozenset({"get", "head", "options", "patch"})
WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})

_PROD_PROBE = """
import django
from django.conf import settings
from django.urls import Resolver404, resolve
django.setup()
answered = []
for path in ("/admin/", "/admin/login/"):
    try:
        resolve(path)
        answered.append(path)
    except Resolver404:
        pass
admin = [app for app in settings.INSTALLED_APPS if app.startswith("django.contrib.admin")]
print(settings.ROOT_URLCONF, answered, admin)
"""


def contract_paths() -> dict[str, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = yaml.safe_load(CONTRACT.read_bytes())["paths"]
    return paths


def segments(route: str) -> set[str]:
    return {part.strip("{}<>").lower() for part in route.replace("-", "/").split("/") if part}


def public_routes(
    patterns: list[URLPattern | URLResolver] | None = None, prefix: str = ""
) -> Iterator[str]:
    """Every route of ``config.urls``, the prod URLconf, including any the schema leaves out."""
    for pattern in patterns if patterns is not None else get_resolver("config.urls").url_patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from public_routes(pattern.url_patterns, route)
        else:
            yield route


def test_AC_IDA_32_schema_has_no_provisioning_endpoints() -> None:
    paths = contract_paths()
    assert paths, "the contract publishes no path"

    for path, operations in paths.items():
        methods = {method for method in operations if method != "parameters"}
        assert not segments(path) & FORBIDDEN_SEGMENTS, path
        if path.startswith(ORGANIZATIONS):
            assert methods <= ORGANIZATION_METHODS, path
        # No write takes a user's id: nobody edits another person by HTTP.
        if "user_id" in segments(path):
            assert not methods & WRITE_METHODS, path


def test_AC_IDA_32_no_public_route_provisions_or_deactivates() -> None:
    routes = list(public_routes())
    assert "api/me/" in routes

    for route in routes:
        assert not segments(route) & FORBIDDEN_SEGMENTS, route


@pytest.mark.urls("config.urls")
def test_AC_IDA_32_admin_does_not_answer(client: Client) -> None:
    assert not [app for app in settings.INSTALLED_APPS if app.startswith("django.contrib.admin")]
    for path in ("/admin/", "/admin/login/"):
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404


def test_AC_IDA_32_admin_absent_under_prod_settings(run_django: RunDjango) -> None:
    result = run_django("-c", _PROD_PROBE, settings_module=PROD, values=VALID_PROD_ENV)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "config.urls [] []"
