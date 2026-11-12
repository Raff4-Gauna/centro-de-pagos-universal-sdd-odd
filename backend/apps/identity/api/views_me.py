"""``GET /api/me/`` (RF-IDA-06, RN-IDA-18, RN-IDA-22, design.md §6.2).

The person the Bearer names (``request.auth``, ``HubJWTAuthentication``) and the memberships that
SPEC-02's selector lists for them, resolved through the port (``EmptyMembershipSelector`` until
``T-TEN-12``). It takes no user identifier, so nobody reads anyone else through it. A person with
no active membership gets ``memberships: []``, never a ``403`` (RN-IDA-22). Default permission:
any authenticated person, whatever their role; anonymous → ``401 unauthenticated``.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.identity.api.authentication import Unauthenticated
from apps.identity.api.serializers import MeSerializer
from apps.identity.ports.registry import get_membership_selector
from apps.identity.selectors.auth_sessions import RequestAuthContext

_PROBLEM = {"$ref": f"#/components/schemas/{PROBLEM}"}


class MeView(APIView):
    @extend_schema(
        operation_id="me_retrieve",
        summary="La persona autenticada y sus memberships activas",
        tags=["identity"],
        responses={
            200: MeSerializer,
            (401, PROBLEM_CONTENT_TYPE): OpenApiResponse(
                response=_PROBLEM,
                description=(
                    "code: unauthenticated · token_expired · token_invalid · session_revoked "
                    '(con WWW-Authenticate: Bearer realm="hub")'
                ),
            ),
        },
    )
    def get(self, request: Request) -> Response:
        context = request.auth
        if not isinstance(context, RequestAuthContext):  # only a Hub session names a person
            raise Unauthenticated
        user = context.user
        memberships = get_membership_selector().list_active_memberships(user.pk)
        body = MeSerializer(
            {
                "id": user.pk,
                "email": user.email,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "memberships": memberships,
            }
        ).data
        # Personal data: no shared or browser cache keeps a copy.
        return Response(body, headers={"Cache-Control": "no-store"})
