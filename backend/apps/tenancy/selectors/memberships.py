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

The members of the active organization (RF-TEN-04, design.md §6, ``GET /api/memberships/``) read
only ``ctx``'s organization (``for_tenant``): a membership of another one is never listed nor found
by id (RN-TEN-05, AC-TEN-02). ``list_members(ctx, status)`` gives the ``active`` or the ``revoked``
ones with their person (id, email, display name: owner and admin only, Q-218, which the route's
``member.list`` enforces), ordered by creation, then id; it is lazy, so the paginator slices it in
the database, and ``to_members`` maps a page. ``get_member(ctx, id)`` is one of them, any status,
or ``None``; ``count_active_owners(ctx)`` the owners the UI hints are computed with. These reads
take no lock: a change decides on what ``selectors/locks.py`` re-reads under the mutex.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import QuerySet

from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import EndedReason, MembershipStatus

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


@dataclass(frozen=True, slots=True)
class Member:
    """A membership of the active organization and its person, as the API lists it."""

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str
    role: Role
    status: MembershipStatus
    ended_reason: EndedReason | None
    created_at: datetime


_MEMBER_FIELDS = (
    "id",
    "user_id",
    "user__email",
    "user__display_name",
    "role",
    "status",
    "ended_reason",
    "created_at",
)


def _member(row: tuple[Any, ...]) -> Member:
    membership_id, user_id, email, name, role, status, ended_reason, created_at = row
    return Member(
        id=membership_id,
        user_id=user_id,
        email=str(email),
        name=str(name),
        role=Role(role),
        status=MembershipStatus(status),
        ended_reason=None if ended_reason is None else EndedReason(ended_reason),
        created_at=created_at,
    )


def list_members(ctx: TenantContext, status: MembershipStatus) -> QuerySet[Membership, Any]:
    """The rows, lazy, so the paginator slices them in the database; ``to_members`` maps a page."""
    return (
        Membership.objects.for_tenant(ctx)
        .filter(status=MembershipStatus(status).value)
        .order_by("created_at", "id")
        .values_list(*_MEMBER_FIELDS)
    )


def to_members(rows: Iterable[tuple[Any, ...]]) -> list[Member]:
    return [_member(row) for row in rows]


def get_member(ctx: TenantContext, membership_id: uuid.UUID) -> Member | None:
    row = (
        Membership.objects.for_tenant(ctx)
        .filter(pk=membership_id)
        .values_list(*_MEMBER_FIELDS)
        .first()
    )
    return None if row is None else _member(row)


def count_active_owners(ctx: TenantContext) -> int:
    return (
        Membership.objects.for_tenant(ctx)
        .filter(role=Role.OWNER.value, status=MembershipStatus.ACTIVE.value)
        .count()
    )
