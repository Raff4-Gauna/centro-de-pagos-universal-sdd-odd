"""Audit port: implemented by SPEC-10 (RN-IDA-17, RF-IDA-09, design.md §7.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from apps.identity.domain.audit_events import (
    AUDIT_REASONS,
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
)


@dataclass(frozen=True, kw_only=True)
class AuditEvent:
    """``metadata`` carries no secrets; on a rejected login, no email nor ``sub`` either (Q-125)."""

    action: IdentityAuditAction
    result: AuditResult
    reason: str | None = None
    actor_type: AuditActorType
    actor_id: UUID | None = None
    organization_id: UUID | None = None
    occurred_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be UTC")
        reasons = AUDIT_REASONS.get(self.action)
        if reasons is not None and self.reason not in reasons:
            raise ValueError(f"reason outside the catalog of {self.action}")


class AuditPort(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Inside the caller's transaction, if there is one: atomic with the state change."""
        ...
