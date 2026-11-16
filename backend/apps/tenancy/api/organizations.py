"""``GET /api/organizations/``: my organizations and my role in each (RF-TEN-02, design.md §6).

Exempt from the active organization (design.md §3.5): it lists the organizations a user can pick,
so it is not a ``TenantViewSet``; ``X-Organization-Id`` is neither required nor read. The user is
always the authenticated one and the route takes no user identifier, so nobody lists anyone else's
(AC-TEN-08). Default permission: any authenticated person; anonymous → ``401 unauthenticated``.

Only ``GET``: there is no way to create, replace or delete an organization through the API
(RN-TEN-10, AC-TEN-21); any other method is ``405 method_not_allowed`` once authenticated.
Paginated as the other lists (``HubPageNumberPagination``), ordered by name.
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
from apps.tenancy.selectors.memberships import MyMembership, list_active_memberships

ORGANIZATIONS_TAG = "tenancy"
_UNAUTHORIZED = OpenApiResponse(
    response={"$ref": f"#/components/schemas/{PROBLEM}"},
    description=(
        "code: unauthenticated · token_expired · token_invalid · session_revoked "
        '(con WWW-Authenticate: Bearer realm="hub")'
    ),
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
