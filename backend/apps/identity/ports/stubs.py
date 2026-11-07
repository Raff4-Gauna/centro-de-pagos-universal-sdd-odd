"""Defaults until SPEC-02 and SPEC-10 register theirs by settings (design.md §6.4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.common.logging import get_logger
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.invitations import InvitationRef, InvitationsNoLongerValid
from apps.identity.ports.memberships import MembershipSummary

audit_channel = get_logger("audit")


class NullInvitationPort:
    """No invitations exist, so every new login ends in ``not_invited``."""

    def find_valid_invitations(
        self, email_normalized: str, *, now: datetime
    ) -> list[InvitationRef]:
        return []

    def accept_invitations(
        self, invitations: Sequence[InvitationRef], user_id: UUID, *, now: datetime
    ) -> None:
        """Always refuses: it never offered an invitation, and a quiet return here would leave a
        user created without one (RN-IDA-06)."""
        raise InvitationsNoLongerValid


class EmptyMembershipSelector:
    def list_active_memberships(self, user_id: UUID) -> list[MembershipSummary]:
        return []


class LogAuditPort:
    """One structured event on the ``audit`` logger, a channel of its own.

    A log line cannot join a transaction, so it waits for the commit: a change that rolls back
    leaves no event claiming it happened. Outside a transaction it goes out at once. The fields are
    copied now, so nothing done to ``metadata`` before the commit changes the event.
    """

    def record(self, event: AuditEvent) -> None:
        fields = asdict(event)
        transaction.on_commit(lambda: audit_channel.info("audit.event", **fields))
