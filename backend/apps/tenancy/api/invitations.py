"""Accept an invitation and list one's own (RN-TEN-11, RN-TEN-12, design.md §3.5, §4.4, §6).

Three routes, all exempt from the active organization (design.md §3.5): the person has no
membership in the invitation's organization yet, so none is a ``TenantViewSet`` and
``X-Organization-Id`` is neither required nor read; the organization is the invitation's. Only a
person with a Hub session reaches them (``401`` otherwise); the invitee is always the
authenticated one, by the email of their Google account, and no route takes a user or an email.

- ``POST /api/invitations/accept/`` (``AcceptInvitationView``): the body is ``{token}``; the token
  is hashed before anything else and never shows up in the response, in an error or in a log
  (RNF-TEN-03, C-06). The refusals are ``400 invitation_invalid`` with ``reason`` (``not_found``,
  ``email_mismatch``, ``revoked``, ``used``, ``expired``).
- ``GET /api/invitations/mine/`` (``MyInvitationsView``, Q-121, Q-124): the ``pending`` and valid
  invitations of the person's email, of active organizations, paginated as the other lists
  (``HubPageNumberPagination``): ``{id, organization:{id, name}, role, expires_at}``, never the
  token nor who invited them.
- ``POST /api/invitations/{id}/accept/`` (``AcceptMyInvitationView``): the same service, without a
  token and without a body (any key is ``400 validation_error``, ``unknown_field``). Another
  person's invitation and a missing one give the same ``400 invitation_invalid`` with
  ``reason=not_found``; this contract has no ``email_mismatch``.

``200`` of both accepts is the membership created; ``409 organization_suspended`` and
``409 already_member`` are the other refusals. Every answer is ``Cache-Control: no-store``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.common.authz.roles import Role
from apps.identity.api.authentication import Unauthenticated
from apps.identity.selectors.auth_sessions import RequestAuthContext
from apps.tenancy.api.serializers.invitations import (
    AcceptedInvitationSerializer,
    InvitationAcceptSerializer,
    JoinedOrganizationSerializer,
)
from apps.tenancy.selectors.invitations import MyInvitation, list_my_pending
from apps.tenancy.services.fields import unknown_field_errors
from apps.tenancy.services.invitation_accept import (
    Invitee,
    accept_by_token,
    accept_from_session,
)

INVITATIONS_TAG = "tenancy"


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


_UNAUTHORIZED = _problem(
    "code: unauthenticated · token_expired · token_invalid · session_revoked "
    '(con WWW-Authenticate: Bearer realm="hub")'
)
_CONFLICT = _problem("code: organization_suspended · already_member")


def _invitee(request: Request) -> Invitee:
    context = request.auth
    if not isinstance(context, RequestAuthContext):  # only a Hub session names a person
        raise Unauthenticated
    return Invitee(user_id=context.user.pk, email=context.user.email)


def _no_store(response: Response) -> Response:
    """Errors too: they say what this person's invitation is."""
    response["Cache-Control"] = "no-store"
    return response


# No body: strict like every body of SPEC-02 (design.md §6), any key is ``unknown_field``.
class NoBodySerializer(serializers.Serializer[dict[str, Any]]):
    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, Mapping) and (unknown := unknown_field_errors(data, ())):
            raise ValidationError(unknown)
        validated: dict[str, Any] = super().to_internal_value(data)
        return validated


# One pending invitation of the person: never the token nor who invited them. The organization has
# the shape of the accept's (``JoinedOrganization``). A comment: drf-spectacular would publish it.
class MyInvitationSerializer(serializers.Serializer[MyInvitation]):
    id = serializers.UUIDField(read_only=True)
    organization = JoinedOrganizationSerializer(source="*", read_only=True)
    role = serializers.ChoiceField(choices=[r.value for r in Role], read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)

    class Meta:
        ref_name = "MyInvitation"


class AcceptInvitationView(APIView):
    @extend_schema(
        operation_id="invitations_accept",
        summary="Aceptar una invitación con su token (sin organización activa)",
        tags=[INVITATIONS_TAG],
        request=InvitationAcceptSerializer,
        responses={
            200: AcceptedInvitationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: invitation_invalid, con reason: not_found · email_mismatch · revoked · "
                "used · expired; o validation_error (falta el token)"
            ),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
            (409, PROBLEM_CONTENT_TYPE): _CONFLICT,
        },
    )
    def post(self, request: Request) -> Response:
        invitee = _invitee(request)
        body = InvitationAcceptSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        accepted = accept_by_token(body.validated_data["token"], invitee)
        return Response(AcceptedInvitationSerializer(accepted).data)

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        return _no_store(super().finalize_response(request, response, *args, **kwargs))


class MyInvitationsView(generics.ListAPIView[Any]):
    serializer_class = MyInvitationSerializer
    pagination_class = HubPageNumberPagination

    @extend_schema(
        operation_id="invitations_mine",
        summary="Las invitaciones pendientes del email de la persona (sin organización activa)",
        tags=[INVITATIONS_TAG],
        responses={
            200: MyInvitationSerializer(many=True),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = list_my_pending(_invitee(request).email, now=timezone.now())
        # DRF pages any sequence; the stubs only type a QuerySet. One query, already ordered.
        page = self.paginate_queryset(rows)  # type: ignore[arg-type]
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        return _no_store(super().finalize_response(request, response, *args, **kwargs))


class AcceptMyInvitationView(APIView):
    @extend_schema(
        operation_id="invitations_accept_mine",
        summary="Aceptar desde la sesión una invitación del propio email (sin organización activa)",
        tags=[INVITATIONS_TAG],
        request=None,
        responses={
            200: AcceptedInvitationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: invitation_invalid, con reason: not_found (no existe o es de otro email: "
                "el mismo cuerpo) · revoked · used · expired; o validation_error (el pedido no "
                "lleva cuerpo)"
            ),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
            (409, PROBLEM_CONTENT_TYPE): _CONFLICT,
        },
    )
    def post(self, request: Request, invitation_id: uuid.UUID) -> Response:
        invitee = _invitee(request)
        NoBodySerializer(data=request.data).is_valid(raise_exception=True)
        accepted = accept_from_session(invitation_id, invitee)
        return Response(AcceptedInvitationSerializer(accepted).data)

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        return _no_store(super().finalize_response(request, response, *args, **kwargs))
