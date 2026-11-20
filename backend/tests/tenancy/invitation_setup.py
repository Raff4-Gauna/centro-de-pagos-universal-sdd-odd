"""Shared setup of the accept tests (T-TEN-15): invitations with a known token, and what to read.

Rows go in as the operator's command would (``platform_ctx``), so no business rule runs; the tests
read back with ``unscoped(PLATFORM)``, never through the code under test.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.common.authz.roles import Role
from apps.common.tenancy.current import tenant_scope
from apps.identity.models import User
from apps.tenancy.domain.invitations import (
    InvitationStatus,
    hash_token,
    new_token,
    normalize_email,
)
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services.invitation_accept import Invitee
from tests.tenancy.api.probe import PLATFORM, platform_ctx


def issue(
    organization: Organization,
    email: str = "x@dominio.com",
    role: Role = Role.OPERATOR,
    *,
    expires_at: datetime | None = None,
    **values: Any,
) -> tuple[Invitation, str]:
    """A ``pending`` invitation and its token in clear (only the test keeps it)."""
    token = new_token()
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        invitation = Invitation.objects.for_tenant(ctx).create(
            email=normalize_email(email),
            role=role.value,
            token_hash=hash_token(token),
            expires_at=expires_at or timezone.now() + timedelta(days=7),
            invited_by_operator="operator@hub.test",
            **values,
        )
    return invitation, token


def set_status(invitation: Invitation, status: InvitationStatus) -> None:
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    rows.update(status=status.value)


def make_due(invitation: Invitation) -> None:
    """Past its expiry but still ``pending``: issued a week ago, due a second ago."""
    now = timezone.now()
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    rows.update(created_at=now - timedelta(days=7), expires_at=now - timedelta(seconds=1))


def status_of(invitation: Invitation) -> str:
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    return str(rows.values_list("status", flat=True).get())


def memberships(user: User) -> list[tuple[Any, ...]]:
    """(organization, role, status, source_invitation) of every membership of ``user``."""
    rows = Membership.objects.unscoped(PLATFORM).filter(user=user).order_by("created_at")
    return list(rows.values_list("organization_id", "role", "status", "source_invitation_id"))


def invitee(user: User, email: str | None = None) -> Invitee:
    return Invitee(user_id=user.pk, email=user.email if email is None else email)
