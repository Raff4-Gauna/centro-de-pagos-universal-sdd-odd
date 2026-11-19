"""Shared setup of the lock tests (T-TEN-11): organizations, members and contexts for each actor."""

from __future__ import annotations

import uuid

from apps.common.authz.roles import Role
from apps.common.tenancy.context import (
    OrgStatus,
    SystemActor,
    SystemReason,
    TenantContext,
    UserActor,
)
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.querysets import UnscopedReason
from apps.identity.models import User
from apps.tenancy.models import Membership, Organization
from tests.testapps.tenant_probe.models import Widget

PLATFORM = UnscopedReason.PLATFORM_COMMAND


def new_org(name: str, status: OrgStatus = OrgStatus.ACTIVE) -> Organization:
    return Organization.objects.unscoped(PLATFORM).create(
        name=name, status=status.value, created_by_operator="operator@hub.test"
    )


def system_ctx(organization_id: uuid.UUID, status: OrgStatus = OrgStatus.ACTIVE) -> TenantContext:
    return TenantContext(organization_id, status, SystemActor(SystemReason.PLATFORM_COMMAND))


def add_member(organization: Organization, name: str, role: Role) -> Membership:
    user = User.objects.create_user(google_sub=f"sub-{name}", email=f"{name}@hub.test")
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx):
        return Membership.objects.for_tenant(ctx).create(user=user, role=role.value)


def user_ctx(membership: Membership, status: OrgStatus = OrgStatus.ACTIVE) -> TenantContext:
    """The context the request resolution builds: the status it read, maybe stale by now."""
    actor = UserActor(membership.user_id, membership.id, Role(membership.role))
    return TenantContext(membership.organization_id, status, actor)


def new_widget(organization: Organization, name: str = "before") -> Widget:
    ctx = system_ctx(organization.id)
    with tenant_scope(ctx):
        return Widget.objects.for_tenant(ctx).create(name=name)


def widget_name(widget: Widget) -> str:
    return str(Widget.objects.unscoped(PLATFORM).values_list("name", flat=True).get(pk=widget.pk))


def set_status(organization: Organization, status: OrgStatus) -> None:
    Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk).update(status=status.value)
