"""AC-PLT-08 (RN-PLT-06, C-06): no secret of a request reaches any log line (T-PLT-14).

A request with ``Authorization: Bearer``, ``Cookie`` and a query string, to a route with a path
parameter, through the whole middleware chain to a view that logs *carelessly* (the request object,
its headers, the credentials themselves), through structlog and through a stdlib logger: no value
shows on stdout or stderr, and the access log has the route template. The redaction processor
(``logging/processors.py``) runs on every event of both kinds, after the traceback is rendered.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from django.http import HttpRequest, JsonResponse
from django.test import Client
from django.urls import path

from apps.common.domain.redaction import REDACTED
from apps.common.logging import get_logger
from apps.common.middleware.access_log import ACCESS_EVENT
from tests.logging.conftest import StdoutLog

# Pieces joined at runtime (gitleaks; and so no source line spells a whole value).
BEARER = "bearer-sentinel-" + "a41f"
COOKIE = "cookie-sentinel-" + "77d0"
QUERY = "query-sentinel-" + "0b9e"
QUERY_TOKEN = "qtoken-sentinel-" + "c3d2"
PATH = "path-sentinel-" + "5e61"
PASSWORD = "pass-sentinel-" + "19aa"
SENTINELS = (BEARER, COOKIE, QUERY, QUERY_TOKEN, PATH, PASSWORD)
ROUTE = "redaction/<str:item_id>"
CARELESS_EVENT = "test.careless"
CARELESS_STDLIB_EVENT = "test.careless_stdlib"
REDIS_URL = "redis://:" + PASSWORD + "@redis.example:6379/0"

logger = get_logger(__name__)
stdlib_logger = logging.getLogger("tests.logging.careless")


def careless_view(request: HttpRequest, item_id: str) -> JsonResponse:
    """Logs what code must never log; the redaction is the net under the rule."""
    logger.info(
        CARELESS_EVENT,
        request=request,  # its repr: "<WSGIRequest: GET '/redaction/<path>?q=<query>'>"
        headers=dict(request.headers),
        authorization=request.headers.get("Authorization"),
        access_token=request.GET.get("access_token"),
    )
    stdlib_logger.info(
        CARELESS_STDLIB_EVENT,
        extra={"cookie": request.headers.get("Cookie"), "request": request},
    )
    return JsonResponse({"status": "ok"})


# This module is the URLconf of its own tests: @pytest.mark.urls(__name__).
urlpatterns = [path(ROUTE, careless_view)]
pytestmark = pytest.mark.urls(__name__)


def send_request_with_secrets() -> None:
    response = Client().get(
        f"/redaction/{PATH}?q={QUERY}&access_token={QUERY_TOKEN}",
        HTTP_AUTHORIZATION=f"Bearer {BEARER}",
        HTTP_COOKIE=f"sessionid={COOKIE}; csrftoken={COOKIE}",
    )
    assert response.status_code == 200


def only(events: list[dict[str, Any]]) -> dict[str, Any]:
    (event,) = events
    return event


def assert_no_sentinel(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text, sentinel


def test_AC_PLT_08_bearer_cookie_and_query_never_logged(stdout_log: StdoutLog) -> None:
    send_request_with_secrets()
    log = stdout_log.read()
    assert_no_sentinel(log.out + log.err)
    careless = only(log.find(CARELESS_EVENT))
    assert careless["authorization"] == REDACTED
    assert careless["headers"]["Authorization"] == REDACTED
    assert careless["headers"]["Cookie"] == REDACTED
    assert careless["request"] == "<WSGIRequest>"
    assert careless["access_token"] == REDACTED
    assert only(log.find(CARELESS_STDLIB_EVENT))["cookie"] == REDACTED


def test_AC_PLT_08_access_log_shows_route_template_not_raw_path(stdout_log: StdoutLog) -> None:
    send_request_with_secrets()
    access = only(stdout_log.read().find(ACCESS_EVENT))
    assert (access["route"], access["status"]) == (ROUTE, 200)
    assert_no_sentinel(repr(access))


def test_AC_PLT_08_redacts_nested_secret_like_keys(stdout_log: StdoutLog) -> None:
    # N-3 (T-PLT-12 review): by key on both paths, structlog kwargs and stdlib extra=.
    logger.info(
        "demo.nested",
        provider={"name": "mp", "credentials": {"access_token": QUERY_TOKEN}},
        attempts=[{"client_secret": PASSWORD, "status": 401}],
        api_key=BEARER,
    )
    logging.getLogger("thirdparty.sdk").warning(
        "demo.stdlib", extra={"password": PASSWORD, "x_api_key": BEARER, "status": 401}
    )
    log = stdout_log.read()
    assert_no_sentinel(log.out + log.err)
    nested = only(log.find("demo.nested"))
    assert nested["provider"] == {"name": "mp", "credentials": REDACTED}
    assert nested["attempts"] == [{"client_secret": REDACTED, "status": 401}]
    assert nested["api_key"] == REDACTED
    stdlib = only(log.find("demo.stdlib"))
    assert (stdlib["password"], stdlib["x_api_key"], stdlib["status"]) == (REDACTED, REDACTED, 401)


def test_AC_PLT_08_location_and_url_credentials_are_redacted(stdout_log: StdoutLog) -> None:
    # T-PLT-12 review: a cache LOCATION and any URL with user:password, in fields and messages.
    logger.info("demo.cache", location=REDIS_URL, broker=REDIS_URL, caches={"LOCATION": REDIS_URL})
    logging.getLogger("thirdparty.redis").warning("connecting to %s", REDIS_URL)
    log = stdout_log.read()
    assert_no_sentinel(log.out + log.err)
    cache = only(log.find("demo.cache"))
    assert cache["location"] == REDACTED
    assert cache["caches"] == {"LOCATION": REDACTED}
    assert cache["broker"] == f"redis://{REDACTED}@redis.example:6379/0"
    assert only(log.find(f"connecting to redis://{REDACTED}@redis.example:6379/0"))


def test_AC_PLT_08_traceback_text_is_redacted_too(stdout_log: StdoutLog) -> None:
    # The processor runs after format_exc_info: the rendered traceback is a string like any other.
    try:
        raise ConnectionError(f"cannot reach {REDIS_URL} with password={PASSWORD}")
    except ConnectionError:
        logging.getLogger("thirdparty.redis").exception("demo.failed")
    log = stdout_log.read()
    assert_no_sentinel(log.out + log.err)
    exception = only(log.find("demo.failed"))["exception"]
    assert "ConnectionError: cannot reach redis://[REDACTED]@redis.example" in exception
