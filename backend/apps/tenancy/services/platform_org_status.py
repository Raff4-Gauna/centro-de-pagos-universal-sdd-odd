"""The platform operator suspends or reactivates an organization (RF-TEN-07, RN-TEN-18, Q-208).

Only ``manage.py tenancy_set_org_status`` calls this: no route of the API changes the status of an
organization, not even for its owner (AC-TEN-29). The command checks ``--operator`` against
``PLATFORM_OPERATOR_EMAILS`` before it gets here; the operator (that email) is the actor of every
event, with the user of the operating system in ``metadata`` (``os_user``), as in
``services/platform_org.py``.

``set_org_status(organization_id, target, reason, operator)``, in one transaction (design.md §4.5):

1. ``tenant_scope(system_context(org, PLATFORM_COMMAND))``: an unknown organization is
   ``OrganizationNotFound`` and nothing is written.
2. The row is locked ``FOR UPDATE`` (bounded, ``LOCK_TIMEOUT``): it waits for every write in flight
   (``FOR KEY SHARE``, ``ensure_writable``) and every membership change (``FOR NO KEY UPDATE``,
   ``lock_membership_mutex``), and every one that comes after waits for it and reads the new status
   (design.md §3.7). That is what makes a suspension effective for the next write, not the next
   request only (AC-TEN-28).
3. ``active`` → ``suspended`` (suspend) or ``suspended`` → ``active`` (reactivate): ``status`` and
   ``status_changed_at`` change and ``organization.suspended`` / ``organization.reactivated`` is
   emitted, with ``--reason`` as the event's reason. Asking for the status it already has is not in
   the transitions of spec §10: rejected and audited (C-05), ``transition.rejected`` (entity, state,
   event) after the transaction, as every refusal of the module (design.md §3.3), and
   ``InvalidTransition``.

The reason is free text of the operator: it goes to the audit event only, never to the logs, which
carry ids and statuses (C-06).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.common.audit.port import AuditActor
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.locks import bounded_lock_wait, system_context
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Organization
from apps.tenancy.services.audit import audit_trigger, record_event
from apps.tenancy.services.platform_org import Operator

logger = get_logger(__name__)

CHANGED_EVENT = "tenancy.platform_org_status_changed"
REJECTED_EVENT = "tenancy.platform_org_status_rejected"
# The operator's reasons are kept as long as the invitation's ``reason`` (design.md §5).
REASON_MAX_LENGTH = 200
_ENTITY = "organization"
_EVENTS = {
    OrgStatus.SUSPENDED: ("suspend", TenancyAuditAction.ORGANIZATION_SUSPENDED),
    OrgStatus.ACTIVE: ("reactivate", TenancyAuditAction.ORGANIZATION_REACTIVATED),
}
_FIELDS = ["status", "status_changed_at", "updated_at"]


class InvalidReasonError(ValueError):
    """A blank or too long ``--reason``; the message never repeats the value."""


@dataclass(frozen=True, slots=True)
class StatusChange:
    organization_id: uuid.UUID
    status: OrgStatus


def clean_reason(value: object) -> str:
    reason = value.strip() if isinstance(value, str) else ""
    if not 0 < len(reason) <= REASON_MAX_LENGTH:
        raise InvalidReasonError(
            f"the reason must have between 1 and {REASON_MAX_LENGTH} characters"
        )
    return reason


@audit_trigger(
    TenancyAuditAction.ORGANIZATION_SUSPENDED, TenancyAuditAction.ORGANIZATION_REACTIVATED
)
def set_org_status(
    organization_id: uuid.UUID,
    target: OrgStatus,
    reason: str,
    operator: Operator,
    *,
    now: datetime | None = None,
) -> StatusChange:
    if not isinstance(target, OrgStatus):
        raise TypeError("target must be an OrgStatus")
    moment = timezone.now() if now is None else now
    event, action = _EVENTS[target]
    actor = AuditActor.platform_operator(operator.email)
    with transaction.atomic():
        ctx = system_context(organization_id, SystemReason.PLATFORM_COMMAND)
        with tenant_scope(ctx):
            current = _change_locked(ctx, target, moment)
            if current is None:
                metadata = {"os_user": operator.os_user}
                record_event(action, ctx=ctx, actor=actor, reason=reason, metadata=metadata)
    if current is not None:
        _reject(ctx, actor, operator, current, event)
    logger.info(CHANGED_EVENT, organization_id=str(organization_id), status=target.value)
    return StatusChange(organization_id, target)


def _change_locked(ctx: TenantContext, target: OrgStatus, now: datetime) -> OrgStatus | None:
    """The status under ``FOR UPDATE``: ``None`` if it changed, else the one it already had."""
    with bounded_lock_wait():
        organization = Organization.objects.for_tenant(ctx).select_for_update().get()
    current = OrgStatus(organization.status)
    if current is target:
        return current
    organization.status = target.value
    organization.status_changed_at = now
    organization.save(update_fields=_FIELDS)
    return None


def _reject(
    ctx: TenantContext, actor: AuditActor, operator: Operator, state: OrgStatus, event: str
) -> None:
    metadata = {
        "entity": _ENTITY,
        "entity_id": str(ctx.organization_id),
        "state": state.value,
        "event": event,
        "os_user": operator.os_user,
    }
    record_event(TenancyAuditAction.TRANSITION_REJECTED, ctx=ctx, actor=actor, metadata=metadata)
    logger.info(REJECTED_EVENT, organization_id=str(ctx.organization_id), state=state.value)
    raise InvalidTransition
