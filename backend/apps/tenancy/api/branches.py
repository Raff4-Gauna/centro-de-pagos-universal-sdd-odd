"""``/api/branches/``: the branches of the active organization (RF-TEN-06, design.md §6).

A ``TenantViewSet``: ``X-Organization-Id`` names the organization and the resolution checks the
membership and reads the role on every request (RN-TEN-03, AC-TEN-05). ``list`` and ``retrieve``
are ``branch.read`` (every role, also with the organization suspended); ``create``,
``partial_update``, ``deactivate`` and ``reactivate`` are ``branch.create``/``update``/
``deactivate``/``reactivate`` (owner and admin, ``WRITE``: ``403`` for operator and viewer,
AC-TEN-16; ``409 organization_suspended`` when suspended).

``GET /api/branches/`` lists active and inactive branches alike, each with ``is_active``
(AC-TEN-30), or only one kind with ``?is_active=true|false``; paginated as the other lists
(``HubPageNumberPagination``), ordered by name. ``POST`` hands the body to
``services.branches.create_branch``, which takes the organization from the context and rejects any
other key (AC-TEN-07); ``PATCH /api/branches/{id}/`` does the same with ``update_branch``.

By id, a branch of another organization, one that does not exist and an id that is not a UUID are
the same ``404 not_found`` (AC-TEN-01). ``deactivate``/``reactivate`` take no body: the state
changes only there, and the wrong one is ``409 invalid_transition`` (AC-TEN-37). There is no route
to delete a branch: ``DELETE`` (and ``PUT``) is ``405`` (AC-TEN-30, RN-TEN-19).

``deactivate`` and ``reactivate`` are mounted in ``urls.py`` (``as_view({"post": ...})``), not with
``@action``: drf-spectacular stores the ``@extend_schema`` of an ``@action`` in its ``as_view()``
initkwargs, and the cross-tenant suite refuses any initkwarg that could replace the guard
(``tests/cross_tenant/classifier.py``). ``ActionPermission`` reads them by name all the same.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.tenancy.api.base import ORGANIZATION_BUSY_RESPONSE, TenantViewSet
from apps.tenancy.api.serializers.branches import (
    BranchCreateSerializer,
    BranchListQuerySerializer,
    BranchSerializer,
    BranchUpdateSerializer,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Branch
from apps.tenancy.selectors.branches import BRANCH_NOT_FOUND, get_branch, list_branches
from apps.tenancy.services.branches import (
    create_branch,
    deactivate_branch,
    reactivate_branch,
    update_branch,
)

BRANCHES_TAG = "tenancy"
LOOKUP = "id"

BRANCH_ID = OpenApiParameter(
    name=LOOKUP, type=OpenApiTypes.UUID, location=OpenApiParameter.PATH, description="La sucursal."
)


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


_FORBIDDEN = _problem("code: forbidden (rol sin permiso de gestión de sucursales)")
_NOT_FOUND = _problem("code: not_found (no existe o es de otra organización: el mismo cuerpo)")
_TRANSITION = _problem("code: invalid_transition (ya está en ese estado) · organization_suspended")
_TAKEN = _problem(
    "code: conflict (nombre o código de otra sucursal activa) · organization_suspended"
)


def _body(request: Request) -> Mapping[str, object]:
    body: Any = request.data
    if not isinstance(body, Mapping):
        raise ValidationError({"non_field_errors": ["El cuerpo tiene que ser un objeto."]})
    return body


class BranchViewSet(TenantViewSet):
    serializer_class = BranchSerializer
    pagination_class = HubPageNumberPagination
    lookup_url_kwarg = LOOKUP
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "create": TENANCY_ACTIONS[TenancyAction.BRANCH_CREATE],
        "retrieve": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "partial_update": TENANCY_ACTIONS[TenancyAction.BRANCH_UPDATE],
        "deactivate": TENANCY_ACTIONS[TenancyAction.BRANCH_DEACTIVATE],
        "reactivate": TENANCY_ACTIONS[TenancyAction.BRANCH_REACTIVATE],
    }

    def _branch_id(self) -> uuid.UUID:
        """The id of the URL; one that is not a UUID is the 404 of an unknown branch."""
        try:
            return uuid.UUID(str(self.kwargs[LOOKUP]))
        except ValueError:
            raise NotFound(BRANCH_NOT_FOUND) from None

    def _respond(self, branch: Branch, status: int = 200) -> Response:
        return Response(self.get_serializer(branch).data, status=status)

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
            (403, PROBLEM_CONTENT_TYPE): _FORBIDDEN,
            (409, PROBLEM_CONTENT_TYPE): _TAKEN,
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def create(self, request: Request) -> Response:
        return self._respond(create_branch(self.tenant, _body(request)), status=201)

    @extend_schema(
        operation_id="branches_retrieve",
        summary="Una sucursal de la organización activa, activa o no",
        tags=[BRANCHES_TAG],
        parameters=[BRANCH_ID],
        responses={200: BranchSerializer, (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND},
    )
    def retrieve(self, request: Request, **kwargs: Any) -> Response:
        return self._respond(get_branch(self.tenant, self._branch_id()))

    @extend_schema(
        operation_id="branches_partial_update",
        summary="Edita el nombre, el código o la dirección de una sucursal",
        tags=[BRANCHES_TAG],
        parameters=[BRANCH_ID],
        request=BranchUpdateSerializer,
        responses={
            200: BranchSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (unknown_field si el cuerpo trae otra clave, como "
                "is_active u organization_id)"
            ),
            (403, PROBLEM_CONTENT_TYPE): _FORBIDDEN,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _TAKEN,
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def partial_update(self, request: Request, **kwargs: Any) -> Response:
        return self._respond(update_branch(self.tenant, self._branch_id(), _body(request)))

    @extend_schema(
        operation_id="branches_deactivate",
        summary="Desactiva una sucursal (no se borra nunca)",
        tags=[BRANCHES_TAG],
        parameters=[BRANCH_ID],
        request=None,
        responses={
            200: BranchSerializer,
            (403, PROBLEM_CONTENT_TYPE): _FORBIDDEN,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _TRANSITION,
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def deactivate(self, request: Request, **kwargs: Any) -> Response:
        return self._respond(deactivate_branch(self.tenant, self._branch_id()))

    @extend_schema(
        operation_id="branches_reactivate",
        summary="Reactiva una sucursal inactiva",
        tags=[BRANCHES_TAG],
        parameters=[BRANCH_ID],
        request=None,
        responses={
            200: BranchSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (taken: otra sucursal activa usa su nombre o su código)"
            ),
            (403, PROBLEM_CONTENT_TYPE): _FORBIDDEN,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _TRANSITION,
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def reactivate(self, request: Request, **kwargs: Any) -> Response:
        return self._respond(reactivate_branch(self.tenant, self._branch_id()))
