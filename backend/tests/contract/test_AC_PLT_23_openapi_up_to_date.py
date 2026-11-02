"""AC-PLT-23 (backend; RN-PLT-15, RF-PLT-14, ADR-0005): the committed OpenAPI contract.

``specs/_contracts/openapi.yaml`` is what ``manage.py export_openapi`` generates from the public
URLconf (``config.urls``, never the dev-only routes of Q-056); ``--check`` fails with the unified
diff when it is out of date, without writing. Every operation answers ``4XX``/``5XX`` with the
``Problem`` component (``application/problem+json``). The version lives in ``info.version``, never
in the URL.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import URLPattern, URLResolver, get_resolver, path
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import OpenApiResponse, extend_schema
from drf_spectacular.validation import validate_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api import schema
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.management.commands import export_openapi
from tests.conftest import BACKEND_DIR

CONTRACT = BACKEND_DIR.parent / "specs" / "_contracts" / "openapi.yaml"
PROBLEM_REF = "#/components/schemas/Problem"
SEMVER = re.compile(r"\d+\.\d+\.\d+")
VERSION_IN_URL = re.compile(r"(^|/)v\d+(/|$)")


class Echo(serializers.Serializer[dict[str, Any]]):
    message = serializers.CharField()


class SampleView(APIView):
    """A documented view: the hook adds what it does not declare."""

    @extend_schema(responses={200: Echo, "4XX": OpenApiResponse(description="declared")})
    def get(self, request: Request) -> Response:
        return Response({"message": "ok"})

    @extend_schema(request=Echo, responses={201: Echo})
    def post(self, request: Request) -> Response:
        return Response({"message": "ok"}, status=201)


# This module is the URLconf of the hook test.
urlpatterns: list[URLPattern | URLResolver] = [path("api/sample/", SampleView.as_view())]


def use_contract_path(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    monkeypatch.setattr(export_openapi, "contract_path", lambda: target)


def test_AC_PLT_23_committed_openapi_matches_generated() -> None:
    out = StringIO()
    call_command("export_openapi", "--check", stdout=out)
    assert "up to date" in out.getvalue()
    contract = CONTRACT.read_text(encoding="utf-8")
    assert schema.PUBLIC_URLCONF == "config.urls"
    assert "/api/dev/" not in contract


@pytest.mark.parametrize("committed", ["stale", "missing"])
def test_AC_PLT_23_check_mode_fails_and_prints_diff_when_outdated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: str
) -> None:
    target = tmp_path / "openapi.yaml"
    current = CONTRACT.read_text(encoding="utf-8")
    stale = current.replace(f"version: {schema.API_VERSION}\n", "version: 0.0.0-stale\n")
    assert stale != current
    if committed == "stale":
        target.write_bytes(stale.encode())
    use_contract_path(monkeypatch, target)
    out = StringIO()
    with pytest.raises(CommandError, match="out of date"):
        call_command("export_openapi", "--check", stdout=out)
    diff = out.getvalue()
    assert "--- specs/_contracts/openapi.yaml (committed)" in diff
    assert "+++ specs/_contracts/openapi.yaml (generated)" in diff
    assert f"+  version: {schema.API_VERSION}\n" in diff
    if committed == "stale":
        assert "-  version: 0.0.0-stale\n" in diff
        assert target.read_bytes() == stale.encode()  # --check never writes
    else:
        assert not target.exists()


def test_AC_PLT_23_export_is_deterministic_lf_and_free_of_local_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "openapi.yaml"
    use_contract_path(monkeypatch, target)
    call_command("export_openapi", stdout=StringIO())
    first = target.read_bytes()
    call_command("export_openapi", stdout=StringIO())
    assert target.read_bytes() == first == CONTRACT.read_bytes()
    assert b"\r" not in first
    assert first.endswith(b"\n")
    text = first.decode("utf-8")
    for local in (str(BACKEND_DIR), BACKEND_DIR.as_posix(), str(tmp_path), tmp_path.as_posix()):
        assert local not in text


def test_AC_PLT_23_generation_warning_fails_the_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Views without serializers make drf-spectacular guess: a warning is a failure (--fail-on-warn).
    target = tmp_path / "openapi.yaml"
    use_contract_path(monkeypatch, target)
    monkeypatch.setattr(export_openapi, "PUBLIC_URLCONF", "tests.api.urls_test")
    with pytest.raises(CommandError, match="warnings"):
        call_command("export_openapi", stdout=StringIO(), stderr=StringIO())
    assert not target.exists()


def test_AC_PLT_23_problem_component_on_4xx_5xx() -> None:
    generated = SchemaGenerator(urlconf=__name__).get_schema(request=None, public=True)
    validate_schema(generated)
    operations = generated["paths"]["/api/sample/"]
    for method in ("get", "post"):
        for status_range in ("4XX", "5XX"):
            response = operations[method]["responses"][status_range]
            if (method, status_range) == ("get", "4XX"):
                assert response == {"description": "declared"}  # never overwritten
                continue
            content = response["content"]
            assert content == {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": PROBLEM_REF}}}
    problem = generated["components"]["schemas"]["Problem"]
    assert problem["required"] == ["type", "title", "status", "code", "request_id"]
    assert set(problem["properties"]) == {*problem["required"], "detail", "errors"}
    field_error = generated["components"]["schemas"]["ProblemFieldError"]
    assert field_error["required"] == ["field", "code", "message"]
    # T-PLT-15 review: detail and errors[].message may echo client input; text, never HTML.
    assert "HTML" in problem["properties"]["detail"]["description"]
    assert "HTML" in field_error["properties"]["message"]["description"]
    committed = yaml.safe_load(CONTRACT.read_bytes())
    assert committed["components"]["schemas"]["Problem"] == problem


def _routes(patterns: list[URLPattern | URLResolver], prefix: str = "") -> list[str]:
    routes = []
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        routes.append(route)
        if isinstance(pattern, URLResolver):
            routes.extend(_routes(pattern.url_patterns, route))
    return routes


def test_RN_PLT_15_info_version_set_and_no_version_in_url() -> None:
    committed = yaml.safe_load(CONTRACT.read_bytes())
    assert SEMVER.fullmatch(schema.API_VERSION)
    assert committed["info"]["version"] == schema.API_VERSION
    routes = [*committed["paths"], *_routes(get_resolver(schema.PUBLIC_URLCONF).url_patterns)]
    assert routes  # the public URLconf has routes (/healthz, /readyz)
    assert [route for route in routes if VERSION_IN_URL.search(route)] == []
