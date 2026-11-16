"""A tenant-scoped route and the data the resolution tests need (T-TEN-08, design.md §3.5).

``ProbeViewSet`` is the smallest ``TenantViewSet``: ``list`` is a ``READ`` open to every role and
``create`` a ``WRITE`` for owner/admin (``branch.read``/``branch.create`` of the matrix), so one
route shows the whole order of errors. The tests mount it with ``pytest.mark.urls(URLCONF)``.
``list`` answers what the view sees of the tenant, so a test can tell that the resolution reached
the view, the ``ContextVar`` and the log context.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from structlog.contextvars import get_contextvars

from apps.common.authz.roles import Role
from apps.common.tenancy.context import (
    OrgStatus,
    SystemActor,
    SystemReason,
    TenantContext,
    UserActor,
)
from apps.common.tenancy.current import current_tenant, tenant_scope
from apps.common.tenancy.querysets import UnscopedReason
from apps.identity.models import User
from apps.identity.services.session_lifecycle import open_session
from apps.identity.tokens.access_token import issue_access_token
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Membership, Organization
from apps.tenancy.models.membership import EndedReason, MembershipStatus

URLCONF = "tests.tenancy.api.probe"
PROBE = "/api/probe/"
HEADER = "X-Organization-Id"
PLATFORM = UnscopedReason.PLATFORM_COMMAND


class ProbeViewSet(TenantViewSet):
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "create": TENANCY_ACTIONS[TenancyAction.BRANCH_CREATE],
    }

    def list(self, request: Request) -> Response:
        ctx = self.tenant
        assert isinstance(ctx.actor, UserActor)
        return Response(
            {
                "organization_id": str(ctx.organization_id),
                "membership_id": str(ctx.actor.membership_id),
                "role": ctx.actor.role.value,
                "status": ctx.organization_status.value,
                "context_var_is_tenant": current_tenant() is ctx,
                "logged_organization_id": get_contextvars().get("organization_id"),
            }
        )

    def create(self, request: Request) -> Response:
        return Response(status=201)


router = SimpleRouter()
router.register("api/probe", ProbeViewSet, basename="probe")
urlpatterns = router.urls


def platform_ctx(organization: Organization) -> TenantContext:
    status = OrgStatus(organization.status)
    actor = SystemActor(SystemReason.PLATFORM_COMMAND)
    return TenantContext(organization_id=organization.id, organization_status=status, actor=actor)


def new_org(name: str, status: OrgStatus = OrgStatus.ACTIVE) -> Organization:
    return Organization.objects.unscoped(PLATFORM).create(
        name=name, status=status.value, created_by_operator="operator@hub.test"
    )


def new_user(name: str) -> User:
    return User.objects.create_user(google_sub=f"sub-{name}", email=f"{name}@hub.test")


def add_member(organization: Organization, user: User, role: Role) -> Membership:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        return Membership.objects.for_tenant(ctx).create(user=user, role=role.value)


def revoke(organization: Organization, membership: Membership) -> None:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        Membership.objects.for_tenant(ctx).filter(pk=membership.pk).update(
            status=MembershipStatus.REVOKED.value,
            ended_reason=EndedReason.REVOKED.value,
            ended_at=timezone.now(),
        )


def bearer_of(user: User) -> dict[str, str]:
    session = open_session(user, now=timezone.now()).session
    token = issue_access_token(user_id=user.pk, session_id=session.pk)
    return {"Authorization": f"Bearer {token}"}


def as_member(user: User, organization_id: uuid.UUID | str | None) -> dict[str, str]:
    """The headers of a request of ``user`` naming ``organization_id`` (``None``: no header)."""
    headers = bearer_of(user)
    if organization_id is not None:
        headers[HEADER] = str(organization_id)
    return headers


def constant_part(response: Any) -> dict[str, Any]:
    """The body without ``request_id``, the one field that differs between two requests."""
    body = dict(response.json())
    body.pop("request_id")
    return body
