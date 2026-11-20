"""Read invitations across organizations, by what the person brings (design.md §3.4, §4.4).

``find_by_token(token)`` is the first step of accepting by token: it hashes the token and reads the
one row with that hash through ``Invitation.objects.by_token_hash``, with no transaction and no
lock, as the diagram of §4.4 does. Only the hash reaches the database; the token is neither kept
nor logged. It gives the id and the organization of the row, which is where the service opens its
``tenant_scope``; everything else is read again under that scope and under the lock.

``list_my_pending(email, now=)`` is ``GET /api/invitations/mine/`` (Q-121, Q-124): the ``pending``
invitations of that email (``Invitation.objects.pending_for_email``), still valid (``expires_at >
now``, RN-TEN-12) and of an ``active`` organization, the filter of the port of SPEC-01. One
``SELECT`` with a ``JOIN`` to the organization, ordered by expiry and then id so a page never
repeats or skips one. It carries what the person needs to decide and nothing else: neither the
token nor its hash, nor who invited them (design.md §6).

The port of SPEC-01 (``services/invitation_port.py``, T-TEN-17) reads in two steps, so the locks
keep the order of ADR-0002 §3, organization before invitation. ``organizations_with_pending(email,
now=)`` is the first: the ids of the ``active`` organizations with a valid ``pending`` invitation
for that email, with no lock and in ``id`` order, the order the port locks them in. Under each
organization's mutex, ``lock_pending_for_email(mutex, email, now=)`` locks (``FOR UPDATE``, in
``id`` order) the ones still ``pending`` and valid, read again through ``for_tenant``.

The invitations of the active organization (RF-TEN-05, design.md §6, ``GET /api/invitations/``)
read only ``ctx``'s organization (``for_tenant``), for owner and admin (``invitation.list``, Q-218).
``list_pending(ctx, now=)`` gives the ``pending`` ones still valid (``expires_at > now``: one past
it is expired already, RN-TEN-12, though nobody wrote it yet), ordered by creation, then id; it is
lazy, so the paginator slices it in the database, and ``to_invitations`` maps a page.
``get_invitation(ctx, id)`` is one of them, any status, or ``None``. Each row carries who invited
(``invited_by``: the person's id, email and display name; ``None`` for one the platform operator
issued, whose identity is not the organization's) and never the token nor its hash.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import QuerySet

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.common.tenancy.locks import bounded_lock_wait
from apps.tenancy.domain.invitations import (
    InvitationPurpose,
    InvitationStatus,
    hash_token,
    normalize_email,
)
from apps.tenancy.models import Invitation
from apps.tenancy.selectors.locks import MembershipMutex


@dataclass(frozen=True, slots=True)
class InvitationRef:
    """Which invitation and in which organization: nothing of the invitee, nothing secret."""

    invitation_id: uuid.UUID
    organization_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class MyInvitation:
    """One pending invitation of the person: where to, with which role and until when."""

    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    role: Role
    expires_at: datetime


def find_by_token(token: str) -> InvitationRef | None:
    row = (
        Invitation.objects.by_token_hash(hash_token(token))
        .values_list("id", "organization_id")
        .first()
    )
    return None if row is None else InvitationRef(*row)


def list_my_pending(email: str, *, now: datetime) -> list[MyInvitation]:
    rows = (
        Invitation.objects.pending_for_email(email)
        .filter(expires_at__gt=now, organization__status=OrgStatus.ACTIVE.value)
        .order_by("expires_at", "id")
        .values_list("id", "organization_id", "organization__name", "role", "expires_at")
    )
    return [
        MyInvitation(invitation_id, organization_id, name, Role(role), expires_at)
        for invitation_id, organization_id, name, role, expires_at in rows
    ]


def organizations_with_pending(email: str, *, now: datetime) -> list[uuid.UUID]:
    rows = (
        Invitation.objects.pending_for_email(email)
        .filter(expires_at__gt=now, organization__status=OrgStatus.ACTIVE.value)
        .order_by("organization_id")
        .values_list("organization_id", flat=True)
        .distinct()
    )
    return list(rows)


def lock_pending_for_email(mutex: MembershipMutex, email: str, *, now: datetime) -> list[uuid.UUID]:
    """Under the organization's mutex: its valid ``pending`` ones for ``email``, locked."""
    with bounded_lock_wait():
        rows = (
            Invitation.objects.for_tenant(mutex.ctx)
            .select_for_update()
            .filter(
                email=normalize_email(email),
                status=InvitationStatus.PENDING.value,
                expires_at__gt=now,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        return list(rows)


@dataclass(frozen=True, slots=True)
class Inviter:
    """Who issued an invitation: a person of the Hub (the operator's name no invitation)."""

    id: uuid.UUID
    email: str
    name: str


@dataclass(frozen=True, slots=True)
class OrganizationInvitation:
    """An invitation of the active organization, as owner and admin see it: never its token."""

    id: uuid.UUID
    email: str
    role: Role
    status: InvitationStatus
    purpose: InvitationPurpose
    expires_at: datetime
    invited_by: Inviter | None
    created_at: datetime


_INVITATION_FIELDS = (
    "id",
    "email",
    "role",
    "status",
    "purpose",
    "expires_at",
    "invited_by_user_id",
    "invited_by_user__email",
    "invited_by_user__display_name",
    "created_at",
)


def _invitation(row: tuple[Any, ...]) -> OrganizationInvitation:
    values = dict(zip(_INVITATION_FIELDS, row, strict=True))
    inviter_id = values["invited_by_user_id"]
    inviter = None
    if inviter_id is not None:
        inviter = Inviter(
            inviter_id,
            str(values["invited_by_user__email"]),
            str(values["invited_by_user__display_name"]),
        )
    return OrganizationInvitation(
        id=values["id"],
        email=str(values["email"]),
        role=Role(values["role"]),
        status=InvitationStatus(values["status"]),
        purpose=InvitationPurpose(values["purpose"]),
        expires_at=values["expires_at"],
        invited_by=inviter,
        created_at=values["created_at"],
    )


def list_pending(ctx: TenantContext, *, now: datetime) -> QuerySet[Invitation, Any]:
    """The rows, lazy, so the paginator slices them in the database; ``to_invitations`` maps a
    page."""
    return (
        Invitation.objects.for_tenant(ctx)
        .filter(status=InvitationStatus.PENDING.value, expires_at__gt=now)
        .order_by("created_at", "id")
        .values_list(*_INVITATION_FIELDS)
    )


def to_invitations(rows: Iterable[tuple[Any, ...]]) -> list[OrganizationInvitation]:
    return [_invitation(row) for row in rows]


def get_invitation(ctx: TenantContext, invitation_id: uuid.UUID) -> OrganizationInvitation | None:
    row = (
        Invitation.objects.for_tenant(ctx)
        .filter(pk=invitation_id)
        .values_list(*_INVITATION_FIELDS)
        .first()
    )
    return None if row is None else _invitation(row)
