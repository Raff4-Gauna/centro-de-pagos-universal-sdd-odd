"""Access log: one ``http.request`` event per request (design.md §3.2.3, AC-PLT-07, RN-PLT-06).

Fields: ``method``, ``route`` (the URL *template*, ``resolver_match.route``, or ``<unmatched>`` when
nothing resolved), ``status`` and ``duration_ms`` (RNF-PLT-03), plus the ``request_id`` bound by
``RequestIdMiddleware``. Never the raw path, the query string, headers or bodies: a path can carry
a semi-secret id (Q-015). Level: DEBUG for /healthz and /readyz (probes every few seconds; a
/readyz 503 already logs ``health.not_ready``), ERROR from 500, INFO otherwise. A 5xx caused by a
view exception carries its traceback, since ``django.request`` is silenced (it logs the raw path).

Streaming responses (N-7 of the T-PLT-12 review): ``duration_ms`` runs until the view returns the
response, i.e. until the headers, not until the body is sent; the body is iterated by the WSGI
server after the middleware chain returned, so events logged while it streams carry no
``request_id``. There is no streaming endpoint yet; when one exists, measure through a closer on
the response.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from django.http import HttpRequest, HttpResponseBase

from apps.common.logging import get_logger

ACCESS_EVENT = "http.request"
UNMATCHED_ROUTE = "<unmatched>"
HEALTH_ROUTES = frozenset({"healthz", "readyz"})

logger = get_logger(__name__)
# The exception of the view, if any, from process_exception to the access event of the request.
_view_exception: ContextVar[Exception | None] = ContextVar("view_exception", default=None)


def _route(request: HttpRequest) -> str:
    match = request.resolver_match
    return match.route if match is not None and match.route else UNMATCHED_ROUTE


def _level(route: str, status: int) -> int:
    if route in HEALTH_ROUTES:
        return logging.DEBUG
    return logging.ERROR if status >= 500 else logging.INFO


class AccessLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        token = _view_exception.set(None)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            route, status = _route(request), response.status_code
            fields: dict[str, Any] = {}
            exception = _view_exception.get()
            if status >= 500 and exception is not None:
                fields["exc_info"] = exception
            logger.log(
                _level(route, status),
                ACCESS_EVENT,
                method=request.method,
                route=route,
                status=status,
                duration_ms=duration_ms,
                **fields,
            )
            return response
        finally:
            _view_exception.reset(token)

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        """Keep the exception for the access event; Django still builds the error response."""
        _view_exception.set(exception)
