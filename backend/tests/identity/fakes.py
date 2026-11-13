"""Ports in memory for the callback tests (T-IDA-12): RN-IDA-05's gate without SPEC-02's tables.

The registry imports a dotted path and calls it on every use, so the settings point at
``current_invitation_port`` and ``current_audit_port`` and ``install_ports`` swaps the instances
behind them.

It keeps the contract of ``ports/invitations.py``: the email is compared exactly after trimming and
lowercasing (Q-107), validity is judged at ``now`` (AC-IDA-04) and ``accept_invitations`` accepts
all or none (RN-IDA-06). What it cannot do is roll back with the caller's transaction or lock a row:
that is the real port's part (``T-TEN-17``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.emails import normalize_email
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.invitations import InvitationRef, InvitationsNoLongerValid


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


@dataclass
class FakeInvitation:
    email: str
    expires_at: datetime
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    invitation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: InvitationStatus = InvitationStatus.PENDING
    accepted_by: uuid.UUID | None = None
    # Stops being acceptable between ``find`` and ``accept`` (AC-IDA-05).
    fails_on_accept: bool = False

    @property
    def ref(self) -> InvitationRef:
        return InvitationRef(invitation_id=self.invitation_id, organization_id=self.organization_id)

    def is_valid(self, now: datetime) -> bool:
        return self.status == InvitationStatus.PENDING and now < self.expires_at


class InMemoryInvitationPort:
    def __init__(self) -> None:
        self.invitations: list[FakeInvitation] = []
        self.calls: list[str] = []
        # Runs inside ``find_valid_invitations``: the race test holds the first callback there.
        self.on_find: Callable[[], None] | None = None

    def invite(
        self, email: str, *, now: datetime, valid_for: timedelta = timedelta(days=7)
    ) -> FakeInvitation:
        """The address is kept as the inviter typed it and normalized, as SPEC-02 stores it."""
        invitation = FakeInvitation(email=normalize_email(email), expires_at=now + valid_for)
        self.invitations.append(invitation)
        return invitation

    def find_valid_invitations(
        self, email_normalized: str, *, now: datetime
    ) -> list[InvitationRef]:
        self.calls.append("find_valid_invitations")
        if self.on_find is not None:
            self.on_find()
        return [
            invitation.ref
            for invitation in self.invitations
            if invitation.email == email_normalized and invitation.is_valid(now)
        ]

    def accept_invitations(
        self, invitations: Sequence[InvitationRef], user_id: uuid.UUID, *, now: datetime
    ) -> None:
        self.calls.append("accept_invitations")
        wanted = {ref.invitation_id for ref in invitations}
        found = [item for item in self.invitations if item.invitation_id in wanted]
        if len(found) != len(wanted) or any(
            item.fails_on_accept or not item.is_valid(now) for item in found
        ):
            raise InvitationsNoLongerValid
        for item in found:
            item.status = InvitationStatus.ACCEPTED
            item.accepted_by = user_id


class RecordingAuditPort:
    """Keeps the events at once; that a rollback drops them is ``LogAuditPort``'s test."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class Ports:
    invitations: InMemoryInvitationPort
    audit: RecordingAuditPort


_ports = Ports(InMemoryInvitationPort(), RecordingAuditPort())


def current_invitation_port() -> InMemoryInvitationPort:
    return _ports.invitations


def current_audit_port() -> RecordingAuditPort:
    return _ports.audit


def install_ports(settings: SettingsWrapper) -> Ports:
    """Fresh ports behind both settings; pytest-django restores the settings after the test."""
    global _ports  # the registry resolves a path, not an instance
    _ports = Ports(InMemoryInvitationPort(), RecordingAuditPort())
    settings.IDENTITY_INVITATION_PORT = f"{__name__}.current_invitation_port"
    settings.IDENTITY_AUDIT_PORT = f"{__name__}.current_audit_port"
    return _ports
