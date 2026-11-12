"""How SPEC-02's services emit audit (RF-TEN-09, RN-TEN-17, design.md §3.3, §9).

``record_event`` builds the event from the tenant context (actor and organization) and the clock,
then emits it: call it inside the service's ``transaction.atomic()``, except for the audited
rejections, which go after it (design.md §3.3).

``AUDIT_TRIGGERS`` maps each action to the service function that emits it. Each service registers
itself with ``@audit_trigger(...)``; T-TEN-27 drives every entry and fails on an action without one.
One function per action: the one the completeness test calls, even if others emit it too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeVar

from django.utils import timezone

from apps.common.audit.port import AuditActor, AuditEvent, emit
from apps.common.tenancy.context import TenantContext
from apps.tenancy.domain.audit_events import TenancyAuditAction

Trigger = Callable[..., object]
F = TypeVar("F", bound=Trigger)

AUDIT_TRIGGERS: dict[TenancyAuditAction, Trigger] = {}


def audit_trigger(
    *actions: TenancyAuditAction, registry: dict[TenancyAuditAction, Trigger] = AUDIT_TRIGGERS
) -> Callable[[F], F]:
    def register(function: F) -> F:
        for action in actions:
            current = registry.setdefault(action, function)
            if current is not function:
                raise ValueError(f"{action} already has a trigger: {current.__qualname__}")
        return function

    return register


def record_event(
    action: TenancyAuditAction,
    *,
    ctx: TenantContext,
    actor: AuditActor | None = None,
    reason: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> AuditEvent:
    """``actor`` replaces the context's (the operator of a command); the event is returned."""
    event = AuditEvent(
        action=TenancyAuditAction(action),
        actor=actor or AuditActor.for_tenant_actor(ctx.actor),
        organization_id=ctx.organization_id,
        occurred_at=timezone.now(),
        reason=reason,
        metadata=dict(metadata or {}),
    )
    emit(event)
    return event
