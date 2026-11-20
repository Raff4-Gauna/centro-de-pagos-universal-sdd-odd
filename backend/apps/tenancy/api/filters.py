"""The branch of the selector as a filter of a listing (RN-TEN-16, Q-204, design.md §3.9, §6).

``resolve_branch_filter(request, ctx)`` reads the query parameter ``branch_id`` of a route that
filters by branch (charges, reports: later modules) and gives the branch of the active organization
it names, or ``None`` without the parameter ("Todas las sucursales").

- A branch of another organization is ``404 not_found``, the body of one that does not exist: never
  its data (AC-TEN-09, RN-TEN-05). It goes through ``selectors.branches.get_branch``.
- It is a filter, not a boundary: every role that may read the route filters by any branch of the
  organization, active or not (AC-TEN-32; there are no memberships restricted to branches in the
  MVP, Q-204). An inactive branch still filters: its history stays (RN-TEN-19).
- A value that is not a UUID (empty included) is ``400 validation_error`` on ``branch_id``.

``BRANCH_FILTER`` documents the parameter in the schema of the routes that use it.
"""

from __future__ import annotations

import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.request import Request

from apps.common.tenancy.context import TenantContext
from apps.tenancy.models import Branch
from apps.tenancy.selectors.branches import get_branch

BRANCH_ID = "branch_id"

BRANCH_FILTER = OpenApiParameter(
    name=BRANCH_ID,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Sucursal de la organización activa; sin el parámetro: todas (RN-TEN-16).",
)


def resolve_branch_filter(request: Request, ctx: TenantContext) -> Branch | None:
    if BRANCH_ID not in request.query_params:
        return None
    try:
        branch_id = uuid.UUID(request.query_params[BRANCH_ID])
    except ValueError:
        message = ErrorDetail("No es un identificador de sucursal.", code="invalid")
        raise ValidationError({BRANCH_ID: [message]}) from None
    return get_branch(ctx, branch_id)
