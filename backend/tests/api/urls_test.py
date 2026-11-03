"""URLs used only by API-level tests: ``@pytest.mark.urls("tests.api.urls_test")``.

The public routes plus views that log through structlog and through a plain stdlib logger, and one
that fails, so the tests see what a real request leaves on stdout and in the response headers.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse
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


urlpatterns: list[URLPattern | URLResolver] = [
    *public_urlpatterns,
    path("test/log", log_events, name="test-log"),
    path("test/error", fail, name="test-error"),
]
