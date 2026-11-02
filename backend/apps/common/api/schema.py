"""The OpenAPI contract of the API (ADR-0005, RN-PLT-15, design.md §3.2.4).

``SPECTACULAR_SETTINGS`` comes from ``spectacular_settings()``. The schema is generated from the
public URLconf only (``PUBLIC_URLCONF``, prod's: the dev-only routes of Q-056 never reach it) by
``manage.py export_openapi`` into ``specs/_contracts/openapi.yaml``, which is never edited by hand.
``API_VERSION`` is ``info.version`` (SemVer; no version in the URL, Q-036): an incompatible change
bumps the major, a compatible new field or endpoint the minor, a documentation fix the patch.

Every operation answers ``4XX``/``5XX`` with the ``Problem`` component (``problems.py``, RFC 9457)
unless it declares that range itself. Imported by the settings: no Django or DRF import here.
"""

from __future__ import annotations

from typing import Any

from apps.common.api.problems import PROBLEM_CONTENT_TYPE

API_VERSION = "0.1.0"
PUBLIC_URLCONF = "config.urls"

PROBLEM = "Problem"
FIELD_ERROR = "ProblemFieldError"
_PROBLEM_REF = f"#/components/schemas/{PROBLEM}"
_PLAIN_TEXT = (
    "Puede reflejar lo que envió el cliente: se muestra como texto plano, nunca se interpreta "
    "como HTML."
)
_OPERATIONS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
_DEFAULT_RESPONSES = (("4XX", "Error del cliente"), ("5XX", "Error del servidor"))


def _problem_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"Sobre único de error (RFC 9457), media type {PROBLEM_CONTENT_TYPE}. Sin trazas, "
            "hosts ni secretos."
        ),
        "properties": {
            "type": {"type": "string", "example": "urn:hub:problem:validation_error"},
            "title": {"type": "string", "description": "Fijo para cada code."},
            "status": {"type": "integer", "minimum": 400, "maximum": 599},
            "code": {
                "type": "string",
                "description": "Estable: cambiar o borrar uno publicado es incompatible.",
                "example": "validation_error",
            },
            "detail": {"type": "string", "description": f"Nunca en un 5xx. {_PLAIN_TEXT}"},
            "request_id": {
                "type": "string",
                "nullable": True,
                "description": "El mismo valor que el header X-Request-ID de la respuesta.",
            },
            "errors": {
                "type": "array",
                "description": "Solo en validation_error.",
                "items": {"$ref": f"#/components/schemas/{FIELD_ERROR}"},
            },
        },
        "required": ["type", "title", "status", "code", "request_id"],
    }


def _field_error_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "field": {"type": "string", "example": "amount"},
            "code": {"type": "string", "example": "required"},
            "message": {"type": "string", "description": _PLAIN_TEXT},
        },
        "required": ["field", "code", "message"],
    }


def add_problem_responses(result: dict[str, Any], **kwargs: object) -> dict[str, Any]:
    """drf-spectacular postprocessing hook: ``4XX``/``5XX`` → ``Problem`` where not declared."""
    for path_item in result.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in _OPERATIONS:
                continue
            responses = operation.setdefault("responses", {})
            for status_range, description in _DEFAULT_RESPONSES:
                responses.setdefault(
                    status_range,
                    {
                        "description": description,
                        "content": {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": _PROBLEM_REF}}},
                    },
                )
    return result


def spectacular_settings() -> dict[str, Any]:
    """``SPECTACULAR_SETTINGS``: everything that shapes the contract is fixed here."""
    return {
        "TITLE": "Centro de Pagos Universal API",
        "VERSION": API_VERSION,
        "OAS_VERSION": "3.0.3",
        "SERVE_INCLUDE_SCHEMA": False,
        # The dev-served schema (/api/dev/schema/) is the committed contract, not the dev routes.
        "SERVE_URLCONF": PUBLIC_URLCONF,
        "COMPONENT_SPLIT_REQUEST": True,
        "APPEND_COMPONENTS": {
            "schemas": {PROBLEM: _problem_schema(), FIELD_ERROR: _field_error_schema()}
        },
        "POSTPROCESSING_HOOKS": [
            "drf_spectacular.hooks.postprocess_schema_enums",
            "apps.common.api.schema.add_problem_responses",
        ],
    }
