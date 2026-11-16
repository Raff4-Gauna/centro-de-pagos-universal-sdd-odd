"""The active memberships of one user: "my organizations" (RF-TEN-02, RN-TEN-07, design.md §3.3).

``list_active_memberships(user_id)`` feeds ``GET /api/organizations/`` and, through
``services/membership_selector.py``, SPEC-01's ``GET /api/me``. One ``SELECT`` with ``JOIN`` to
``tenancy_organization`` over the partial index ``membership_active_user_org``. It reads with
``Membership.objects.for_user(user_id)`` (design.md §3.4): the user is the scope, across
organizations, and there is no active organization to ask for (the routes are exempt, §3.5).

Only ``active`` memberships, whatever the status of the organization: a suspended one is still the
user's, and the UI shows it read-only (RN-TEN-18). Ordered by organization name, then id, so a page
never repeats or skips one. A row whose role or status is outside its enum, which the constraints
should have stopped, is left out and logged as a bug: it fails closed, as the resolution does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import MembershipStatus

logger = get_logger(__name__)

INVALID_ROW_EVENT = "tenancy.membership_invalid_row"


@dataclass(frozen=True, slots=True)
class MyMembership:
    organization_id: uuid.UUID
    organization_name: str
    organization_status: OrgStatus
    role: Role


def list_active_memberships(user_id: uuid.UUID) -> list[MyMembership]:
    rows = (
        Membership.objects.for_user(user_id)
        .filter(status=MembershipStatus.ACTIVE.value)
        .order_by("organization__name", "organization_id")
        .values_list("id", "organization_id", "organization__name", "organization__status", "role")
    )
    found: list[MyMembership] = []
    for membership_id, organization_id, name, status, role in rows:
        try:
            found.append(MyMembership(organization_id, name, OrgStatus(status), Role(role)))
        except ValueError:
            logger.error(INVALID_ROW_EVENT, membership_id=str(membership_id))
    return found
