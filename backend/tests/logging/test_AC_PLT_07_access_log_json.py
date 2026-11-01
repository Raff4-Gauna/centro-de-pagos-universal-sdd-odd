"""AC-PLT-07 (RN-PLT-05/06, RNF-PLT-03): the access log line of every request (T-PLT-13).

One ``http.request`` JSON event with the required fields, ``method``, the route *template*,
``status`` and ``duration_ms``; its ``request_id`` is the ``X-Request-ID`` of the response.
RN-PLT-06 (T-PLT-12 review N-1): no line on stdout or stderr carries the raw path or the query
string, for any status: ``django.request``, ``django.security.csrf`` and ``django.server`` are
silenced.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from django.conf import settings
from django.test import Client

from apps.common.logging.setup import configure_logging, logging_config
from apps.common.middleware.access_log import ACCESS_EVENT, UNMATCHED_ROUTE
from apps.common.middleware.request_id import REQUEST_ID_HEADER
from tests.conftest import RunDjango
from tests.logging.conftest import StdoutLog

ITEM_ROUTE = "test/items/<str:item_id>"
# Stand-ins for a semi-secret id in a path (Q-015) and a token in a query string.
PATH_SENTINEL = "seg-sentinel-7f3a"
QUERY_SENTINEL = "qs-sentinel-91c2"

pytestmark = pytest.mark.urls("tests.api.urls_test")


def access_event(stdout_log: StdoutLog) -> dict[str, Any]:
    (event,) = stdout_log.read().find(ACCESS_EVENT)
    return event


@pytest.fixture
def debug_level() -> Iterator[None]:
    configure_logging(logging_config("DEBUG"))
    yield
    configure_logging(settings.LOGGING)


def test_AC_PLT_07_line_is_valid_json_with_required_fields_and_utc_timestamp(
    client: Client, stdout_log: StdoutLog
) -> None:
    client.get("/test/items/abc")
    event = access_event(stdout_log)
    assert {"timestamp", "level", "component", "message", "request_id"} <= event.keys()
    assert event["component"] == "apps.common.middleware.access_log"
    timestamp = datetime.fromisoformat(event["timestamp"])
    assert timestamp.utcoffset() == UTC.utcoffset(None)


def test_AC_PLT_07_access_log_has_method_route_status_duration_ms(
    client: Client, stdout_log: StdoutLog
) -> None:
    client.post("/test/items/abc?outcome=200")
    event = access_event(stdout_log)
    assert (event["method"], event["route"], event["status"]) == ("POST", ITEM_ROUTE, 200)
    assert event["level"] == "info"
    assert isinstance(event["duration_ms"], int | float)
    assert event["duration_ms"] >= 0


def test_AC_PLT_07_request_id_equals_response_header(client: Client, stdout_log: StdoutLog) -> None:
    response = client.get("/test/items/abc")
    assert access_event(stdout_log)["request_id"] == response[REQUEST_ID_HEADER]


def test_AC_PLT_07_unmatched_route_logs_placeholder(client: Client, stdout_log: StdoutLog) -> None:
    response = client.get(f"/no/such/{PATH_SENTINEL}")
    assert response.status_code == 404
    event = access_event(stdout_log)
    assert (event["route"], event["status"], event["level"]) == (UNMATCHED_ROUTE, 404, "info")


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_AC_PLT_07_health_requests_logged_at_debug(
    client: Client, stdout_log: StdoutLog, path: str
) -> None:
    client.get(path)  # /readyz is 503 here (LocMemCache, no Redis): still DEBUG
    assert stdout_log.read().find(ACCESS_EVENT) == []  # hidden at the default INFO level


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_AC_PLT_07_health_requests_shown_at_debug_level(
    client: Client, stdout_log: StdoutLog, debug_level: None, path: str
) -> None:
    client.get(path)
    event = access_event(stdout_log)
    assert (event["route"], event["level"]) == (path.lstrip("/"), "debug")


def test_AC_PLT_07_5xx_logged_at_error(stdout_log: StdoutLog) -> None:
    response = Client(raise_request_exception=False).get("/test/items/abc?outcome=500")
    assert response.status_code == 500
    event = access_event(stdout_log)
    assert (event["level"], event["status"], event["route"]) == ("error", 500, ITEM_ROUTE)
    # django.request is silenced, so the traceback travels with the access event.
    assert "RuntimeError: test.failure" in event["exception"]


@pytest.mark.parametrize(
    ("method", "outcome", "status", "route"),
    [
        ("get", "404", 404, ITEM_ROUTE),  # Http404 raised by a resolved view
        ("get", None, 404, UNMATCHED_ROUTE),  # nothing resolved
        ("get", "400", 400, ITEM_ROUTE),  # SuspiciousOperation
        ("get", "403", 403, ITEM_ROUTE),  # PermissionDenied
        ("post", "200", 403, ITEM_ROUTE),  # CSRF rejection (django.security.csrf)
        ("get", "500", 500, ITEM_ROUTE),
    ],
)
def test_RN_PLT_06_no_raw_path_for_404_400_403_500(
    stdout_log: StdoutLog, method: str, outcome: str | None, status: int, route: str
) -> None:
    client = Client(enforce_csrf_checks=True, raise_request_exception=False)
    prefix = "/test/items" if outcome else "/test/nowhere"
    query = f"outcome={outcome}&token={QUERY_SENTINEL}" if outcome else f"token={QUERY_SENTINEL}"
    response = getattr(client, method)(f"{prefix}/{PATH_SENTINEL}?{query}")
    assert response.status_code == status
    log = stdout_log.read()
    for leak in (PATH_SENTINEL, QUERY_SENTINEL, "token="):
        assert leak not in log.out + log.err, leak
    (event,) = log.find(ACCESS_EVENT)
    assert (event["route"], event["status"]) == (route, status)


# pytest attaches its capture handlers to every logger, which hides logging's lastResort (it writes
# WARNING+ of a logger without handlers to stderr). A plain interpreter shows whether a silenced
# logger really writes nothing.
SILENCED_PROBE = f"""
import django
from django.test import Client
from django.test.utils import override_settings
django.setup()
with override_settings(ROOT_URLCONF="tests.api.urls_test"):
    client = Client(HTTP_HOST="localhost", enforce_csrf_checks=True, raise_request_exception=False)
    for outcome in ("404", "403", "500"):
        client.get("/test/items/{PATH_SENTINEL}?outcome=" + outcome + "&token={QUERY_SENTINEL}")
    client.post("/test/items/{PATH_SENTINEL}")
"""


def test_RN_PLT_06_silenced_loggers_write_nothing_outside_pytest(run_django: RunDjango) -> None:
    result = run_django(
        "-c",
        SILENCED_PROBE,
        settings_module="config.settings.test",
        values={
            "DJANGO_SECRET_KEY": "test-only-not-a-secret",
            "DATABASE_URL": "postgres://db.example/hub",
            "REDIS_URL": "redis://redis.example:6379/0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    statuses = [json.loads(line)["status"] for line in result.stdout.splitlines()]
    assert statuses == [404, 403, 500, 403]  # only the access log lines
    for leak in (PATH_SENTINEL, QUERY_SENTINEL):
        assert leak not in result.stdout
