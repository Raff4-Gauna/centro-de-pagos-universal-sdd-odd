"""``/api/branches/``: list and create the branches of the active organization (RF-TEN-06, §6).

A ``TenantViewSet``: ``X-Organization-Id`` names the organization and the resolution checks the
membership on every request (RN-TEN-03). ``list`` is ``branch.read`` (every role, also with the
organization suspended); ``create`` is ``branch.create`` (owner and admin, ``WRITE``: ``403`` for
operator and viewer, AC-TEN-16; ``409 organization_suspended`` when suspended).

``GET`` lists active and inactive branches alike, each with ``is_active`` (AC-TEN-30), or only one
kind with ``?is_active=true|false``; paginated as the other lists (``HubPageNumberPagination``),
ordered by name. ``POST`` hands the body to ``services.branches.create_branch``, which takes the
organization from the context and rejects any other key (AC-TEN-07). There is no route to delete a
branch: ``DELETE`` (and ``PUT``) is ``405`` (AC-TEN-30, RN-TEN-19). Seeing, editing, deactivating
and reactivating one by id come with T-TEN-25.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.api.serializers.branches import (
    BranchCreateSerializer,
    BranchListQuerySerializer,
    BranchSerializer,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.selectors.branches import list_branches
from apps.tenancy.services.branches import create_branch

BRANCHES_TAG = "tenancy"


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


class BranchViewSet(TenantViewSet):
    serializer_class = BranchSerializer
    pagination_class = HubPageNumberPagination
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "create": TENANCY_ACTIONS[TenancyAction.BRANCH_CREATE],
    }

    @extend_schema(
        operation_id="branches_list",
        summary="Las sucursales de la organización activa",
        tags=[BRANCHES_TAG],
        parameters=[BranchListQuerySerializer],
        responses={200: BranchSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        query = BranchListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        branches = list_branches(self.tenant, is_active=query.is_active_filter())
        page = self.paginate_queryset(branches)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(
        operation_id="branches_create",
        summary="Crea una sucursal en la organización activa",
        tags=[BRANCHES_TAG],
        request=BranchCreateSerializer,
        responses={
            201: BranchSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (unknown_field si el cuerpo trae otra clave) · "
                "organization_required"
            ),
            (403, PROBLEM_CONTENT_TYPE): _problem("code: forbidden"),
            (409, PROBLEM_CONTENT_TYPE): _problem(
                "code: conflict (nombre o código de otra sucursal activa) · organization_suspended"
            ),
        },
    )
    def create(self, request: Request) -> Response:
        body: Any = request.data
        if not isinstance(body, Mapping):
            raise ValidationError({"non_field_errors": ["El cuerpo tiene que ser un objeto."]})
        branch = create_branch(self.tenant, body)
        return Response(self.get_serializer(branch).data, status=201)
