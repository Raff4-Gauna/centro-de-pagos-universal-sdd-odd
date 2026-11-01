"""Access log: one ``http.request`` event per request (design.md §3.2.3, AC-PLT-07, RN-PLT-06).

Fields: ``method``, ``route`` (the URL *template*, ``resolver_match.route``), ``status`` and
``duration_ms`` (RNF-PLT-03), plus the ``request_id`` bound by ``RequestIdMiddleware``. ``route`` is
``<unmatched>`` when nothing resolved, and also when a middleware answered or failed before URL
resolution (a ``CommonMiddleware`` APPEND_SLASH redirect, an exception in ``process_request``).
Never the raw path, the query string, headers or bodies: a path can carry a semi-secret id (Q-015).
Level: DEBUG for /healthz and /readyz (probes every few seconds; a /readyz 503 already logs
``health.not_ready``), ERROR from 500, INFO otherwise.

An unhandled exception anywhere inside this middleware (view, inner middleware, ``process_view``,
URLconf, template response) reaches the event through Django's ``got_request_exception``, since
``django.request`` is silenced (it logs the raw path). Only its type, the types of its
``__cause__``/``__context__`` chain (``module.QualName``, builtins bare, at most ``MAX_CHAIN``) and
its frames (``path:line in function``, the path relative to ``site-packages`` or ``BASE_DIR``, so no
system user nor image layout shows) are logged, never a message: a message can carry a URL with a
token, a Redis URL with its password, a raw path or a pydantic ``input_value`` (C-06; same rule as
``health.not_ready``).

Not in the access log: responses of the middlewares *before* this one, e.g. the HTTPS redirects of
``SecurityMiddleware`` in prod. Streaming responses (N-7 of the T-PLT-12 review): ``duration_ms``
runs until the view returns the response (the headers), not until the body is sent; the WSGI server
iterates the body after the middleware chain returned, so events logged while it streams carry no
``request_id``. There is no streaming endpoint yet; when one exists, measure through a closer.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from django.conf import settings
from django.core.signals import got_request_exception
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponseBase

from apps.common.logging import get_logger

ACCESS_EVENT = "http.request"
UNMATCHED_ROUTE = "<unmatched>"
HEALTH_ROUTES = frozenset({"healthz", "readyz"})
MAX_FRAMES = 30
MAX_CHAIN = 10
_PACKAGE_DIRS = ("/site-packages/", "/dist-packages/")

logger = get_logger(__name__)
# The unhandled exception of the current request, from got_request_exception to the access event.
_request_exception: ContextVar[BaseException | None] = ContextVar("request_exception", default=None)


@receiver(got_request_exception, dispatch_uid="apps.common.access_log")
def _keep_request_exception(sender: object, **kwargs: object) -> None:
    """Sent by Django inside its ``except`` block, so ``sys.exc_info()`` is the exception."""
    _request_exception.set(sys.exc_info()[1])


def _type_name(error: BaseException) -> str:
    kind = type(error)
    return (
        kind.__qualname__
        if kind.__module__ == "builtins"
        else f"{kind.__module__}.{kind.__qualname__}"
    )


def _short_path(filename: str) -> str:
    """``django/core/handlers/base.py`` or ``apps/...``: never an absolute path."""
    path = filename.replace("\\", "/")
    for marker in _PACKAGE_DIRS:
        if marker in path:
            return path.rsplit(marker, 1)[1]
    base = str(settings.BASE_DIR).replace("\\", "/").rstrip("/") + "/"
    if path.lower().startswith(base.lower()):
        return path[len(base) :]
    return path.rsplit("/", 1)[-1]  # the standard library or anything else: the file name only


def describe_exception(error: BaseException) -> dict[str, Any]:
    """Type, chain of cause types and frames of ``error``; never its message nor its args."""
    chain: list[str] = []
    seen = {id(error)}
    cause = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    while cause is not None and id(cause) not in seen and len(chain) < MAX_CHAIN:
        seen.add(id(cause))
        chain.append(_type_name(cause))
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    frames = traceback.extract_tb(error.__traceback__)[-MAX_FRAMES:]
    return {
        "exception_type": _type_name(error),
        "exception_chain": chain,
        "exception_frames": [f"{_short_path(f.filename)}:{f.lineno} in {f.name}" for f in frames],
    }


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
        _request_exception.set(None)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            route, status = _route(request), response.status_code
            exception = _request_exception.get()
            fields = (
                describe_exception(exception) if status >= 500 and exception is not None else {}
            )
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
            # set, not reset: reset would bring back an exception signalled before this request
            # (an outer middleware, a command) and keep it, with its frames, alive in the context.
            _request_exception.set(None)
