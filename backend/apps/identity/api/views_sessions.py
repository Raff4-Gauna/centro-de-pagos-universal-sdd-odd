"""The person's own sessions, for "Seguridad" (RF-IDA-07, RN-IDA-24, design.md §6.2).

``GET /api/auth/sessions/``: the live sessions of the person the Bearer names, last used first, with
``is_current`` on the one of the request (``request.auth.sid``). Browser, OS and dates; never an IP
(RNF-IDA-05). Paginated as SPEC-02's lists (``HubPageNumberPagination``: 50 per page, ``page_size``
up to 200), so the contract does not change when a person has many: there is no cap on concurrent
sessions (Q-113), and what bounds the active ones is the 30-day absolute expiry (RN-IDA-11).
``POST /api/auth/sessions/{id}/revoke/``: ends that session, the current one included; one of
another person, already ended or unknown is the same ``404 not_found`` (AC-IDA-25).
``POST /api/auth/sessions/revoke-others/``: ends every session but the current (AC-IDA-33).

They take no user identifier: the user is always the authenticated one. Default permission: any
authenticated person, whatever their role or memberships; anonymous → ``401 unauthenticated``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api.pagination import HubPageNumberPagination
from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import PROBLEM
from apps.identity.api.authentication import Unauthenticated
from apps.identity.api.serializers import SessionSerializer
from apps.identity.selectors.auth_sessions import RequestAuthContext, list_active_sessions
from apps.identity.services.sessions import (
    SessionNotFoundError,
    revoke_other_sessions,
    revoke_own_session,
)

SESSIONS_TAG = "identity"
_NO_STORE = {"Cache-Control": "no-store"}
_UNAUTHORIZED = OpenApiResponse(
    response={"$ref": f"#/components/schemas/{PROBLEM}"},
    description=(
        "code: unauthenticated · token_expired · token_invalid · session_revoked "
        '(con WWW-Authenticate: Bearer realm="hub")'
    ),
)
_NOT_FOUND = OpenApiResponse(
    response={"$ref": f"#/components/schemas/{PROBLEM}"},
    description="code: not_found (también si la sesión es de otra persona o ya terminó)",
)


def _context(request: Request) -> RequestAuthContext:
    context = request.auth
    if not isinstance(context, RequestAuthContext):  # only a Hub session names a person
        raise Unauthenticated
    return context


# A ListAPIView for its pagination and contract only; the rows are dicts built from the sessions.
class SessionListView(generics.ListAPIView[Any]):
    serializer_class = SessionSerializer
    pagination_class = HubPageNumberPagination

    @extend_schema(
        operation_id="auth_sessions_list",
        summary="Las sesiones activas de la persona autenticada",
        tags=[SESSIONS_TAG],
        responses={
            200: SessionSerializer(many=True),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        context = _context(request)
        sessions = list_active_sessions(user_id=context.user.pk, now=timezone.now())
        page = self.paginate_queryset(sessions)
        rows: list[dict[str, Any]] = [
            {
                "id": session.pk,
                "browser": session.client_browser or None,
                "os": session.client_os or None,
                "created_at": session.created_at,
                "last_used_at": session.last_used_at,
                "is_current": session.pk == context.sid,
            }
            for session in page or ()
        ]
        response = self.get_paginated_response([SessionSerializer(row).data for row in rows])
        # Personal data: no shared or browser cache keeps a copy.
        response["Cache-Control"] = "no-store"
        return response


class SessionRevokeView(APIView):
    @extend_schema(
        operation_id="auth_sessions_revoke",
        summary="Cierra una sesión propia",
        tags=[SESSIONS_TAG],
        request=None,
        responses={
            204: OpenApiResponse(description="La sesión quedó cerrada."),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
            (404, PROBLEM_CONTENT_TYPE): _NOT_FOUND,
        },
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        context = _context(request)
        try:
            revoke_own_session(user_id=context.user.pk, session_id=session_id, now=timezone.now())
        except SessionNotFoundError:
            raise NotFound from None
        return Response(status=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


class RevokeOtherSessionsView(APIView):
    @extend_schema(
        operation_id="auth_sessions_revoke_others",
        summary="Cierra todas las sesiones propias salvo la actual",
        tags=[SESSIONS_TAG],
        request=None,
        responses={
            204: OpenApiResponse(description="Solo queda activa la sesión actual."),
            (401, PROBLEM_CONTENT_TYPE): _UNAUTHORIZED,
        },
    )
    def post(self, request: Request) -> Response:
        context = _context(request)
        revoke_other_sessions(
            user_id=context.user.pk, current_session_id=context.sid, now=timezone.now()
        )
        return Response(status=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)
