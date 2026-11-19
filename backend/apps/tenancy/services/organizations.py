"""Edit the data of the active organization (RF-TEN-03, Q-209, design.md §3.3, §5, §6).

``update_organization(ctx, changes)`` takes any of ``name``, ``legal_name``, ``tax_id`` and
``timezone`` (Q-209); nothing else is a field it writes (``EDITABLE_FIELDS``). The status is not
among them: only the operator's command suspends or reactivates an organization (RN-TEN-18,
AC-TEN-29). Who may call it (owner or admin, ``org.update``) is the route's ``ActionPermission``.

Each value is normalized here, so every caller keeps the same thing (design.md §5): spaces removed
at both ends; ``name`` not empty and up to 120 characters, ``legal_name`` up to 200 (empty clears
it), ``tax_id`` through ``domain/tax_id.py`` (empty clears it), ``timezone`` one of
``zoneinfo.available_timezones()``. A wrong value is ``400 validation_error`` naming the field,
before any lock; the message never repeats the value.

In one transaction: ``ensure_writable`` (``organization_suspended`` if the operator suspended it
after the request was resolved, AC-TEN-28), then the row locked (``lock_organization``) and only the
fields whose value changes are saved, with ``organization.updated`` and their names (never their
values) in the audit. Nothing changed: no write and no event.
"""

from __future__ import annotations

import zoneinfo
from collections.abc import Mapping
from functools import cache

from django.db import transaction
from rest_framework.exceptions import ErrorDetail, ValidationError

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.locks import ensure_writable
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.tax_id import InvalidTaxIdError, normalize_tax_id
from apps.tenancy.models import Organization
from apps.tenancy.selectors.organizations import lock_organization
from apps.tenancy.services.audit import audit_trigger, record_event

EDITABLE_FIELDS = ("name", "legal_name", "tax_id", "timezone")
NAME_MAX_LENGTH = 120
LEGAL_NAME_MAX_LENGTH = 200
UNKNOWN_FIELD = "unknown_field"
UNKNOWN_FIELD_MESSAGE = "Este campo no se puede modificar."


@cache
def _timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def _error(message: str, code: str) -> list[ErrorDetail]:
    return [ErrorDetail(message, code=code)]


def _text(field: str, value: object, errors: dict[str, list[ErrorDetail]]) -> str | None:
    if not isinstance(value, str):
        errors[field] = _error("Tiene que ser un texto.", "invalid")
        return None
    return value.strip()


def _check_length(field: str, value: str, limit: int, errors: dict[str, list[ErrorDetail]]) -> None:
    if len(value) > limit:
        errors[field] = _error(f"Como máximo {limit} caracteres.", "max_length")


def clean_changes(changes: Mapping[str, object]) -> dict[str, str]:
    """The normalized values of ``changes``; ``ValidationError`` with every wrong field."""
    errors: dict[str, list[ErrorDetail]] = {}
    for field in sorted(set(changes) - set(EDITABLE_FIELDS)):
        errors[field] = _error(UNKNOWN_FIELD_MESSAGE, UNKNOWN_FIELD)
    cleaned: dict[str, str] = {}
    for field in EDITABLE_FIELDS:
        if field not in changes:
            continue
        value = _text(field, changes[field], errors)
        if value is None:
            continue
        if field == "name":
            if not value:
                errors[field] = _error("El nombre es obligatorio.", "blank")
            _check_length(field, value, NAME_MAX_LENGTH, errors)
        elif field == "legal_name":
            _check_length(field, value, LEGAL_NAME_MAX_LENGTH, errors)
        elif field == "tax_id":
            try:
                value = normalize_tax_id(value)
            except InvalidTaxIdError:
                errors[field] = _error("No es un CUIT válido.", "invalid")
        elif value not in _timezones():
            errors[field] = _error("No es una zona horaria conocida.", "invalid")
        cleaned[field] = value
    if errors:
        raise ValidationError(errors)
    return cleaned


@audit_trigger(TenancyAuditAction.ORGANIZATION_UPDATED)
def update_organization(ctx: TenantContext, changes: Mapping[str, object]) -> Organization:
    cleaned = clean_changes(changes)
    with transaction.atomic():
        ensure_writable(ctx)
        organization = lock_organization(ctx)
        changed = [
            field for field, value in cleaned.items() if getattr(organization, field) != value
        ]
        if not changed:
            return organization
        for field in changed:
            setattr(organization, field, cleaned[field])
        organization.save(update_fields=[*changed, "updated_at"])
        record_event(
            TenancyAuditAction.ORGANIZATION_UPDATED,
            ctx=ctx,
            metadata={"changed_fields": changed},
        )
    return organization
