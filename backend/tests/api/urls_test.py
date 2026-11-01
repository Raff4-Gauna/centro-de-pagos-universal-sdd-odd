"""URLs used only by API-level tests: ``@pytest.mark.urls("tests.api.urls_test")``.

The public routes plus views that log through structlog and through a plain stdlib logger, one
that fails, and one with a path parameter that answers the status asked for in ``?outcome=``, so the
tests see what a real request leaves on stdout and in the response headers. ``ExplodingMiddleware``
fails outside any view, for the tests that add it to ``MIDDLEWARE``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponseBase, JsonResponse
from django.urls import URLPattern, URLResolver, path

from apps.common.logging import get_logger
from config.urls import urlpatterns as public_urlpatterns

STRUCTLOG_EVENT = "test.structlog_event"
STDLIB_EVENT = "test.stdlib_event"
# Stand-in for what an exception message may carry (a URL with a token, a Redis URL with its
# password, a raw path, a pydantic input_value). Pieces joined at runtime.
LEAK_SENTINEL = "leak-sentinel-5d1e"

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
    if outcome == "leaky":
        raise_leaky_chain()
    return JsonResponse({"status": "ok"})


def raise_leaky_chain() -> None:
    try:
        raise ValueError("input_value=" + repr(LEAK_SENTINEL + "-cause"))
    except ValueError as cause:
        message = " ".join(
            [
                "https://api.example/v1?access_" + "token=" + LEAK_SENTINEL + "-token",
                "redis://:" + LEAK_SENTINEL + "-pass@redis.example:6379/0",
                "/items/" + LEAK_SENTINEL + "-path",
            ]
        )
        raise RuntimeError(message) from cause


class ExplodingMiddleware:
    """Fails outside the view: in ``__call__`` (``?explode=call``) or ``process_view``
    (``?explode=view``), where Django calls no ``process_exception``."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        if request.GET.get("explode") == "call":
            raise RuntimeError("test.middleware_failure")
        return self.get_response(request)

    def process_view(
        self, request: HttpRequest, view: Callable[..., Any], args: Any, kwargs: Any
    ) -> None:
        if request.GET.get("explode") == "view":
            raise RuntimeError("test.process_view_failure")


urlpatterns: list[URLPattern | URLResolver] = [
    *public_urlpatterns,
    path("test/log", log_events, name="test-log"),
    path("test/error", fail, name="test-error"),
    path("test/items/<str:item_id>", item, name="test-item"),
]
