"""A person's authentication on the API (RF-IDA-03, RN-IDA-08, RN-IDA-19, RN-IDA-20, design §4.4).

``HubJWTAuthentication`` is the only authentication class of the API (``DEFAULT_AUTHENTICATION_
CLASSES``): it accepts the Hub's own access JWT as ``Authorization: Bearer`` and nothing else, so
neither a Google token nor an ERP API key (SPEC-11) passes as a person's session (RN-IDA-19). Django
never authenticates by cookie: the BFF holds the cookies and sends the Bearer (ADR-0004).

On every request it verifies the token locally and then asks ``get_request_auth_context`` whether
the session is still live (RN-IDA-20): one query, no cache. Each failure is a ``401`` with one of
the codes of spec §11 and ``WWW-Authenticate: Bearer realm="hub"``; no part of the token reaches the
response or a log (C-06). Without an ``Authorization: Bearer`` it authenticates nobody, so a route
that is open on purpose (``AllowAny``) still answers an anonymous caller.

``IsAuthenticated`` is the default permission (deny by default): a view that declares none refuses
an anonymous caller with ``401 unauthenticated`` (DRF's own says ``not_authenticated``).

``HubBearerScheme`` documents it in the contract as the ``HubBearer`` security scheme; it lives here
so that drf-spectacular finds it whenever it resolves the class (it registers on import).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions, permissions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.selectors.auth_sessions import RequestAuthContext, get_request_auth_context
from apps.identity.tokens.access_token import AccessTokenError, verify_access_token

if TYPE_CHECKING:
    from drf_spectacular.openapi import AutoSchema
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from apps.identity.models import User

AUTH_SCHEME = b"bearer"
WWW_AUTHENTICATE = 'Bearer realm="hub"'

# Fixed per code: the detail never says what in the token was wrong.
_DETAILS = {
    IdentityErrorCode.TOKEN_EXPIRED: "El token de acceso venció.",
    IdentityErrorCode.TOKEN_INVALID: "El token de acceso no es válido.",
    IdentityErrorCode.SESSION_REVOKED: "La sesión ya no está activa.",
}


class Unauthenticated(exceptions.NotAuthenticated):
    default_detail = "Se requiere una sesión."
    default_code = IdentityErrorCode.UNAUTHENTICATED.value


def _rejected(code: IdentityErrorCode) -> exceptions.AuthenticationFailed:
    return exceptions.AuthenticationFailed(detail=_DETAILS[code], code=code.value)


class HubJWTAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[User, RequestAuthContext] | None:
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != AUTH_SCHEME:
            return None
        if len(parts) != 2:  # the scheme and the token
            raise _rejected(IdentityErrorCode.TOKEN_INVALID)
        try:
            token = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise _rejected(IdentityErrorCode.TOKEN_INVALID) from None
        try:
            identity = verify_access_token(token)
        except AccessTokenError as error:
            raise _rejected(error.code) from None
        context = get_request_auth_context(
            session_id=identity.session_id, user_id=identity.user_id, now=timezone.now()
        )
        if context is None:
            raise _rejected(IdentityErrorCode.SESSION_REVOKED)
        return context.user, context

    def authenticate_header(self, request: Request) -> str:
        return WWW_AUTHENTICATE


class IsAuthenticated(permissions.IsAuthenticated):
    """DRF's ``IsAuthenticated`` with the module's code: ``401 unauthenticated`` (spec §11)."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            raise Unauthenticated
        return True


class HubBearerScheme(OpenApiAuthenticationExtension):
    """``HubJWTAuthentication`` in the OpenAPI contract: ``Authorization: Bearer <Hub JWT>``."""

    target_class = HubJWTAuthentication
    name = "HubBearer"

    def get_security_definition(self, auto_schema: AutoSchema) -> dict[str, str]:
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
