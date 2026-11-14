"""``auth/bff/*``: what only the BFF may call (design.md §6.1, ADR-0004 §9).

``POST /api/auth/bff/login/start/`` (RF-IDA-01): the BFF sends the binding it keeps in
``__Host-cpu_login`` and where the person was going; it gets Google's authorization URL.
``POST /api/auth/bff/login/complete/`` (RF-IDA-02): the BFF relays Google's redirect (``state``,
``code`` or ``error``) with that binding; it gets the session's tokens and where to go. The
person's User-Agent comes in ``X-Hub-Client-UA``: only its browser and OS reach the session.

Order of design.md §4.1: credential (``BffAPIView``, ``404`` without it), 10/min per client IP
(``429 rate_limited``, before anything else runs, so before Google), flag (``503
login_disabled``), body. A hostile ``return_path`` is not an error: the attempt keeps "Inicio"
instead (AC-IDA-19).

``POST /api/auth/bff/refresh/`` (RF-IDA-04): the BFF sends the refresh token of ``__Host-cpu_rt``
and gets a new access token and, unless it falls in the grace window, a new refresh token
(``services/refresh.py``). Credential first, then 60/min per client IP and 30/min per session
(``429 rate_limited``). Any failure is ``401`` with ``token_invalid`` (no such token, or a body
without one) or ``session_revoked`` (the session cannot go on), never ``400``: the BFF only needs to
know whether to clear the cookies. ``Authorization`` is not read (``BffAPIView``), so neither a
person's JWT nor an ERP API key counts as a refresh (AC-IDA-22). The login flag does not apply
(ADR-0004 §14): sessions already open keep refreshing with it off.

``POST /api/auth/bff/logout/`` (RF-IDA-05, RN-IDA-14): the BFF sends what it holds of the session
(the refresh token, the access JWT, or both) and ``reason`` (``superseded`` for the login over a
previous session; a missing or unknown one is ``logout``); the session ends
(``services/logout.py``). ``204``, empty, for every JSON body: with a session or without, or with a
body that names none, so the answer says nothing of the tokens. A body that is not JSON never gets
that far: DRF answers ``400 parse_error`` (malformed) or ``415`` (another content type) before the
view, as the contract's ``4XX`` says. The BFF clears its cookies whatever Django answers
(``T-IDA-25``). No throttle: the platform's default would key every person on the BFF's address
and turn a logout into a ``429``; a logout reveals nothing and the credential already keeps
everybody else out. The login flag does not apply either.

The shapes live in ``serializers.py``.

The callback's codes keep the status of design.md §6.1. ``UserProvisioningError`` has none of its
own: no rule explains it, so it is ``500 internal_error``, without detail nor personal data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.schema import BFF_CREDENTIAL_SCHEME, PROBLEM
from apps.common.feature_flags import is_enabled
from apps.common.logging import get_logger
from apps.identity.api.bff_auth import BffAPIView
from apps.identity.api.serializers import (
    LoginCompleteRequestSerializer,
    LoginCompleteResponseSerializer,
    LoginStartRequestSerializer,
    LoginStartResponseSerializer,
    LogoutRequestSerializer,
    RefreshRequestSerializer,
    RefreshResponseSerializer,
)
from apps.identity.api.throttles import (
    LoginCompleteIpThrottle,
    LoginStartIpThrottle,
    RefreshIpThrottle,
    RefreshSessionThrottle,
)
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.models import RevokeReason
from apps.identity.services.login_complete import complete_login
from apps.identity.services.login_start import LOGIN_FLAG, LoginDisabledError, start_login
from apps.identity.services.logout import LOGOUT_EVENT, logout
from apps.identity.services.refresh import refresh_session
from apps.identity.tokens.access_token import ACCESS_TOKEN_TTL_SECONDS

BFF_TAG = "bff-internal"
CLIENT_UA_HEADER = "X-Hub-Client-UA"
_PROBLEM = {"$ref": f"#/components/schemas/{PROBLEM}"}
# A security requirement, which is what drf-spectacular writes to the operation as it comes; its
# stubs type the argument as a list of names.
_BFF_SECURITY: Any = [{BFF_CREDENTIAL_SCHEME: []}]
_NO_STORE = {"Cache-Control": "no-store"}

logger = get_logger(__name__)

# Status and fixed detail of each code (spec §11): the detail says no more than the code, never an
# email nor anything Google sent. A 5xx carries none (problems.py).
_LOGIN_ERRORS: dict[IdentityErrorCode, tuple[int, str | None]] = {
    IdentityErrorCode.GOOGLE_AUTH_FAILED: (400, "No se pudo validar el ingreso con Google."),
    IdentityErrorCode.LOGIN_CANCELLED: (400, "El ingreso con Google se canceló."),
    IdentityErrorCode.EMAIL_NOT_VERIFIED: (
        403,
        "La cuenta de Google no tiene el email verificado.",
    ),
    IdentityErrorCode.NOT_INVITED: (403, "No hay una invitación vigente para esta cuenta."),
    IdentityErrorCode.USER_INACTIVE: (403, "El usuario está desactivado."),
    IdentityErrorCode.IDENTITY_CONFLICT: (409, "El email ya pertenece a otro usuario."),
    IdentityErrorCode.GOOGLE_UNAVAILABLE: (503, None),
    IdentityErrorCode.LOGIN_DISABLED: (503, None),
}


class LoginDisabled(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = IdentityErrorCode.LOGIN_DISABLED.value


class LoginFailed(APIException):
    """One of the callback's codes, with its status and fixed detail."""

    def __init__(self, code: IdentityErrorCode) -> None:
        self.status_code, detail = _LOGIN_ERRORS[code]
        super().__init__(detail=detail, code=code.value)


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


def _problems(*described: tuple[int, str]) -> dict[Any, OpenApiResponse]:
    return {
        (status_code, PROBLEM_CONTENT_TYPE): OpenApiResponse(
            response=_PROBLEM, description=description
        )
        for status_code, description in described
    }


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
            **_problems(
                (429, "code: rate_limited (con Retry-After)"), (503, "code: login_disabled")
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
        return Response({"authorization_url": authorization_url}, headers=_NO_STORE)


class LoginCompleteView(BffAPIView):
    throttle_classes = (LoginCompleteIpThrottle,)

    @extend_schema(
        operation_id="auth_bff_login_complete",
        summary="Completa un login con Google (solo BFF)",
        description=(
            "Consume el intento de login (un solo uso, 10 minutos), canjea el código con Google, "
            "valida el ID token y abre la sesión. Los tokens son solo para el BFF."
        ),
        tags=[BFF_TAG],
        auth=_BFF_SECURITY,
        parameters=[
            OpenApiParameter(
                name=CLIENT_UA_HEADER,
                location=OpenApiParameter.HEADER,
                required=False,
                type=str,
                description=(
                    "User-Agent del navegador de la persona. Solo se guardan el navegador y el "
                    "sistema operativo resumidos, nunca el valor completo."
                ),
            )
        ],
        request=LoginCompleteRequestSerializer,
        responses={
            200: LoginCompleteResponseSerializer,
            **_problems(
                (400, "code: google_auth_failed · login_cancelled · validation_error"),
                (403, "code: email_not_verified · not_invited · user_inactive"),
                (409, "code: identity_conflict"),
                (429, "code: rate_limited (con Retry-After)"),
                (503, "code: google_unavailable · login_disabled"),
            ),
        },
    )
    def post(self, request: Request) -> Response:
        # The flag before the body, as in start: no attempt is consumed with the login off.
        if not is_enabled(LOGIN_FLAG):
            raise LoginDisabled
        body = LoginCompleteRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            login = complete_login(
                state=data["state"],
                login_binding=data["login_binding"],
                code=data.get("code"),
                error=data.get("error"),
                # Only this view's caller has the BFF credential (BffAPIView): nobody else's counts.
                client_user_agent=request.headers.get(CLIENT_UA_HEADER),
            )
        except IdentityError as error:
            if error.code not in _LOGIN_ERRORS:
                raise
            raise LoginFailed(error.code) from None
        result = LoginCompleteResponseSerializer(
            {
                "access_token": login.access_token,
                "access_expires_in": login.access_expires_in,
                "refresh_token": login.refresh_token,
                "session_id": login.session_id,
                "session_expires_in": login.session_expires_in,
                "return_path": login.return_path,
            }
        ).data
        # Tokens: no cache keeps a copy (design.md §7.5).
        return Response(result, headers=_NO_STORE)


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
            **_problems(
                (401, "code: token_invalid | session_revoked"),
                (429, "code: rate_limited (con Retry-After)"),
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
        return Response(payload, headers=_NO_STORE)


class LogoutView(BffAPIView):
    throttle_classes = ()  # see the module's docstring: a logout is never a 429

    @extend_schema(
        operation_id="auth_bff_logout",
        summary="Cierra la sesión (solo BFF)",
        description=(
            "Revoca la sesión que nombran el refresh token o el token de acceso, este aunque haya "
            "vencido. Responde 204 siempre, haya o no una sesión que cerrar."
        ),
        tags=[BFF_TAG],
        auth=_BFF_SECURITY,
        request=LogoutRequestSerializer,
        responses={204: OpenApiResponse(description="Siempre, sin cuerpo.")},
    )
    def post(self, request: Request) -> Response:
        data = request.data
        body = LogoutRequestSerializer(data=data)
        if not body.is_valid() and isinstance(data, Mapping) and set(body.errors) == {"reason"}:
            # Planner's decision (2026-11-13): the person asked to leave, so a bad reason still
            # logs out; a session left alive is the less safe failure. Logged without the body.
            logger.warning(LOGOUT_EVENT, result="invalid_reason")
            body = LogoutRequestSerializer(data={k: v for k, v in data.items() if k != "reason"})
        if not body.is_valid():
            # No token to take from it (not an object, a token that is no text): nothing ends.
            logger.warning(LOGOUT_EVENT, result="invalid_body")
            return Response(status=status.HTTP_204_NO_CONTENT)
        logout(
            refresh_token=body.validated_data.get("refresh_token"),
            access_token=body.validated_data.get("access_token"),
            reason=RevokeReason(body.validated_data.get("reason", RevokeReason.LOGOUT)),
            now=timezone.now(),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
