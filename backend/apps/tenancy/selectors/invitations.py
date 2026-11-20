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
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.locks import bounded_lock_wait
from apps.tenancy.domain.invitations import InvitationStatus, hash_token, normalize_email
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
