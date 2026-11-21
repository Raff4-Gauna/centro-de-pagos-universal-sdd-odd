"""Invitations: of the active organization, and accepting one's own (RF-TEN-05, design.md §6).

``/api/invitations/`` (``InvitationViewSet``) is a ``TenantViewSet``: ``X-Organization-Id`` names
the organization and the resolution checks the membership on every request (RN-TEN-03).

- ``GET`` is ``invitation.list``: owner and admin only (Q-218), so an operator or a viewer gets
  ``403`` and no email (AC-TEN-34). The ``pending`` and still valid ones, paginated as the other
  lists (``HubPageNumberPagination``), by creation; never a token (AC-TEN-24).
- ``POST`` with ``{email, role}`` is ``invitation.create`` (owner and admin, a ``WRITE``):
  ``services.invitations.create_invitation`` decides under the organization's lock (design.md
  §4.3). ``201`` is the invitation and its ``accept_url``, the only response that carries the
  token, once (RNF-TEN-03, Q-207). Refusals: ``403`` (an admin inviting an ``owner``, AC-TEN-15),
  ``409 already_member`` (AC-TEN-20), ``409 invitation_pending`` (AC-TEN-26),
  ``409 organization_suspended``, ``400 validation_error`` and ``503 organization_busy`` (Q-230).

- ``POST /api/invitations/{id}/resend/`` is ``invitation.resend`` (owner and admin, a ``WRITE``)
  and ``POST /api/invitations/{id}/revoke/`` is ``invitation.revoke`` (a ``REDUCE_ACCESS``, allowed
  with the organization suspended, Q-221), through ``services/invitation_manage.py`` (design.md
  §4.3). No body. The resend's ``201`` is the new invitation and its ``accept_url``, the only
  answer with the new token (AC-TEN-24); the revoke's ``200`` is the revoked row. Refusals:
  ``403`` (an admin on an ``owner`` one, AC-TEN-15), ``404 not_found`` (another organization's, a
  missing one or an id that is not a UUID: the same body, AC-TEN-02), ``409 invalid_transition``
  (not ``pending``, AC-TEN-37), ``409 organization_suspended`` (resend) and
  ``503 organization_busy`` (Q-230). Both are mounted in ``urls.py`` with ``as_view``, not
  ``@action``, as ``api/branches.py`` explains (the cross-tenant suite's classifier).

All of them answer ``Cache-Control: no-store`` (invitees' emails, and the link).

The other three routes are exempt from the active organization (design.md §3.5): the person has no
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
``409 already_member`` are the other refusals, and ``503 organization_busy`` a lock of the
organization not taken in time (Q-230). Every answer is ``Cache-Control: no-store``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.common.authz.roles import Role
from apps.identity.api.authentication import Unauthenticated
from apps.identity.selectors.auth_sessions import RequestAuthContext
from apps.tenancy.api.base import ORGANIZATION_BUSY_RESPONSE, TenantViewSet
from apps.tenancy.api.serializers.invitations import (
    AcceptedInvitationSerializer,
    CreatedInvitationSerializer,
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    JoinedOrganizationSerializer,
    invitation_view,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.selectors.invitations import (
    MyInvitation,
    OrganizationInvitation,
    get_invitation,
    list_my_pending,
    list_pending,
    to_invitations,
)
from apps.tenancy.services.fields import unknown_field_errors
from apps.tenancy.services.invitation_accept import (
    Invitee,
    accept_by_token,
    accept_from_session,
)
from apps.tenancy.services.invitation_manage import (
    INVITATION_NOT_FOUND,
    resend_invitation,
    revoke_invitation,
)
from apps.tenancy.services.invitations import create_invitation
from apps.tenancy.tasks import queue_invitation_email

INVITATIONS_TAG = "tenancy"
LOOKUP = "id"

INVITATION_ID = OpenApiParameter(
    name=LOOKUP,
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    description="La invitación.",
)


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


_UNAUTHORIZED = _problem(
    "code: unauthenticated · token_expired · token_invalid · session_revoked "
    '(con WWW-Authenticate: Bearer realm="hub")'
)
_CONFLICT = _problem("code: organization_suspended · already_member")
_NO_BODY = _problem("code: validation_error (el pedido no lleva cuerpo) · organization_required")
_MANAGE_FORBIDDEN = _problem(
    "code: forbidden (el rol no alcanza: un admin no gestiona invitaciones owner)"
)
_NOT_FOUND = _problem(
    "code: not_found (no existe o es de otra organización: el mismo cuerpo) · "
    "organization_not_found"
)


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


class InvitationViewSet(TenantViewSet):
    serializer_class = InvitationSerializer
    pagination_class = HubPageNumberPagination
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.INVITATION_LIST],
        "create": TENANCY_ACTIONS[TenancyAction.INVITATION_CREATE],
        "resend": TENANCY_ACTIONS[TenancyAction.INVITATION_RESEND],
        "revoke": TENANCY_ACTIONS[TenancyAction.INVITATION_REVOKE],
    }

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        return _no_store(super().finalize_response(request, response, *args, **kwargs))

    @extend_schema(
        operation_id="invitations_list",
        summary="Las invitaciones pendientes de la organización activa (owner y admin)",
        tags=[INVITATIONS_TAG],
        responses={
            200: InvitationSerializer(many=True),
            (403, PROBLEM_CONTENT_TYPE): _problem("code: forbidden (operator y viewer)"),
        },
    )
    def list(self, request: Request) -> Response:
        ctx = self.tenant
        page = self.paginate_queryset(list_pending(ctx, now=timezone.now()))
        views = [invitation_view(row, ctx) for row in to_invitations(page or [])]
        return self.get_paginated_response(self.get_serializer(views, many=True).data)

    @extend_schema(
        operation_id="invitations_create",
        summary="Invitar a alguien a la organización activa (el link se muestra una sola vez)",
        tags=[INVITATIONS_TAG],
        request=InvitationCreateSerializer,
        responses={
            201: CreatedInvitationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _problem(
                "code: validation_error (email inválido, rol desconocido u otra clave: "
                "unknown_field) · organization_required"
            ),
            (403, PROBLEM_CONTENT_TYPE): _problem(
                "code: forbidden (el rol no alcanza: un admin no invita owners)"
            ),
            (409, PROBLEM_CONTENT_TYPE): _problem(
                "code: already_member · invitation_pending (hay una vigente: reenviarla) · "
                "organization_suspended"
            ),
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def create(self, request: Request) -> Response:
        body = InvitationCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ctx = self.tenant
        created = create_invitation(ctx, body.invitee_email(), body.invited_role())
        queue_invitation_email(ctx, created.invitation_id, created.accept_url)  # flag, Q-207
        invitation = get_invitation(ctx, created.invitation_id)
        if invitation is None:  # just inserted in this organization; an invitation is never deleted
            raise AssertionError("the invitation just created is not found")
        view = invitation_view(invitation, ctx, actor_role=created.actor_role)
        data = {**self.get_serializer(view).data, "accept_url": created.accept_url}
        return Response(data, status=status.HTTP_201_CREATED)

    def _invitation_id(self) -> uuid.UUID:
        """The id of the URL; one that is not a UUID is the 404 of an unknown invitation."""
        try:
            return uuid.UUID(str(self.kwargs[LOOKUP]))
        except ValueError:
            raise NotFound(INVITATION_NOT_FOUND) from None

    @extend_schema(
        operation_id="invitations_resend",
        summary="Reenviar una invitación: revoca la anterior y emite otra (link una sola vez)",
        tags=[INVITATIONS_TAG],
        parameters=[INVITATION_ID],
        request=None,
        responses={
            201: CreatedInvitationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _NO_BODY,
            (403, PROBLEM_CONTENT_TYPE): _MANAGE_FORBIDDEN,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _problem(
                "code: invalid_transition (no está pendiente) · organization_suspended"
            ),
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def resend(self, request: Request, **kwargs: object) -> Response:
        NoBodySerializer(data=request.data).is_valid(raise_exception=True)
        ctx = self.tenant
        resent = resend_invitation(ctx, self._invitation_id())
        queue_invitation_email(ctx, resent.invitation_id, resent.accept_url)  # flag, Q-207
        view = invitation_view(self._read(resent.invitation_id), ctx, actor_role=resent.actor_role)
        data = {**self.get_serializer(view).data, "accept_url": resent.accept_url}
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="invitations_revoke",
        summary="Revocar una invitación pendiente (también con la organización suspendida)",
        tags=[INVITATIONS_TAG],
        parameters=[INVITATION_ID],
        request=None,
        responses={
            200: InvitationSerializer,
            (400, PROBLEM_CONTENT_TYPE): _NO_BODY,
            (403, PROBLEM_CONTENT_TYPE): _MANAGE_FORBIDDEN,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
            (409, PROBLEM_CONTENT_TYPE): _problem("code: invalid_transition (no está pendiente)"),
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
        },
    )
    def revoke(self, request: Request, **kwargs: object) -> Response:
        NoBodySerializer(data=request.data).is_valid(raise_exception=True)
        ctx = self.tenant
        revoked = revoke_invitation(ctx, self._invitation_id())
        invitation = self._read(revoked.invitation_id)
        view = invitation_view(invitation, ctx, actor_role=revoked.actor_role)
        return Response(self.get_serializer(view).data)

    def _read(self, invitation_id: uuid.UUID) -> OrganizationInvitation:
        invitation = get_invitation(self.tenant, invitation_id)
        if invitation is None:  # just written in this organization; an invitation is never deleted
            raise AssertionError("the invitation just written is not found")
        return invitation


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
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
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
            (503, PROBLEM_CONTENT_TYPE): ORGANIZATION_BUSY_RESPONSE,
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
