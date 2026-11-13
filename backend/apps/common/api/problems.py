"""The ``application/problem+json`` envelope of every API error (RFC 9457, RN-PLT-15, Q-036).

Pure (no Django, no DRF): ``api/exceptions.py`` turns exceptions into ``build_problem`` calls.
Fields (design.md §3.2.4, §6.2): ``type`` (``urn:hub:problem:<code>``), ``title`` (fixed per code),
``status``, ``code``, ``detail`` (never on a 5xx), ``request_id`` and, for ``validation_error``
only, ``errors[]`` of ``field``/``code``/``message``. ``code`` is the contract: changing or removing
a published one is incompatible (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from http import HTTPStatus
from typing import Any

PROBLEM_CONTENT_TYPE = "application/problem+json"
TYPE_PREFIX = "urn:hub:problem:"
INTERNAL_ERROR = "internal_error"
NOT_FOUND = "not_found"
VALIDATION_ERROR = "validation_error"
# Code of a validation message that carries none (DRF's ValidationError default).
DEFAULT_MESSAGE_CODE = "invalid"

TITLES: Mapping[str, str] = {
    VALIDATION_ERROR: "Datos inválidos",
    "parse_error": "Solicitud mal formada",
    "not_authenticated": "No autenticado",
    "authentication_failed": "Autenticación fallida",
    "permission_denied": "Permiso denegado",
    NOT_FOUND: "No encontrado",
    "method_not_allowed": "Método no permitido",
    "not_acceptable": "Formato de respuesta no disponible",
    "unsupported_media_type": "Tipo de contenido no soportado",
    "throttled": "Demasiadas solicitudes",
    # SPEC-01 (design.md §6.1): codes of auth/bff/*.
    "rate_limited": "Demasiadas solicitudes",
    "login_disabled": "Ingreso deshabilitado",
    "google_auth_failed": "Ingreso con Google fallido",
    "login_cancelled": "Ingreso cancelado",
    "google_unavailable": "Google no disponible",
    "email_not_verified": "Email no verificado",
    "not_invited": "Sin invitación",
    "user_inactive": "Usuario desactivado",
    "identity_conflict": "Conflicto de identidad",
    INTERNAL_ERROR: "Error interno",
}


def _title(code: str, status: int) -> str:
    if code in TITLES:
        return TITLES[code]
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def build_problem(
    *,
    code: str,
    status: int,
    request_id: str | None,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """The envelope; ``detail`` is dropped from any 5xx, whatever the caller passed."""
    problem: dict[str, Any] = {
        "type": TYPE_PREFIX + code,
        "title": _title(code, status),
        "status": status,
        "code": code,
    }
    if detail and status < HTTPStatus.INTERNAL_SERVER_ERROR:
        problem["detail"] = detail
    problem["request_id"] = request_id
    if errors is not None:
        problem["errors"] = errors
    return problem


def validation_errors(detail: object, non_field_key: str) -> list[dict[str, str]]:
    """``errors[]`` from the details of a validation error.

    ``detail`` is a message (a ``str``, its ``code`` attribute if it has one, like DRF's
    ``ErrorDetail``), a list of them or a mapping of field to either, nested for nested
    serializers. Keys join with ``.``; a list item that holds fields adds its index
    (``items.0.amount``). A message outside any field goes under ``non_field_key``.
    """
    return [
        {"field": field or non_field_key, "code": code, "message": message}
        for field, code, message in _flatten(detail, None)
    ]


def _join(field: str | None, key: object) -> str:
    return str(key) if field is None else f"{field}.{key}"


def _flatten(detail: object, field: str | None) -> Iterator[tuple[str | None, str, str]]:
    if isinstance(detail, Mapping):
        for key, value in detail.items():
            yield from _flatten(value, _join(field, key))
    elif isinstance(detail, list | tuple):
        for index, item in enumerate(detail):
            nested = isinstance(item, Mapping | list | tuple)
            yield from _flatten(item, _join(field, index) if nested else field)
    else:
        code = getattr(detail, "code", None) or DEFAULT_MESSAGE_CODE
        yield field, str(code), str(detail)
