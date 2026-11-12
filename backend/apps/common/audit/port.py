"""Audit port towards SPEC-10 (RF-TEN-09, RN-TEN-17, C-08, design.md §3.1).

``emit(event)`` hands the event to the sink named by ``settings.AUDIT_SINK``. Contract: it is called
**inside** the business transaction, so the transactional sink SPEC-10 brings commits or rolls back
with the change it records. Audited rejections are the exception: they are emitted after leaving the
atomic block, so the rollback does not take them (design.md §3.3).

Every event says who (``AuditActor``), what (``action``), on which organization and when, in UTC
(AC-TEN-23). ``metadata`` never carries secrets, tokens nor someone else's email (C-06, RNF-TEN-06).
``action`` is a plain string: each module brings its catalog (``apps.tenancy.domain.audit_events``)
and this package imports none of them.

Lives next to identity's ``AuditPort`` (``apps.identity.ports.audit``); both write to the ``audit``
channel and SPEC-10 unifies them with the real sink (tasks.md, "Ajustes al diseño").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

from apps.common.tenancy.context import Actor, ApiKeyActor, SystemActor, UserActor


class AuditActorKind(StrEnum):
    USER = "user"
    API_KEY = "api_key"
    SYSTEM = "system"
    PLATFORM_OPERATOR = "platform_operator"


# Which kinds are identified by an id and which by a name (the system reason, the operator).
_BY_ID = frozenset({AuditActorKind.USER, AuditActorKind.API_KEY})


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditActor:
    """``id`` for a user or an API key; ``name`` for the system (its reason) or the operator."""

    kind: AuditActorKind
    id: uuid.UUID | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AuditActorKind):
            raise TypeError("kind must be an AuditActorKind")
        if self.kind in _BY_ID:
            if not isinstance(self.id, uuid.UUID) or self.name is not None:
                raise ValueError(f"a {self.kind} actor is identified by a UUID id only")
        elif self.id is not None or not (isinstance(self.name, str) and self.name.strip()):
            raise ValueError(f"a {self.kind} actor is identified by a name only")

    @classmethod
    def for_tenant_actor(cls, actor: Actor) -> AuditActor:
        if isinstance(actor, UserActor):
            return cls(kind=AuditActorKind.USER, id=actor.user_id)
        if isinstance(actor, ApiKeyActor):
            return cls(kind=AuditActorKind.API_KEY, id=actor.key_id)
        if isinstance(actor, SystemActor):
            return cls(kind=AuditActorKind.SYSTEM, name=actor.reason.value)
        raise TypeError("actor must be a UserActor, ApiKeyActor or SystemActor")

    @classmethod
    def platform_operator(cls, name: str) -> AuditActor:
        """The operator of a management command, by its allow-listed identity (Q-212)."""
        return cls(kind=AuditActorKind.PLATFORM_OPERATOR, name=name)


@dataclass(frozen=True, kw_only=True)
class AuditEvent:
    action: str
    actor: AuditActor
    organization_id: uuid.UUID
    occurred_at: datetime
    reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (isinstance(self.action, str) and self.action):
            raise ValueError("action is required")
        if not isinstance(self.actor, AuditActor):
            raise TypeError("actor must be an AuditActor")
        if not isinstance(self.organization_id, uuid.UUID):
            raise TypeError("organization_id must be a UUID")
        if self.occurred_at.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be UTC")


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


@cache
def _load_sink(dotted_path: str) -> AuditSink:
    sink: AuditSink = import_string(dotted_path)()
    return sink


def get_sink() -> AuditSink:
    """One instance per configured path and process, so the test sink keeps what it recorded."""
    return _load_sink(settings.AUDIT_SINK)


def emit(event: AuditEvent) -> None:
    get_sink().record(event)
