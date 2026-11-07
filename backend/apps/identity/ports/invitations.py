"""Invitation port: defined here, implemented by SPEC-02 (Q-108, Q-120, RN-IDA-06)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class InvitationRef:
    invitation_id: UUID
    organization_id: UUID


class InvitationsNoLongerValid(Exception):  # noqa: N818 - the name design.md §6.4 fixes
    """At least one invitation cannot be accepted: the caller rolls everything back."""


class InvitationPort(Protocol):
    def find_valid_invitations(
        self, email_normalized: str, *, now: datetime
    ) -> list[InvitationRef]:
        """The pending, unexpired invitations of that exact email, locked by the caller's
        transaction (``SELECT ... FOR UPDATE``) until it ends. Does not commit."""
        ...

    def accept_invitations(
        self, invitations: Sequence[InvitationRef], user_id: UUID, *, now: datetime
    ) -> None:
        """In the caller's transaction, all of them or none: creates the memberships or raises
        ``InvitationsNoLongerValid`` (or any error) and the caller rolls back the whole thing
        (RN-IDA-06). Does not commit nor emit identity's audit events."""
        ...
