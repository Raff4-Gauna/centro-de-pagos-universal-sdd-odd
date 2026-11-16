"""The organization of each request and what its actor may do there (design.md §3.5, ADR-0001).

DRF permissions, not a Django middleware: the user is the one SPEC-01's ``HubJWTAuthentication``
authenticated inside DRF (ADR-0001). ``TenantViewSet`` runs them after ``IsAuthenticated``.

``ResolveTenant`` (RF-TEN-01, RN-TEN-03/06/08/20):

1. ``X-Organization-Id`` absent or empty → ``400 organization_required`` (AC-TEN-06).
2. Not a UUID → ``404 organization_not_found``, the body of an unknown organization.
3. One query (``selectors.resolution.find_active_membership``) for the active membership of this
   user in that organization. None → the same ``404``: unknown, without membership, revoked and a
   superuser/staff without membership are one case (AC-TEN-03/04/33). ``is_superuser``/``is_staff``
   are never read (RN-TEN-20).
4. Builds the ``TenantContext`` (the only builder outside ``apps/common/tenancy/``), leaves it in
   ``request.tenant`` and activates it (``ContextVar`` and the ``organization_id`` log key; the
   middleware clears both when the request ends). Nothing is cached between requests (RN-TEN-08).

``ActionPermission`` (RN-TEN-09/18): the ``ActionSpec`` of ``view.action`` goes through
``authz.checks.require``: role first (``403 forbidden``), then the suspension (``409
organization_suspended``). An action without a spec is denied; a method the viewset does not map
is ``405``.

Every denial logs ``tenancy.access_denied`` with its ``reason``, the user and the organization asked
for (RNF-TEN-02, Q-217): only a parsed UUID, never the raw header. ``request_id`` comes from the
log context; ``organization_id`` is bound only once validated.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from rest_framework import exceptions
from rest_framework.permissions import BasePermission

from apps.common.authz.actions import ActionSpec
from apps.common.authz.checks import require
from apps.common.logging import get_logger
from apps.common.tenancy.context import TenantContext, UserActor
from apps.common.tenancy.current import activate_tenant
from apps.common.tenancy.errors import (
    Forbidden,
    OrganizationNotFound,
    OrganizationRequired,
    OrganizationSuspended,
    TenantContextMissingError,
)
from apps.identity.api.authentication import Unauthenticated
from apps.tenancy.selectors.resolution import find_active_membership

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

logger = get_logger(__name__)

# The header of the active organization (design.md §6): part of the contract, not a setting.
TENANT_HEADER = "X-Organization-Id"
# Attribute of the DRF ``Request`` that carries the resolved context (``tenant_of``).
TENANT_ATTR = "tenant"
DENIED_EVENT = "tenancy.access_denied"


def tenant_of(request: Request) -> TenantContext:
    """The context ``ResolveTenant`` left on ``request``; without one it is a bug (500)."""
    ctx = getattr(request, TENANT_ATTR, None)
    if not isinstance(ctx, TenantContext):
        raise TenantContextMissingError
    return ctx


def _deny(reason: str, request: Request, **fields: Any) -> None:
    user_id = getattr(request.user, "pk", None)
    logger.warning(
        DENIED_EVENT,
        reason=reason,
        user_id=str(user_id) if user_id is not None else None,
        **fields,
    )


def _requested_organization(request: Request) -> uuid.UUID:
    value = request.headers.get(TENANT_HEADER, "").strip()
    if not value:
        _deny("organization_header_missing", request, requested_organization_id=None)
        raise OrganizationRequired()
    try:
        return uuid.UUID(value)
    except ValueError:
        _deny("organization_header_malformed", request, requested_organization_id=None)
        raise OrganizationNotFound() from None


class ResolveTenant(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            raise Unauthenticated
        organization_id = _requested_organization(request)
        found = find_active_membership(user_id=user.pk, organization_id=organization_id)
        if found is None:
            _deny("no_active_membership", request, requested_organization_id=str(organization_id))
            raise OrganizationNotFound()
        ctx = TenantContext(
            organization_id=organization_id,
            organization_status=found.organization_status,
            actor=UserActor(user_id=user.pk, membership_id=found.membership_id, role=found.role),
        )
        setattr(request, TENANT_ATTR, ctx)
        activate_tenant(ctx)
        return True


class ActionPermission(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        ctx = tenant_of(request)
        name = getattr(view, "action", None)
        if name is None:  # a method the viewset does not map: never reaches a handler
            raise exceptions.MethodNotAllowed(request.method or "")
        specs = getattr(view, "action_specs", {})
        spec = specs.get(name)
        if not isinstance(spec, ActionSpec):
            _deny("undeclared_action", request, action=str(name))
            raise Forbidden()
        try:
            require(ctx, spec)
        except Forbidden:
            _deny("role_not_allowed", request, action=spec.name)
            raise
        except OrganizationSuspended:
            _deny("organization_suspended", request, action=spec.name)
            raise
        return True
