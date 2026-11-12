"""Stub sinks until SPEC-10 brings the transactional one (design.md §3.1, §10).

``StructlogAuditSink`` is not durable: a log line cannot join a transaction. That is the production
gate of design.md §10, no real organization is onboarded on it.
"""

from __future__ import annotations

import copy
from dataclasses import asdict

from django.db import transaction

from apps.common.audit.port import AuditEvent
from apps.common.logging import get_logger

audit_channel = get_logger("audit")


class RecordingSink:
    """Tests: keeps every event in memory, in order, as it was when recorded.

    It records the call at once, even inside a transaction that later rolls back: it stands for
    "the service emitted", not for durability.
    """

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(copy.deepcopy(event))

    def clear(self) -> None:
        self.events.clear()


class StructlogAuditSink:
    """Dev/staging: one ``audit.event`` on the ``audit`` logger, a channel of its own.

    It waits for the commit, so a change that rolls back leaves no event claiming it happened;
    outside a transaction it goes out at once. The fields are copied now.
    """

    def record(self, event: AuditEvent) -> None:
        fields = asdict(event)
        transaction.on_commit(lambda: audit_channel.info("audit.event", **fields))
