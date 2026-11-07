"""Membership selector for ``/api/me``: implemented by SPEC-02 (Q-114), which fixes the final shape
of ``MembershipSummary`` (``T-TEN-12``); identity only passes the list along."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class MembershipSummary:
    organization_id: UUID
    organization_name: str
    role: str


class MembershipSelectorPort(Protocol):
    def list_active_memberships(self, user_id: UUID) -> list[MembershipSummary]: ...
