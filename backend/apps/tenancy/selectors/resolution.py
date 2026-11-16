"""The active membership a request names (RN-TEN-03/06/08, RNF-TEN-07, design.md §3.5).

``find_active_membership`` is what ``ResolveTenant`` asks on every request, with no cache: **one**
``SELECT`` of ``tenancy_membership`` joined to ``tenancy_organization`` by the partial index
``membership_active_user_org``, whatever the number of memberships of the user. There is no tenant
yet (resolving it is the point), so it reads with ``unscoped(TENANT_RESOLUTION)``, the reason
design.md §3.3 keeps for this module only; the filter by user *and* organization is the scope.

An unknown organization, one without a membership of the user and a revoked membership all give
``None``: the caller cannot tell them apart (RN-TEN-06). So does a row whose role or organization
status is outside its enum, which the constraints should have stopped: it fails closed and is
logged as a bug, never turned into a context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.querysets import UnscopedReason
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import MembershipStatus

logger = get_logger(__name__)

INVALID_ROW_EVENT = "tenancy.resolution_invalid_row"


@dataclass(frozen=True, slots=True)
class ActiveMembership:
    membership_id: uuid.UUID
    role: Role
    organization_status: OrgStatus


def find_active_membership(
    *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> ActiveMembership | None:
    row = (
        Membership.objects.unscoped(UnscopedReason.TENANT_RESOLUTION)
        .filter(
            user_id=user_id,
            organization_id=organization_id,
            status=MembershipStatus.ACTIVE.value,
        )
        .values_list("id", "role", "organization__status")
        .first()
    )
    if row is None:
        return None
    membership_id, role, organization_status = row
    try:
        return ActiveMembership(membership_id, Role(role), OrgStatus(organization_status))
    except ValueError:
        logger.error(INVALID_ROW_EVENT, membership_id=str(membership_id))
        return None
