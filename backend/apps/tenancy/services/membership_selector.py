"""SPEC-01's ``MembershipSelectorPort``, implemented by tenancy (Q-114, RF-TEN-02, AC-IDA-21).

``IDENTITY_MEMBERSHIP_SELECTOR`` names ``TenancyMembershipSelector``, so ``GET /api/me`` lists the
real memberships without identity importing tenancy (design.md §6.4 of SPEC-01). It adapts the
selector's rows to ``MembershipSummary``, whose shape this module fixes (T-TEN-12): organization
id, organization name and role. The organization status is not part of it: the shell reads it from
``GET /api/organizations/``, the one source for the selector of organizations (design.md §3.9).
"""

from __future__ import annotations

import uuid

from apps.identity.ports.memberships import MembershipSummary
from apps.tenancy.selectors.memberships import list_active_memberships


class TenancyMembershipSelector:
    def list_active_memberships(self, user_id: uuid.UUID) -> list[MembershipSummary]:
        return [
            MembershipSummary(m.organization_id, m.organization_name, m.role.value)
            for m in list_active_memberships(user_id)
        ]
