"""Create, edit, deactivate and reactivate a branch (RF-TEN-06, RN-TEN-04, RN-TEN-19, §5, §6).

``create_branch(ctx, fields)`` takes ``name`` (required), ``code`` and ``address`` (optional);
``update_branch(ctx, branch_id, changes)`` takes any of them. Nothing else (``CREATE_FIELDS``):
any other key (``organization_id``, ``is_active``, ``id``, a typo) is ``400 validation_error``
with code ``unknown_field`` on that key (``services/fields.py``), and nothing is written: the
organization of a branch is always the one of ``ctx``, never one the client names (RN-TEN-04,
AC-TEN-07), and its state changes only through deactivate and reactivate. Who may call each one
(owner or admin, ``branch.create``/``update``/``deactivate``/``reactivate``) is the route's
``ActionPermission`` (AC-TEN-05, AC-TEN-16).

The service validates on its own, for any caller and not only the API: spaces removed at both
ends (design.md §5), ``name`` not empty and up to 120 characters, ``code`` up to 32 and ``address``
up to 255 (empty is "not informed"). A wrong value is ``400 validation_error`` naming the field,
before any lock; the message never repeats the value.

Every write runs in one transaction: ``ensure_writable`` (``organization_suspended`` if the operator
suspended the organization after the request was resolved, AC-TEN-28), the branch locked by
``selectors/branches.py::lock_branch`` (``404 not_found`` for one of another organization,
AC-TEN-01), the write and its event in the audit. Uniqueness among active branches is the
database's (``branch_unique_active_name`` without case, Q-226; ``branch_unique_active_code``,
Q-227): checking first and writing after would let two concurrent requests through. The write runs
in a savepoint, so the transaction is still usable, and nothing is audited when it is refused:

- creating or editing onto a taken name or code is ``409 conflict`` naming the field (AC-TEN-38);
- reactivating onto one is ``400 validation_error`` with code ``taken`` on that field, and the
  branch stays inactive (RN-TEN-19, Q-210, AC-TEN-30). design.md §6 names the name; a taken code
  answers the same way, as the reactivation has no other code for it.

Any other integrity error is a bug and goes up as is. An edit that changes nothing writes nothing.

A branch is never deleted (AC-TEN-30): deactivating sets ``is_active`` false and ``deactivated_at``;
reactivating sets them back. Deactivating an inactive branch or reactivating an active one is
``409 invalid_transition``, with ``transition.rejected`` (entity, state, event: Q-225) emitted after
the transaction, so its rollback does not take the event with it (design.md §3.3, AC-TEN-37).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.locks import ensure_writable
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Branch
from apps.tenancy.models.branch import ADDRESS_MAX_LENGTH, CODE_MAX_LENGTH, NAME_MAX_LENGTH
from apps.tenancy.selectors.branches import lock_branch
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
TAKEN = "taken"
_STATE_FIELDS = ["is_active", "deactivated_at"]
# ``transition.rejected`` (Q-225): which entity, in which state, refused which event.
_ENTITY = "branch"
DEACTIVATE = "deactivate"
REACTIVATE = "reactivate"


class BranchConflict(APIException):
    """``409 conflict``: the name or the code is already used by an active branch (AC-TEN-38)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Ya hay una sucursal activa con esos datos."


def _error(message: str, code: str) -> list[ErrorDetail]:
    return [ErrorDetail(message, code=code)]


def _clean(fields: Mapping[str, object], *, name_required: bool) -> dict[str, str]:
    errors = unknown_field_errors(fields, CREATE_FIELDS)
    cleaned: dict[str, str] = {}
    for field, limit in CREATE_FIELDS.items():
        if field not in fields:
            if field == "name" and name_required:
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


def clean_new_branch(fields: Mapping[str, object]) -> dict[str, str]:
    """The normalized values of a new branch; ``ValidationError`` with every wrong field."""
    return _clean(fields, name_required=True)


def clean_changes(changes: Mapping[str, object]) -> dict[str, str]:
    """The normalized values of an edit (any subset); ``ValidationError`` with every wrong one."""
    return _clean(changes, name_required=False)


def _taken_field(error: IntegrityError) -> str:
    """The field of a uniqueness constraint; any other integrity error goes up as the bug it is."""
    diagnostics = getattr(error.__cause__, "diag", None)
    field = _UNIQUE_FIELDS.get(str(getattr(diagnostics, "constraint_name", None)))
    if field is None:
        raise error
    return field


def _conflict(field: str) -> BranchConflict:
    return BranchConflict(detail=_TAKEN[field], code="conflict")


def _save(branch: Branch, fields: list[str]) -> str | None:
    """Saves ``fields`` in a savepoint; the field whose value is taken, if any."""
    try:
        with transaction.atomic():
            branch.save(update_fields=[*fields, "updated_at"])
    except IntegrityError as error:
        return _taken_field(error)
    return None


def _metadata(branch: Branch) -> dict[str, object]:
    return {"branch_id": str(branch.pk)}


@audit_trigger(TenancyAuditAction.BRANCH_CREATED)
def create_branch(ctx: TenantContext, fields: Mapping[str, object]) -> Branch:
    cleaned = clean_new_branch(fields)
    with transaction.atomic():
        ensure_writable(ctx)
        try:
            with transaction.atomic():
                branch = Branch.objects.for_tenant(ctx).create(**cleaned)
        except IntegrityError as error:
            raise _conflict(_taken_field(error)) from None
        record_event(TenancyAuditAction.BRANCH_CREATED, ctx=ctx, metadata=_metadata(branch))
    return branch


@audit_trigger(TenancyAuditAction.BRANCH_UPDATED)
def update_branch(
    ctx: TenantContext, branch_id: uuid.UUID, changes: Mapping[str, object]
) -> Branch:
    """``branch.updated`` with the names of the changed fields, never their values."""
    cleaned = clean_changes(changes)
    with transaction.atomic():
        ensure_writable(ctx)
        branch = lock_branch(ctx, branch_id)
        changed = [field for field, value in cleaned.items() if getattr(branch, field) != value]
        if not changed:
            return branch
        for field in changed:
            setattr(branch, field, cleaned[field])
        if taken := _save(branch, changed):
            raise _conflict(taken)
        metadata = {**_metadata(branch), "changed_fields": changed}
        record_event(TenancyAuditAction.BRANCH_UPDATED, ctx=ctx, metadata=metadata)
    return branch


@audit_trigger(TenancyAuditAction.BRANCH_DEACTIVATED)
def deactivate_branch(ctx: TenantContext, branch_id: uuid.UUID) -> Branch:
    with transaction.atomic():
        ensure_writable(ctx)
        branch = lock_branch(ctx, branch_id)
        if branch.is_active:
            branch.is_active, branch.deactivated_at = False, timezone.now()
            # Deactivating frees the name and the code: no constraint can refuse it.
            _save(branch, _STATE_FIELDS)
            record_event(TenancyAuditAction.BRANCH_DEACTIVATED, ctx=ctx, metadata=_metadata(branch))
            return branch
    raise _rejected(ctx, branch, DEACTIVATE)


@audit_trigger(TenancyAuditAction.BRANCH_REACTIVATED, TenancyAuditAction.TRANSITION_REJECTED)
def reactivate_branch(ctx: TenantContext, branch_id: uuid.UUID) -> Branch:
    with transaction.atomic():
        ensure_writable(ctx)
        branch = lock_branch(ctx, branch_id)
        if not branch.is_active:
            branch.is_active, branch.deactivated_at = True, None
            if taken := _save(branch, _STATE_FIELDS):
                raise ValidationError({taken: _error(_TAKEN[taken], TAKEN)})
            record_event(TenancyAuditAction.BRANCH_REACTIVATED, ctx=ctx, metadata=_metadata(branch))
            return branch
    raise _rejected(ctx, branch, REACTIVATE)


def _rejected(ctx: TenantContext, branch: Branch, event: str) -> InvalidTransition:
    """Emits ``transition.rejected`` (outside the transaction) and gives the error to raise."""
    state = "active" if branch.is_active else "inactive"
    metadata = {"entity": _ENTITY, "entity_id": str(branch.pk), "state": state, "event": event}
    record_event(TenancyAuditAction.TRANSITION_REJECTED, ctx=ctx, metadata=metadata)
    return InvalidTransition()
