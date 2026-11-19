"""Create a branch in the active organization (RF-TEN-06, RN-TEN-04, RN-TEN-19, design.md §5, §6).

``create_branch(ctx, fields)`` takes ``name`` (required), ``code`` and ``address`` (optional) and
nothing else (``CREATE_FIELDS``). Any other key (``organization_id``, ``is_active``, ``id``, a typo)
is ``400 validation_error`` with code ``unknown_field`` on that key (``services/fields.py``), and
nothing is written: the
organization of the new branch is always the one of ``ctx``, never one the client names
(RN-TEN-04, AC-TEN-07). Who may call it (owner or admin, ``branch.create``) is the route's
``ActionPermission`` (AC-TEN-16).

The service validates on its own, for any caller and not only the API: spaces removed at both
ends (design.md §5), ``name`` not empty and up to 120 characters, ``code`` up to 32 and ``address``
up to 255 (empty is "not informed"). A wrong value is ``400 validation_error`` naming the field,
before any lock; the message never repeats the value.

In one transaction: ``ensure_writable`` (``organization_suspended`` if the operator suspended the
organization after the request was resolved, AC-TEN-28), the insert, and ``branch.created`` in the
audit with the id of the branch. Uniqueness among active branches is the database's
(``branch_unique_active_name`` without case, Q-226; ``branch_unique_active_code``, Q-227): checking
first and inserting after would let two concurrent requests through. Its ``IntegrityError`` is
``409 conflict`` naming the field (AC-TEN-38); the insert runs in a savepoint, so the transaction
is still usable, and nothing is audited. Any other integrity error is a bug and goes up as is.
"""

from __future__ import annotations

from collections.abc import Mapping

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.locks import ensure_writable
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Branch
from apps.tenancy.models.branch import ADDRESS_MAX_LENGTH, CODE_MAX_LENGTH, NAME_MAX_LENGTH
from apps.tenancy.services.audit import audit_trigger, record_event
from apps.tenancy.services.fields import unknown_field_errors

CREATE_FIELDS: Mapping[str, int] = {
    "name": NAME_MAX_LENGTH,
    "code": CODE_MAX_LENGTH,
    "address": ADDRESS_MAX_LENGTH,
}

# Constraint of the database → the field whose value is taken (design.md §5).
_UNIQUE_FIELDS = {
    "branch_unique_active_name": "name",
    "branch_unique_active_code": "code",
}
_TAKEN = {
    "name": "Ya hay una sucursal activa con ese nombre.",
    "code": "Ya hay una sucursal activa con ese código.",
}


class BranchConflict(APIException):
    """``409 conflict``: the name or the code is already used by an active branch (AC-TEN-38)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Ya hay una sucursal activa con esos datos."


def _error(message: str, code: str) -> list[ErrorDetail]:
    return [ErrorDetail(message, code=code)]


def clean_new_branch(fields: Mapping[str, object]) -> dict[str, str]:
    """The normalized values of ``fields``; ``ValidationError`` with every wrong field."""
    errors = unknown_field_errors(fields, CREATE_FIELDS)
    cleaned: dict[str, str] = {}
    for field, limit in CREATE_FIELDS.items():
        if field not in fields:
            if field == "name":
                errors[field] = _error("El nombre es obligatorio.", "required")
            continue
        value = fields[field]
        if not isinstance(value, str):
            errors[field] = _error("Tiene que ser un texto.", "invalid")
            continue
        value = value.strip()
        if field == "name" and not value:
            errors[field] = _error("El nombre es obligatorio.", "blank")
        elif len(value) > limit:
            errors[field] = _error(f"Como máximo {limit} caracteres.", "max_length")
        cleaned[field] = value
    if errors:
        raise ValidationError(errors)
    return cleaned


def _conflict(error: IntegrityError) -> BranchConflict | None:
    diagnostics = getattr(error.__cause__, "diag", None)
    field = _UNIQUE_FIELDS.get(str(getattr(diagnostics, "constraint_name", None)))
    if field is None:
        return None
    return BranchConflict(detail=_TAKEN[field], code="conflict")


@audit_trigger(TenancyAuditAction.BRANCH_CREATED)
def create_branch(ctx: TenantContext, fields: Mapping[str, object]) -> Branch:
    cleaned = clean_new_branch(fields)
    with transaction.atomic():
        ensure_writable(ctx)
        try:
            with transaction.atomic():
                branch = Branch.objects.for_tenant(ctx).create(**cleaned)
        except IntegrityError as error:
            if (conflict := _conflict(error)) is None:
                raise
            raise conflict from None
        record_event(
            TenancyAuditAction.BRANCH_CREATED, ctx=ctx, metadata={"branch_id": str(branch.pk)}
        )
    return branch
