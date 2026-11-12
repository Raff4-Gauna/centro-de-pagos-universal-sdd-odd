"""``HubJWTAuthentication`` and deny by default at API level (RF-IDA-03, RN-IDA-08, RN-IDA-19,
RN-IDA-20, RNF-IDA-02; AC-IDA-10, 11, 12, 22, 26, 34).

``/api/me`` arrives with T-IDA-07, so this module is its own urlconf: a view that declares no
permission (what any new route gets), one open on purpose and one of ``auth/bff/*``. The hostile
tokens are those of ``tests/identity/tokens``: what is new here is the request, the ``401`` it
answers and the session check behind it.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest import mock

import jwt
import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import URLPattern, URLResolver, path
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.identity.api.authentication import HubJWTAuthentication, IsAuthenticated
from apps.identity.api.bff_auth import BffAPIView
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.session_policy import ACCESS_TOKEN_LIFETIME
from apps.identity.models import AuthSession, RevokeReason, User
from apps.identity.selectors.auth_sessions import RequestAuthContext
from apps.identity.services.session_lifecycle import open_session, revoke
from apps.identity.tokens import access_token
from apps.identity.tokens.access_token import issue_access_token
from config import urls as public_urls
from tests.identity.tokens.test_access_token import (
    by_hand,
    claims,
    forge,
    header,
    other_key,
    rsa_key,
)

pytestmark = [pytest.mark.urls(__name__), pytest.mark.django_db]

handler404 = public_urls.handler404
handler500 = public_urls.handler500

PROTECTED = "/api/test/protected"
OPEN = "/api/test/open"
BFF_ROUTE = "/api/test/bff"
BFF_CREDENTIAL = "bff-test-value"
CHALLENGE = 'Bearer realm="hub"'
# Past the 60 s of tolerance, with room for a slow run.
EXPIRED_ISSUED_AGO = 900 + 65


class _Protected(APIView):
    """No ``permission_classes``: what every new route of the API gets."""

    def get(self, request: Request) -> Response:
        context = request.auth
        assert isinstance(context, RequestAuthContext)
        assert context.user is request.user
        return Response({"user": str(context.user.pk), "sid": str(context.sid)})


class _Open(APIView):
    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        return Response({"anonymous": request.user is None})


class _Bff(BffAPIView):
    def post(self, request: Request) -> Response:
        return Response({"reached": True})


urlpatterns: list[URLPattern | URLResolver] = [
    *public_urls.urlpatterns,
    path("api/test/protected", _Protected.as_view()),
    path("api/test/open", _Open.as_view()),
    path("api/test/bff", _Bff.as_view()),
]


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-auth", email="ana@example.com")


@pytest.fixture
def session(user: User) -> AuthSession:
    return open_session(user, now=timezone.now()).session


def token_of(session: AuthSession, *, issued_ago: float = 0) -> str:
    moment = timezone.now() - timedelta(seconds=issued_ago)
    return issue_access_token(user_id=session.user_id, session_id=session.pk, now=moment)


def get(client: Client, authorization: str | None, url: str = PROTECTED) -> Any:
    headers = {} if authorization is None else {"Authorization": authorization}
    return client.get(url, headers=headers)


def assert_401(response: Any, code: IdentityErrorCode, token: str = "") -> None:
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == CHALLENGE
    assert response["Content-Type"] == "application/problem+json"
    body = json.loads(response.content)
    assert body["code"] == code.value
    if token:  # nothing of the token travels back (C-06)
        for part in token.split("."):
            assert not part or part not in response.content.decode()


# --- Deny by default -----------------------------------------------------------------------------


def test_no_session_authentication_in_settings() -> None:
    defaults = api_settings.user_settings
    assert defaults["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "apps.identity.api.authentication.HubJWTAuthentication"
    ]
    assert defaults["DEFAULT_PERMISSION_CLASSES"] == [
        "apps.identity.api.authentication.IsAuthenticated"
    ]
    assert APIView.authentication_classes == [HubJWTAuthentication]
    assert APIView.permission_classes == [IsAuthenticated]
    for forbidden in (SessionAuthentication, BasicAuthentication):
        assert forbidden not in APIView.authentication_classes


def test_new_route_without_permission_is_401(client: Client) -> None:
    assert_401(get(client, None), IdentityErrorCode.UNAUTHENTICATED)


def test_RN_IDA_19_a_django_session_cookie_is_not_a_session(client: Client) -> None:
    client.cookies["sessionid"] = "anything"
    client.cookies["__Host-cpu_at"] = "anything"
    assert_401(get(client, None), IdentityErrorCode.UNAUTHENTICATED)


def test_open_routes_stay_open(client: Client) -> None:
    assert client.get("/healthz").status_code == 200
    assert get(client, None, OPEN).json() == {"anonymous": True}


@pytest.mark.urls("config.urls_dev")
@pytest.mark.parametrize("route", ["/api/dev/schema/", "/api/dev/docs/"])
def test_dev_schema_and_docs_stay_open(client: Client, route: str) -> None:
    assert client.get(route).status_code == 200


def test_bff_routes_keep_their_own_credential(
    client: Client, settings: SettingsWrapper, session: AuthSession
) -> None:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(BFF_CREDENTIAL),)
    garbage = {"Authorization": "Bearer not-a-token"}
    response = client.post(BFF_ROUTE, headers={"X-Hub-Bff-Credential": BFF_CREDENTIAL, **garbage})
    assert response.json() == {"reached": True}
    # A person's valid JWT does not open them: without the credential they do not exist.
    bearer = {"Authorization": f"Bearer {token_of(session)}"}
    assert client.post(BFF_ROUTE, headers=bearer).status_code == 404


# --- The session behind the JWT (RN-IDA-20) ------------------------------------------------------


def test_RF_IDA_03_valid_token_attaches_user_and_session(
    client: Client, session: AuthSession
) -> None:
    response = get(client, f"Bearer {token_of(session)}")
    assert response.status_code == 200
    assert response.json() == {"user": str(session.user_id), "sid": str(session.pk)}


def test_AC_IDA_26_revoked_session_next_request_401(client: Client, session: AuthSession) -> None:
    authorization = f"Bearer {token_of(session)}"
    assert get(client, authorization).status_code == 200
    assert revoke(session.pk, reason=RevokeReason.USER_REVOKED, now=timezone.now())
    assert_401(get(client, authorization), IdentityErrorCode.SESSION_REVOKED)


def test_RN_IDA_07_deactivated_user_next_request_401(client: Client, session: AuthSession) -> None:
    authorization = f"Bearer {token_of(session)}"
    assert get(client, authorization).status_code == 200
    User.objects.filter(pk=session.user_id).update(is_active=False, deactivated_at=timezone.now())
    assert_401(get(client, authorization), IdentityErrorCode.SESSION_REVOKED)


def test_RN_IDA_20_session_past_its_idle_deadline_is_401(
    client: Client, session: AuthSession
) -> None:
    authorization = f"Bearer {token_of(session)}"
    AuthSession.objects.filter(pk=session.pk).update(idle_expires_at=timezone.now())
    assert_401(get(client, authorization), IdentityErrorCode.SESSION_REVOKED)


def test_RN_IDA_20_unknown_session_or_another_users_is_401(
    client: Client, session: AuthSession
) -> None:
    other = User.objects.create_user(google_sub="sub-other", email="otro@example.com")
    foreign = issue_access_token(user_id=other.pk, session_id=session.pk)
    assert_401(get(client, f"Bearer {foreign}"), IdentityErrorCode.SESSION_REVOKED)
    AuthSession.objects.filter(pk=session.pk).delete()
    assert_401(get(client, f"Bearer {token_of(session)}"), IdentityErrorCode.SESSION_REVOKED)


def test_RN_IDA_20_one_query_no_cache(client: Client, session: AuthSession) -> None:
    authorization = f"Bearer {token_of(session)}"
    before = AuthSession.objects.values().get(pk=session.pk)
    with (
        CaptureQueriesContext(connection) as queries,
        mock.patch.object(LocMemCache, "get", autospec=True) as read,
        mock.patch.object(LocMemCache, "set", autospec=True) as put,
    ):
        assert get(client, authorization).status_code == 200
    (query,) = queries.captured_queries
    sql = query["sql"]
    assert sql.startswith("SELECT")
    assert 'FROM "auth_sessions" INNER JOIN "users"' in sql
    assert (read.call_count, put.call_count) == (0, 0)
    assert AuthSession.objects.values().get(pk=session.pk) == before  # no write either


# --- What the JWT must be (RN-IDA-08) ------------------------------------------------------------


def test_AC_IDA_10_expired_via_api(client: Client, session: AuthSession) -> None:
    expired = token_of(session, issued_ago=EXPIRED_ISSUED_AGO)
    assert_401(get(client, f"Bearer {expired}"), IdentityErrorCode.TOKEN_EXPIRED, expired)
    assert get(client, f"Bearer {token_of(session, issued_ago=14 * 60)}").status_code == 200


def test_AC_IDA_11_bad_signature_via_api(client: Client, session: AuthSession) -> None:
    head, payload, signature = token_of(session).split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    mine = claims(sub=str(session.user_id), sid=str(session.pk))
    for token in (
        f"{head}.{payload}.{flipped}",
        forge(mine, key=other_key()),
        forge(mine, key=rsa_key(), alg="RS256"),
        by_hand(header(alg="none"), lambda _: b""),
    ):
        assert_401(get(client, f"Bearer {token}"), IdentityErrorCode.TOKEN_INVALID, token)


def test_AC_IDA_12_google_token_is_401(client: Client, session: AuthSession) -> None:
    mine = {"sub": str(session.user_id), "sid": str(session.pk)}
    google = claims(iss="https://accounts.google.com", aud="client.apps.example", **mine)
    for token in (
        jwt.encode(google, rsa_key(), "RS256", headers={"kid": "google-kid"}),
        forge(claims(iss="https://accounts.google.com", **mine)),
        forge(claims(aud="other-api", **mine)),
    ):
        assert_401(get(client, f"Bearer {token}"), IdentityErrorCode.TOKEN_INVALID, token)


def test_AC_IDA_34_skew_via_api(client: Client, session: AuthSession) -> None:
    for accepted in (-30, ACCESS_TOKEN_LIFETIME.total_seconds() + 30):
        token = token_of(session, issued_ago=accepted)
        assert get(client, f"Bearer {token}").status_code == 200, accepted
    future = token_of(session, issued_ago=-120)
    assert_401(get(client, f"Bearer {future}"), IdentityErrorCode.TOKEN_INVALID, future)


@pytest.mark.parametrize("authorization", ["Bearer", "Bearer a b", "bearer   ", "Bearer é.é.é"])
def test_RN_IDA_08_malformed_bearer_is_token_invalid(client: Client, authorization: str) -> None:
    assert_401(get(client, authorization), IdentityErrorCode.TOKEN_INVALID)


def test_RN_IDA_08_a_bad_bearer_is_401_even_on_an_open_route(client: Client) -> None:
    assert_401(get(client, "Bearer not-a-token", OPEN), IdentityErrorCode.TOKEN_INVALID)


# --- Not a person's session (RN-IDA-19) ----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Api-Key erp-key-1234"},
        {"Authorization": "Basic dGVzdDp0ZXN0"},
        {"X-Api-Key": "erp-key-1234"},
    ],
    ids=["api-key-scheme", "basic", "api-key-header"],
)
def test_AC_IDA_22_api_key_is_not_a_session(client: Client, headers: dict[str, str]) -> None:
    assert_401(client.get(PROTECTED, headers=headers), IdentityErrorCode.UNAUTHENTICATED)


def test_AC_IDA_22_api_key_as_bearer_is_token_invalid(client: Client) -> None:
    assert_401(get(client, "Bearer erp-key-1234"), IdentityErrorCode.TOKEN_INVALID)


# --- One source for the lifetime and the codes (review of #79) -----------------------------------


def test_access_token_takes_lifetime_and_codes_from_the_domain() -> None:
    lifetime = ACCESS_TOKEN_LIFETIME.total_seconds()
    assert lifetime == access_token.ACCESS_TOKEN_TTL_SECONDS
    assert access_token.AccessTokenExpiredError.code is IdentityErrorCode.TOKEN_EXPIRED
    assert access_token.AccessTokenInvalidError.code is IdentityErrorCode.TOKEN_INVALID
