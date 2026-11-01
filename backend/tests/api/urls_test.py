"""URLs used only by API-level tests: ``@pytest.mark.urls("tests.api.urls_test")``.

The public routes plus views that log through structlog and through a plain stdlib logger, one
that fails, and one with a path parameter that answers the status asked for in ``?outcome=``, so the
tests see what a real request leaves on stdout and in the response headers.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, path

from apps.common.logging import get_logger
from config.urls import urlpatterns as public_urlpatterns

STRUCTLOG_EVENT = "test.structlog_event"
STDLIB_EVENT = "test.stdlib_event"

logger = get_logger(__name__)
stdlib_logger = logging.getLogger("tests.api.stdlib")


def log_events(request: HttpRequest) -> JsonResponse:
    logger.info(STRUCTLOG_EVENT)
    stdlib_logger.info(STDLIB_EVENT)
    return JsonResponse({"status": "ok"})


def fail(request: HttpRequest) -> JsonResponse:
    raise RuntimeError("test.failure")


def item(request: HttpRequest, item_id: str) -> JsonResponse:
    # Never echoes item_id: the tests check it reaches no log line.
    outcome = request.GET.get("outcome", "200")
    if outcome == "400":
        raise SuspiciousOperation("test.suspicious")
    if outcome == "403":
        raise PermissionDenied
    if outcome == "404":
        raise Http404
    if outcome == "500":
        raise RuntimeError("test.failure")
    return JsonResponse({"status": "ok"})


urlpatterns: list[URLPattern | URLResolver] = [
    *public_urlpatterns,
    path("test/log", log_events, name="test-log"),
    path("test/error", fail, name="test-error"),
    path("test/items/<str:item_id>", item, name="test-item"),
]
