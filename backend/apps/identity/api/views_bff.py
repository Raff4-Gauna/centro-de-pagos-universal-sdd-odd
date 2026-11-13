"""``auth/bff/*``: what only the BFF may call (design.md §6.1, ADR-0004 §9).

``POST /api/auth/bff/login/start/`` (RF-IDA-01): the BFF sends the binding it keeps in
``__Host-cpu_login`` and where the person was going; it gets Google's authorization URL. Order of
design.md §4.1: credential (``BffAPIView``, ``404`` without it), 10/min per client IP (``429
rate_limited``, before anything else runs, so before Google), flag (``503 login_disabled``), body.
A hostile ``return_path`` is not an error: the attempt keeps "Inicio" instead (AC-IDA-19).

The serializers live here, apart from the public ones: these shapes are the BFF's, not the
browser's. Their errors never echo the input (design.md §7.5).
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import BFF_CREDENTIAL_SCHEME, PROBLEM
from apps.common.feature_flags import is_enabled
from apps.identity.api.bff_auth import BffAPIView
from apps.identity.api.throttles import LoginStartIpThrottle
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.secrets_format import is_login_binding
from apps.identity.services.login_start import LOGIN_FLAG, LoginDisabledError, start_login

BFF_TAG = "bff-internal"
_PROBLEM = {"$ref": f"#/components/schemas/{PROBLEM}"}
_BINDING_LENGTH = 43
# A security requirement, which is what drf-spectacular writes to the operation as it comes; its
# stubs type the argument as a list of names.
_BFF_SECURITY: Any = [{BFF_CREDENTIAL_SCHEME: []}]


class LoginDisabled(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = IdentityErrorCode.LOGIN_DISABLED.value


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
