"""``auth/bff/*``: what only the BFF may call (design.md §6.1, ADR-0004 §9).

``POST /api/auth/bff/login/start/`` (RF-IDA-01): the BFF sends the binding it keeps in
``__Host-cpu_login`` and where the person was going; it gets Google's authorization URL. Order of
design.md §4.1: credential (``BffAPIView``, ``404`` without it), 10/min per client IP (``429
rate_limited``, before anything else runs, so before Google), flag (``503 login_disabled``), body.
A hostile ``return_path`` is not an error: the attempt keeps "Inicio" instead (AC-IDA-19).

``POST /api/auth/bff/refresh/`` (RF-IDA-04): the BFF sends the refresh token of ``__Host-cpu_rt``
and gets a new access token and, unless it falls in the grace window, a new refresh token
(``services/refresh.py``). Credential first, then 60/min per client IP and 30/min per session
(``429 rate_limited``). Any failure is ``401`` with ``token_invalid`` (no such token, or a body
without one) or ``session_revoked`` (the session cannot go on), never ``400``: the BFF only needs to
know whether to clear the cookies. ``Authorization`` is not read (``BffAPIView``), so neither a
person's JWT nor an ERP API key counts as a refresh (AC-IDA-22). The login flag does not apply
(ADR-0004 §14): sessions already open keep refreshing with it off.

The serializers live here, apart from the public ones: these shapes are the BFF's, not the
browser's. Their errors never echo the input (design.md §7.5).
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import BFF_CREDENTIAL_SCHEME, PROBLEM
from apps.common.feature_flags import is_enabled
from apps.identity.api.bff_auth import BffAPIView
from apps.identity.api.throttles import (
    LoginStartIpThrottle,
    RefreshIpThrottle,
    RefreshSessionThrottle,
)
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.secrets_format import is_login_binding
from apps.identity.services.login_start import LOGIN_FLAG, LoginDisabledError, start_login
from apps.identity.services.refresh import refresh_session
from apps.identity.tokens.access_token import ACCESS_TOKEN_TTL_SECONDS

BFF_TAG = "bff-internal"
_PROBLEM = {"$ref": f"#/components/schemas/{PROBLEM}"}
_BINDING_LENGTH = 43
# A security requirement, which is what drf-spectacular writes to the operation as it comes; its
# stubs type the argument as a list of names.
_BFF_SECURITY: Any = [{BFF_CREDENTIAL_SCHEME: []}]


class LoginDisabled(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = IdentityErrorCode.LOGIN_DISABLED.value


# Fixed per code: the detail never says what was wrong with the token.
_REFRESH_DETAILS = {
    IdentityErrorCode.TOKEN_INVALID: "El token de refresco no es válido.",
    IdentityErrorCode.SESSION_REVOKED: "La sesión ya no está activa.",
}


class RefreshRefused(APIException):
    """Not ``AuthenticationFailed``: DRF turns that into ``403`` on a view with no authenticator."""

    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, code: IdentityErrorCode) -> None:
        super().__init__(detail=_REFRESH_DETAILS[code], code=code.value)


def _login_binding(value: str) -> None:
    if not is_login_binding(value):
        raise serializers.ValidationError("Formato inválido.", code="invalid")


# Comments, not docstrings: drf-spectacular would publish a docstring as the description.
# login_binding: 32 random bytes in base64url, created by the BFF (design.md §6.3).
# return_path: any text is accepted; one that is not an internal path is replaced, not refused.
class LoginStartRequestSerializer(serializers.Serializer[dict[str, Any]]):
    login_binding = serializers.CharField(
        min_length=_BINDING_LENGTH,
        max_length=_BINDING_LENGTH,
        trim_whitespace=False,
        validators=[_login_binding],
    )
    return_path = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, trim_whitespace=False
    )

    class Meta:
        ref_name = "LoginStart"  # published as LoginStartRequest (split components)


class LoginStartResponseSerializer(serializers.Serializer[dict[str, Any]]):
    authorization_url = serializers.URLField(read_only=True)

    class Meta:
        ref_name = "LoginStartResponse"


class LoginStartView(BffAPIView):
    throttle_classes = (LoginStartIpThrottle,)

    @extend_schema(
        operation_id="auth_bff_login_start",
        summary="Inicia un login con Google (solo BFF)",
        description=(
            "Crea el intento de login y devuelve la URL de autorización de Google. Un return_path "
            "que no es una ruta interna se reemplaza por Inicio."
        ),
        tags=[BFF_TAG],
        auth=_BFF_SECURITY,
        request=LoginStartRequestSerializer,
        responses={
            200: LoginStartResponseSerializer,
            (429, PROBLEM_CONTENT_TYPE): OpenApiResponse(
                response=_PROBLEM, description="code: rate_limited (con Retry-After)"
            ),
            (503, PROBLEM_CONTENT_TYPE): OpenApiResponse(
                response=_PROBLEM, description="code: login_disabled"
            ),
        },
    )
    def post(self, request: Request) -> Response:
        # The flag before the body (design.md §4.1): off, a malformed body is 503 too.
        if not is_enabled(LOGIN_FLAG):
            raise LoginDisabled
        body = LoginStartRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            authorization_url = start_login(
                return_path=body.validated_data.get("return_path"),
                login_binding=body.validated_data["login_binding"],
            )
        except LoginDisabledError:
            raise LoginDisabled from None
        # The URL carries state and nonce: no cache keeps a copy.
        return Response(
            {"authorization_url": authorization_url}, headers={"Cache-Control": "no-store"}
        )


# refresh_token: rt1.<sid>.<secret>, the one in __Host-cpu_rt (design.md §4.5).
class RefreshRequestSerializer(serializers.Serializer[dict[str, Any]]):
    refresh_token = serializers.CharField(trim_whitespace=False)

    class Meta:
        ref_name = "Refresh"  # published as RefreshRequest (split components)


# refresh_token is null in the grace window: the BFF then keeps the cookie it has (design.md §4.5).
# session_expires_in: seconds to the idle deadline, the Max-Age of __Host-cpu_rt (design.md §7.1).
class RefreshResponseSerializer(serializers.Serializer[dict[str, Any]]):
    access_token = serializers.CharField(read_only=True)
    access_expires_in = serializers.IntegerField(read_only=True)
    refresh_token = serializers.CharField(read_only=True, allow_null=True)
    session_expires_in = serializers.IntegerField(read_only=True)

    class Meta:
        ref_name = "RefreshResponse"


class RefreshView(BffAPIView):
    # IP first: a made-up session id spends the client's quota before getting one of its own.
    throttle_classes = (RefreshIpThrottle, RefreshSessionThrottle)

    @extend_schema(
        operation_id="auth_bff_refresh",
        summary="Refresca la sesión (solo BFF)",
        description=(
            "Rota el refresh token y devuelve un token de acceso nuevo. Dentro de la ventana de "
            "gracia refresh_token es null: el BFF conserva la cookie que ya tiene."
        ),
        tags=[BFF_TAG],
        auth=_BFF_SECURITY,
        request=RefreshRequestSerializer,
        responses={
            200: RefreshResponseSerializer,
            (401, PROBLEM_CONTENT_TYPE): OpenApiResponse(
                response=_PROBLEM, description="code: token_invalid | session_revoked"
            ),
            (429, PROBLEM_CONTENT_TYPE): OpenApiResponse(
                response=_PROBLEM, description="code: rate_limited (con Retry-After)"
            ),
        },
    )
    def post(self, request: Request) -> Response:
        body = RefreshRequestSerializer(data=request.data)
        if not body.is_valid():
            raise RefreshRefused(IdentityErrorCode.TOKEN_INVALID)
        try:
            refreshed = refresh_session(body.validated_data["refresh_token"], now=timezone.now())
        except IdentityError as error:
            raise RefreshRefused(error.code) from None
        payload = {
            "access_token": refreshed.access_token,
            "access_expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "refresh_token": refreshed.refresh_token,
            "session_expires_in": refreshed.session_expires_in,
        }
        # Tokens: no cache keeps a copy.
        return Response(payload, headers={"Cache-Control": "no-store"})
