"""DRF ``EXCEPTION_HANDLER`` and Django ``handler404``/``handler500``: every API error is one
``application/problem+json`` envelope (design.md §3.2.4, RN-PLT-15, AC-PLT-34).

DRF views: an ``APIException`` keeps its status, its ``code`` (``get_codes()`` when that is one
string, else the class default; a ``ValidationError`` is ``validation_error`` with ``errors[]``) and
the headers DRF would send (``WWW-Authenticate``, ``Retry-After``). Django's ``Http404`` and
``PermissionDenied`` become ``not_found``/``permission_denied`` *without* their message (it may name
a model or an id). Anything else is ``500 internal_error`` without detail, also with ``DEBUG``. The
handler runs inside DRF's ``except``, so it sends ``got_request_exception`` there: the access log
keeps the exception type and frames under the same ``request_id`` (T-PLT-13 review N-5), and the
test client re-raises it unless built with ``raise_request_exception=False``. Like DRF, it rolls
back an ``ATOMIC_REQUESTS`` transaction.

``not_found``/``server_error`` (``config.urls``; Django uses them only with ``DEBUG=False``): the
same envelope for paths under ``/api/`` (an unknown route, a plain Django view that fails), Django's
own pages elsewhere. Django already sent ``got_request_exception`` before calling ``server_error``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.signals import got_request_exception
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views import defaults
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import set_rollback

from apps.common.api.problems import (
    INTERNAL_ERROR,
    NOT_FOUND,
    PROBLEM_CONTENT_TYPE,
    VALIDATION_ERROR,
    build_problem,
    validation_errors,
)
from apps.common.logging.context import current_request_id

API_PREFIX = "/api/"


def problem_exception_handler(exc: Exception, context: Mapping[str, Any]) -> Response:
    """``REST_FRAMEWORK["EXCEPTION_HANDLER"]``: never returns ``None`` (nothing reaches Django)."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    set_rollback()
    if not isinstance(exc, exceptions.APIException):
        request = context.get("request")
        got_request_exception.send(sender=None, request=getattr(request, "_request", request))
        problem = build_problem(code=INTERNAL_ERROR, status=500, request_id=current_request_id())
        return _response(problem, 500, {})
    headers = {}
    if auth_header := getattr(exc, "auth_header", None):
        headers["WWW-Authenticate"] = str(auth_header)
    if wait := getattr(exc, "wait", None):
        headers["Retry-After"] = str(int(wait))
    return _response(_api_problem(exc), exc.status_code, headers)


def _api_problem(exc: exceptions.APIException) -> dict[str, Any]:
    if isinstance(exc, exceptions.ValidationError):
        errors = validation_errors(exc.detail, api_settings.NON_FIELD_ERRORS_KEY)
        return build_problem(
            code=VALIDATION_ERROR,
            status=exc.status_code,
            request_id=current_request_id(),
            errors=errors,
        )
    codes = exc.get_codes()
    return build_problem(
        code=codes if isinstance(codes, str) else str(exc.default_code),
        status=exc.status_code,
        request_id=current_request_id(),
        detail=exc.detail if isinstance(exc.detail, str) else None,
    )


def _response(problem: dict[str, Any], status: int, headers: dict[str, str]) -> Response:
    return Response(problem, status=status, headers=headers, content_type=PROBLEM_CONTENT_TYPE)


def _is_api(request: HttpRequest) -> bool:
    return (request.path_info.rstrip("/") + "/").startswith(API_PREFIX)


def _plain_problem(code: str, status: int, detail: str | None = None) -> JsonResponse:
    request_id = current_request_id()
    problem = build_problem(code=code, status=status, request_id=request_id, detail=detail)
    return JsonResponse(problem, status=status, content_type=PROBLEM_CONTENT_TYPE)


def not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """``handler404``: the exception's message never reaches the body."""
    if not _is_api(request):
        return defaults.page_not_found(request, exception)
    return _plain_problem(NOT_FOUND, 404, str(exceptions.NotFound.default_detail))


def server_error(request: HttpRequest) -> HttpResponse:
    """``handler500``."""
    if not _is_api(request):
        return defaults.server_error(request)
    return _plain_problem(INTERNAL_ERROR, 500)
