"""Strict bodies: a key the operation does not take is an error, never ignored (design.md §6).

Every write of SPEC-02 that takes a body rejects a field that is unknown or read-only
(``organization_id``, ``status``, ``id``, a typo) with ``400 validation_error`` and the code
``unknown_field`` on that key, and writes nothing (AC-TEN-07, AC-TEN-29). ``unknown_field_errors``
is that one rule, shared by the services that validate a body and the serializers that check one.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from rest_framework.exceptions import ErrorDetail

UNKNOWN_FIELD = "unknown_field"
UNKNOWN_FIELD_MESSAGE = "Este campo no se acepta."


def unknown_field_errors(
    keys: Iterable[object], allowed: Collection[str]
) -> dict[str, list[ErrorDetail]]:
    """One ``unknown_field`` error per key (of a body) outside ``allowed``, sorted by key."""
    unknown = sorted(str(key) for key in keys if key not in allowed)
    return {key: [ErrorDetail(UNKNOWN_FIELD_MESSAGE, code=UNKNOWN_FIELD)] for key in unknown}
