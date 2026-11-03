"""AC-PLT-34 (RN-PLT-15, Q-036): every API error is one ``application/problem+json`` (T-PLT-15).

DRF views answer through ``EXCEPTION_HANDLER``; the rest of ``/api/`` (unknown routes, plain Django
views) through ``handler404``/``handler500``. Always ``code`` and ``request_id``; never a trace, a
host, a secret nor an exception message (C-06), whatever ``DEBUG`` says. The trace only in the
access log, under the same ``request_id``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from django.conf import settings
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper
from rest_framework.exceptions import AuthenticationFailed

from apps.common.api.exceptions import problem_exception_handler
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.middleware.access_log import ACCESS_EVENT
from apps.common.middleware.request_id import REQUEST_ID_HEADER
from tests.api.urls_test import LEAK_SENTINEL

if TYPE_CHECKING:
    # What django.test.Client returns; a stub-only type, so never imported at runtime.
    from django.test.client import _MonkeyPatchedWSGIResponse as ClientResponse

PROBLEMS = "/api/test/problems"
ENVELOPE = {"type", "title", "status", "code", "request_id"}

pytestmark = pytest.mark.urls("tests.api.urls_test")


@pytest.fixture
def lenient_client() -> Client:
    """A 500 sends ``got_request_exception``; the default client would re-raise it."""
    return Client(raise_request_exception=False)


def problem(response: ClientResponse) -> dict[str, Any]:
    assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
    body: dict[str, Any] = json.loads(response.content)
    assert body["status"] == response.status_code
    assert body["type"] == f"urn:hub:problem:{body['code']}"
    assert body["title"]
    assert body["request_id"] == response[REQUEST_ID_HEADER]
    return body


@pytest.mark.parametrize("debug", [False, True])
def test_AC_PLT_34_unhandled_exception_returns_problem_json_500(
    lenient_client: Client, settings: SettingsWrapper, debug: bool
) -> None:
    settings.DEBUG = debug
    response = lenient_client.get(PROBLEMS, {"outcome": "500"})
    assert response.status_code == 500
    body = problem(response)
    assert (body.keys(), body["code"]) == (ENVELOPE, "internal_error")


@pytest.mark.parametrize("path", [PROBLEMS, "/api/test/plain/abc"])
def test_AC_PLT_34_500_has_code_and_request_id_without_trace_hosts_or_detail(
    lenient_client: Client, path: str
) -> None:
    # DRF view and plain Django view (handler500): the message carries a token, a Redis URL with
    # its password and a raw path; the cause a pydantic-like input_value.
    response = lenient_client.get(path, {"outcome": "leaky"})
    assert response.status_code == 500
    assert problem(response).keys() == ENVELOPE  # no detail on a 500
    content = response.content.decode()
    leaks = [LEAK_SENTINEL, "example", "Traceback", "RuntimeError", ".py", "testserver"]
    assert [leak for leak in leaks if leak in content] == []
    assert settings.SECRET_KEY not in content


def test_AC_PLT_34_trace_only_in_log_with_same_request_id(
    lenient_client: Client, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    response = lenient_client.get(PROBLEMS, {"outcome": "leaky"})
    out = capsys.readouterr().out
    (event,) = [e for e in map(json.loads, out.splitlines()) if e.get("message") == ACCESS_EVENT]
    assert event["request_id"] == problem(response)["request_id"]
    assert (event["level"], event["status"]) == ("error", 500)
    assert (event["exception_type"], event["exception_chain"]) == ("RuntimeError", ["ValueError"])
    assert any(f.startswith("tests/api/urls_test.py:") for f in event["exception_frames"])
    assert LEAK_SENTINEL not in out


def test_AC_PLT_34_validation_error_has_errors_list(client: Client) -> None:
    response = client.post(PROBLEMS, {"quantities": [0]}, content_type="application/json")
    assert response.status_code == 400
    body = problem(response)
    assert body["code"] == "validation_error"
    errors = sorted((e["field"], e["code"]) for e in body["errors"])
    assert errors == [("amount", "required"), ("quantities.0", "min_value")]
    assert all(isinstance(e["message"], str) and e["message"] for e in body["errors"])


@pytest.mark.parametrize(
    "urlconf",
    [
        pytest.param("config.urls", marks=pytest.mark.urls("config.urls")),
        pytest.param("config.urls_dev", marks=pytest.mark.urls("config.urls_dev")),
    ],
)
def test_AC_PLT_34_unknown_api_route_returns_problem_404(client: Client, urlconf: str) -> None:
    response = client.get(f"/api/{LEAK_SENTINEL}/missing")
    assert response.status_code == 404
    body = problem(response)
    assert body["code"] == "not_found"
    assert body["detail"]
    assert LEAK_SENTINEL not in response.content.decode()
    # Outside /api/ Django keeps its own page.
    assert client.get("/missing")["Content-Type"].startswith("text/html")


@pytest.mark.parametrize(
    ("method", "kwargs", "status", "code"),
    [
        ("get", {"data": {"outcome": "denied"}}, 403, "permission_denied"),
        ("get", {"data": {"outcome": "missing"}}, 404, "not_found"),
        ("delete", {}, 405, "method_not_allowed"),
        ("get", {"HTTP_ACCEPT": "text/html"}, 406, "not_acceptable"),
        ("post", {"data": "{", "content_type": "application/json"}, 400, "parse_error"),
        ("post", {"data": "x", "content_type": "text/plain"}, 415, "unsupported_media_type"),
    ],
)
def test_AC_PLT_34_drf_errors_have_stable_codes_and_no_exception_message(
    client: Client, method: str, kwargs: dict[str, Any], status: int, code: str
) -> None:
    response = getattr(client, method)(PROBLEMS, **kwargs)
    body = problem(response)
    assert (response.status_code, body["code"]) == (status, code)
    assert body["detail"]
    assert LEAK_SENTINEL not in response.content.decode()


def test_AC_PLT_34_exception_headers_are_preserved(client: Client) -> None:
    response = client.get(PROBLEMS, {"outcome": "throttled"})
    assert (response.status_code, response["Retry-After"]) == (429, "30")
    assert problem(response)["code"] == "throttled"
    failed = AuthenticationFailed()
    failed.auth_header = 'Bearer realm="api"'  # type: ignore[attr-defined]  # set by DRF's view
    unauthorized = problem_exception_handler(failed, {})
    assert unauthorized.headers["WWW-Authenticate"] == 'Bearer realm="api"'
    assert unauthorized.data["code"] == "authentication_failed"
