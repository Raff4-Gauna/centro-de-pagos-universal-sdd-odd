"""The organizations of the person and the active one (RF-TEN-02, RF-TEN-03, design.md §6).

``GET /api/organizations/`` (``MyOrganizationsView``) is exempt from the active organization
(design.md §3.5): it lists the organizations a user can pick, so it is not a ``TenantViewSet``;
``X-Organization-Id`` is neither required nor read. The user is always the authenticated one and
the route takes no user identifier, so nobody lists anyone else's (AC-TEN-08). Default permission:
any authenticated person; anonymous → ``401 unauthenticated``. Paginated as the other lists
(``HubPageNumberPagination``), ordered by name.

``/api/organizations/current/`` (``CurrentOrganizationViewSet``) is the organization of
``X-Organization-Id``: ``GET`` for every role (``org.read``), ``PATCH`` of ``name``,
``legal_name``, ``tax_id`` and ``timezone`` for owner and admin (``org.update``, a ``WRITE``:
``409 organization_suspended`` while suspended). Both answer the same body.

There is no way to create, replace, delete or change the status of an organization through the
API (RN-TEN-10, RN-TEN-18, AC-TEN-21, AC-TEN-29): any other method is ``405 method_not_allowed``
once authenticated, and ``status`` in a ``PATCH`` is ``400 validation_error``. Both routes answer
``Cache-Control: no-store``.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.api.authentication import Unauthenticated
from apps.identity.selectors.auth_sessions import RequestAuthContext
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.api.serializers.organizations import (
    CurrentOrganizationSerializer,
    OrganizationUpdateSerializer,
    current_organization,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Organization
from apps.tenancy.selectors.memberships import MyMembership, list_active_memberships
from apps.tenancy.selectors.organizations import get_organization
from apps.tenancy.services.organizations import update_organization

ORGANIZATIONS_TAG = "tenancy"


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


_UNAUTHORIZED = _problem(
    "code: unauthenticated · token_expired · token_invalid · session_revoked "
    '(con WWW-Authenticate: Bearer realm="hub")'
)
_ORGANIZATION_REQUIRED = _problem("code: organization_required (falta X-Organization-Id)")
_ORGANIZATION_NOT_FOUND = _problem(
    "code: organization_not_found (no existe o sin membership activa: el mismo cuerpo)"
)


# One organization of the user and the role of their active membership in it. A comment, not a
# docstring: drf-spectacular would publish a docstring as the component's description.
class MyOrganizationSerializer(serializers.Serializer[MyMembership]):
    id = serializers.UUIDField(source="organization_id", read_only=True)
    name = serializers.CharField(source="organization_name", read_only=True)
    status = serializers.ChoiceField(
        source="organization_status", choices=[s.value for s in OrgStatus], read_only=True
    )
    role = serializers.ChoiceField(choices=[r.value for r in Role], read_only=True)

    class Meta:
        ref_name = "MyOrganization"


class MyOrganizationsView(generics.ListAPIView[Any]):
    serializer_class = MyOrganizationSerializer
    pagination_class = HubPageNumberPagination

    @extend_schema(
        operation_id="organizations_list",
        summary="Las organizaciones de la persona autenticada y su rol en cada una",
        tags=[ORGANIZATIONS_TAG],
        responses={
            200: MyOrganizationSerializer(many=True),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        context = request.auth
        if not isinstance(context, RequestAuthContext):  # only a Hub session names a person
            raise Unauthenticated
        rows = list_active_memberships(context.user.pk)
        # DRF pages any sequence; the stubs only type a QuerySet. One query, already ordered.
        page = self.paginate_queryset(rows)  # type: ignore[arg-type]
        response = self.get_paginated_response(self.get_serializer(page, many=True).data)
        response["Cache-Control"] = "no-store"  # personal data: no shared or browser copy
        return response


class CurrentOrganizationViewSet(TenantViewSet):
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "retrieve": TENANCY_ACTIONS[TenancyAction.ORG_READ],
        "partial_update": TENANCY_ACTIONS[TenancyAction.ORG_UPDATE],
    }

    def _respond(self, organization: Organization) -> Response:
        body = CurrentOrganizationSerializer(current_organization(organization, self.tenant)).data
        response = Response(body)
        response["Cache-Control"] = "no-store"  # the actor's role and permissions
        return response

    @extend_schema(
        operation_id="organizations_current_retrieve",
        summary="La organización activa y lo que la persona puede hacer en ella",
        tags=[ORGANIZATIONS_TAG],
        responses={
            200: CurrentOrganizationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _ORGANIZATION_REQUIRED,
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
            (404, PROBLEM_CONTENT_TYPE): _ORGANIZATION_NOT_FOUND,
        },
    )
    def retrieve(self, request: Request) -> Response:
        return self._respond(get_organization(self.tenant))

    @extend_schema(
        operation_id="organizations_current_partial_update",
        summary="Editar los datos de la organización activa (owner y admin)",
        tags=[ORGANIZATIONS_TAG],
        request=OrganizationUpdateSerializer,
        responses={
            200: CurrentOrganizationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (un campo desconocido o de solo lectura, como status, "
                "es unknown_field) · organization_required"
            ),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
            (403, PROBLEM_CONTENT_TYPE): _problem("code: forbidden (rol sin org.update)"),
            (404, PROBLEM_CONTENT_TYPE): _ORGANIZATION_NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _problem("code: organization_suspended"),
        },
    )
    def partial_update(self, request: Request) -> Response:
        serializer = OrganizationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._respond(update_organization(self.tenant, serializer.validated_data))
