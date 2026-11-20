"""Accept an invitation with its token (RN-TEN-11, RN-TEN-12, design.md §3.5, §4.4, §6).

``POST /api/invitations/accept/`` (``AcceptInvitationView``) is exempt from the active organization
(design.md §3.5): the person has no membership in it yet, so it is not a ``TenantViewSet`` and
``X-Organization-Id`` is neither required nor read; the organization is the invitation's. Only a
person with a Hub session reaches it (``401`` otherwise); the invitee is always the authenticated
one, by the email of their Google account.

The body is ``{token}``; the token is hashed before anything else and never shows up in the
response, in an error or in a log (RNF-TEN-03, C-06). ``200`` is the membership created; the
refusals are ``400 invitation_invalid`` with ``reason`` (``not_found``, ``email_mismatch``,
``revoked``, ``used``, ``expired``), ``409 organization_suspended`` and ``409 already_member``.
Every answer is ``Cache-Control: no-store``.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.identity.api.authentication import Unauthenticated
from apps.identity.selectors.auth_sessions import RequestAuthContext
from apps.tenancy.api.serializers.invitations import (
    AcceptedInvitationSerializer,
    InvitationAcceptSerializer,
)
from apps.tenancy.services.invitation_accept import Invitee, accept_by_token

INVITATIONS_TAG = "tenancy"


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"$ref": f"#/components/schemas/{PROBLEM}"}, description=description
    )


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
            (401, PROBLEM_CONTENT_TYPE): _problem(
                "code: unauthenticated · token_expired · token_invalid · session_revoked "
                '(con WWW-Authenticate: Bearer realm="hub")'
            ),
            (409, PROBLEM_CONTENT_TYPE): _problem("code: organization_suspended · already_member"),
        },
    )
    def post(self, request: Request) -> Response:
        context = request.auth
        if not isinstance(context, RequestAuthContext):  # only a Hub session names a person
            raise Unauthenticated
        body = InvitationAcceptSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        invitee = Invitee(user_id=context.user.pk, email=context.user.email)
        accepted = accept_by_token(body.validated_data["token"], invitee)
        return Response(AcceptedInvitationSerializer(accepted).data)

    def finalize_response(
        self, request: Request, response: Response, *args: object, **kwargs: object
    ) -> Response:
        """``no-store`` on the errors too: they say what this person's invitation is."""
        final = super().finalize_response(request, response, *args, **kwargs)
        final["Cache-Control"] = "no-store"
        return final
