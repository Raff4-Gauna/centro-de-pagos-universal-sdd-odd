"""``TenantContext``: who acts and on which organization (RF-TEN-01, design.md §3.1, ADR-0001).

Immutable (``frozen`` + ``slots``): once resolved for a request or a task nobody can repoint it to
another organization. The types are checked on construction, so a raw string or an ``int`` never
passes for an organization id, a status or an actor. Pure: no Django, no database.

Not here yet: ``system_context(organization_id, reason)`` reads the real status of the organization
and needs its model (T-TEN-02); it arrives with the tasks that use it (T-TEN-11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class OrgStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class SystemReason(StrEnum):
    """Why a process acts without a user (design.md §3.6)."""

    WEBHOOK = "webhook"
    POLLER = "poller"
    CELERY = "celery"
    PLATFORM_COMMAND = "platform_command"


@dataclass(frozen=True, slots=True)
class UserActor:
    """A person through an active membership. ``role`` becomes ``authz.roles.Role`` in T-TEN-05."""

    user_id: uuid.UUID
    membership_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class ApiKeyActor:
    """Reserved for SPEC-11 (API keys): the union below already names it."""

    key_id: uuid.UUID
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class SystemActor:
    reason: SystemReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, SystemReason):
            raise TypeError("reason must be a SystemReason")


Actor = UserActor | ApiKeyActor | SystemActor


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: uuid.UUID
    organization_status: OrgStatus
    actor: Actor

    def __post_init__(self) -> None:
        if not isinstance(self.organization_id, uuid.UUID):
            raise TypeError("organization_id must be a UUID")
        if not isinstance(self.organization_status, OrgStatus):
            raise TypeError("organization_status must be an OrgStatus")
        if not isinstance(self.actor, UserActor | ApiKeyActor | SystemActor):
            raise TypeError("actor must be a UserActor, ApiKeyActor or SystemActor")

    @property
    def is_suspended(self) -> bool:
        return self.organization_status is OrgStatus.SUSPENDED
