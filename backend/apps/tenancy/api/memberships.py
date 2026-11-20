"""``/api/memberships/``: the members of the active organization and their roles (RF-TEN-04, §6).

A ``TenantViewSet``: ``X-Organization-Id`` names the organization and the resolution checks the
membership on every request (RN-TEN-03). ``GET /api/memberships/`` is ``member.list``: owner and
admin only (Q-218), so an operator or a viewer gets ``403`` and no email (AC-TEN-34).
``?status=`` is ``active`` (the default) or ``revoked``; paginated as the other lists
(``HubPageNumberPagination``), ordered by creation. ``PATCH /api/memberships/{id}/`` with
``{role}`` is ``member.change_role`` (owner and admin, a ``WRITE``):
``services.memberships.change_role`` decides with the roles and the owners as they are under the
lock (design.md §4.2); a lock not taken in time is ``503 organization_busy`` (Q-230). An id of
another organization, or one that is not a UUID, is ``404 not_found``, as a missing one
(RN-TEN-05, AC-TEN-02).

Both answer each membership with ``allowed_actions`` and ``assignable_roles``
(``serializers/memberships.py``) and ``Cache-Control: no-store`` (colleagues' emails). Revoking
(``DELETE``) and leaving (``POST /api/memberships/me/leave/``) come with T-TEN-23; until then
``DELETE`` and ``PUT`` are ``405``.
"""

from __future__ import annotations

import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.tenancy.api.base import ORGANIZATION_BUSY_RESPONSE, TenantViewSet
from apps.tenancy.api.serializers.memberships import (
    MembershipListQuerySerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    member_view,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.selectors.memberships import (
    count_active_owners,
    get_member,
    list_members,
    to_members,
)
from apps.tenancy.services.memberships import MEMBERSHIP_NOT_FOUND, change_role

MEMBERSHIPS_TAG = "tenancy"
LOOKUP = "id"

MEMBERSHIP_ID = OpenApiParameter(
    name=LOOKUP,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    description="La membership.",
)


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


class MembershipViewSet(TenantViewSet):
    serializer_class = MembershipSerializer
    pagination_class = HubPageNumberPagination
    lookup_url_kwarg = LOOKUP
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.MEMBER_LIST],
        "partial_update": TENANCY_ACTIONS[TenancyAction.MEMBER_CHANGE_ROLE],
    }

    def _membership_id(self) -> uuid.UUID:
        """The id of the URL; one that is not a UUID is the 404 of an unknown membership."""
        try:
            return uuid.UUID(str(self.kwargs[LOOKUP]))
        except ValueError:
            raise NotFound(MEMBERSHIP_NOT_FOUND) from None

    @staticmethod
    def _no_store(response: Response) -> Response:
        response["Cache-Control"] = "no-store"  # colleagues' emails and the actor's permissions
        return response

    @extend_schema(
        operation_id="memberships_list",
        summary="Los miembros de la organización activa (owner y admin)",
        tags=[MEMBERSHIPS_TAG],
        parameters=[MembershipListQuerySerializer],
        responses={
            200: MembershipSerializer(many=True),
            (403, PROBLEM_CONTENT_TYPE): _problem("code: forbidden (operator y viewer)"),
        },
    )
    def list(self, request: Request) -> Response:
        query = MembershipListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        ctx = self.tenant
        page = self.paginate_queryset(list_members(ctx, query.membership_status()))
        owners = count_active_owners(ctx)
        views = [member_view(member, ctx, owners=owners) for member in to_members(page or [])]
        return self._no_store(
            self.get_paginated_response(self.get_serializer(views, many=True).data)
        )

    @extend_schema(
        operation_id="memberships_partial_update",
        summary="Cambiar el rol de una membership de la organización activa",
        tags=[MEMBERSHIPS_TAG],
        parameters=[MEMBERSHIP_ID],
        request=MembershipRoleSerializer,
        responses={
            200: MembershipSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (otra clave que role es unknown_field) · "
                "organization_required"
            ),
            (403, PROBLEM_CONTENT_TYPE): _problem(
                "code: forbidden (el rol no alcanza: un admin no toca owners, nadie se eleva)"
            ),
            (404, PROBLEM_CONTENT_TYPE): _problem(
                "code: not_found (no existe o es de otra organización: el mismo cuerpo) · "
                "organization_not_found"
            ),
            (409, PROBLEM_CONTENT_TYPE): _problem(
                "code: last_owner (dejaría la organización sin owner) · invalid_transition "
                "(membership revocada) · organization_suspended"
            ),
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def partial_update(self, request: Request, **kwargs: object) -> Response:
        body = MembershipRoleSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ctx = self.tenant
        change = change_role(ctx, self._membership_id(), body.new_role())
        member = get_member(ctx, change.membership_id)
        if member is None:  # it was just locked in this organization; a membership is never deleted
            raise NotFound(MEMBERSHIP_NOT_FOUND)
        view = member_view(
            member, ctx, owners=count_active_owners(ctx), actor_role=change.actor_role
        )
        return self._no_store(Response(self.get_serializer(view).data))
