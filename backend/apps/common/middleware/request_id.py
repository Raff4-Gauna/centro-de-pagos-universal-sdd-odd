"""``RequestIdMiddleware``: the ``request_id`` of every request (RN-PLT-07, AC-PLT-09, Q-041).

First in ``MIDDLEWARE``, so every log event of the request, from any middleware or view, carries the
id. The incoming ``X-Request-ID`` is kept only when it is a valid UUIDv4 (normalised to lower case);
otherwise a new one is generated (``domain.request_id``). The id is bound to the logging context for
the request and returned on **every** response: Django turns an exception of the inner layers into
a response before it reaches this middleware, so 404/500 carry it too. The context is cleared at the
start and at the end, so nothing leaks to the next request served by the same thread.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase

from apps.common.domain.request_id import resolve_request_id
from apps.common.logging import context

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        context.bind_request(request_id)
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            context.clear()
