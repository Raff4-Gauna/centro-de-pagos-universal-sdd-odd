"""BFF credential, client IP and throttles (AC-IDA-20, AC-IDA-37, RN-IDA-15, design.md §7.6).

The views that use them arrive with T-IDA-10/13/14, so this module is its own urlconf: three
stand-ins with the permission and the throttle each real view will declare. History lives in
LocMemCache, cleared around each test; the Redis behaviour is ``apps.common``'s (AC-PLT-30).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.urls import URLPattern, URLResolver, path
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from structlog.testing import capture_logs

from apps.common import feature_flags
from apps.identity.api.bff_auth import BffAPIView, IsBffCaller
from apps.identity.api.client_ip import INVALID_CLIENT_IP_EVENT, client_ip_for
from apps.identity.api.throttles import (
    LoginCompleteIpThrottle,
    LoginStartIpThrottle,
    RefreshSessionThrottle,
)
from apps.identity.domain.secrets_format import generate_refresh_token
from config import urls as public_urls
from config.settings.env import PlatformEnv, load_bff_credentials, load_env

pytestmark = pytest.mark.urls(__name__)

handler404 = public_urls.handler404
handler500 = public_urls.handler500

START = "/api/test/bff/start"
COMPLETE = "/api/test/bff/complete"
REFRESH = "/api/test/bff/refresh"
CURRENT = "current-bff-value"
PREVIOUS = "previous-bff-value"
BFF = {"X-Hub-Bff-Credential": CURRENT}
SESSION_A = "3f2b8c1e-6d4a-4f0e-9b1a-1c2d3e4f5a6b"
SESSION_B = "7a9e0d2c-1b3f-4c5d-8e6f-0a1b2c3d4e5f"
SECRET_PART = "s" * 43  # the shape of the secret part of a refresh token

reached_views: list[str] = []


class _StandIn(BffAPIView):
    """What a view of ``auth/bff/*`` declares; it records that the view body ran."""

    def post(self, request: Request) -> Response:
        reached_views.append(request.path)
        return Response({"client_ip": client_ip_for(request)})


class _Start(_StandIn):
    throttle_classes = (LoginStartIpThrottle,)


class _Complete(_StandIn):
    throttle_classes = (LoginCompleteIpThrottle,)


class _Refresh(_StandIn):
    throttle_classes = (RefreshSessionThrottle,)


urlpatterns: list[URLPattern | URLResolver] = [
    path("api/test/bff/start", _Start.as_view()),
    path("api/test/bff/complete", _Complete.as_view()),
    path("api/test/bff/refresh", _Refresh.as_view()),
]


@pytest.fixture(autouse=True)
def clean_state(settings: SettingsWrapper) -> Iterator[None]:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CURRENT), SecretStr(PREVIOUS))
    reached_views.clear()
    cache.clear()
    yield
    cache.clear()


def bff_post(client: Client, url: str, ip: str, **body: object) -> Any:
    headers = {**BFF, "X-Hub-Client-IP": ip}
    return client.post(url, body, content_type="application/json", headers=headers)


def rest_request(headers: dict[str, str], remote_addr: str = "10.0.0.5") -> Request:
    return Request(APIRequestFactory().post("/", headers=headers, REMOTE_ADDR=remote_addr))


def as_missing_route(response: Any) -> tuple[int, dict[str, str], bytes]:
    """Status, headers and body bytes, without what changes on every request (its id)."""
    request_id = response["X-Request-ID"]
    headers = {name: value for name, value in response.items() if name != "X-Request-ID"}
    return response.status_code, headers, response.content.replace(request_id.encode(), b"")


def problem(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(response.content)
    body.pop("request_id", None)
    body.pop("instance", None)
    return body


# --- Credential ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Hub-Bff-Credential": ""},
        {"X-Hub-Bff-Credential": "wrong"},
        {"X-Hub-Bff-Credential": CURRENT + "x"},
        {"X-Hub-Bff-Credential": CURRENT[:-1]},
        # Non-ASCII text: hmac.compare_digest raises TypeError if it is handed str.
        {"X-Hub-Bff-Credential": "contraseña"},
    ],
)
def test_bff_endpoint_without_credential_is_404(client: Client, headers: dict[str, str]) -> None:
    response = client.post(START, {}, content_type="application/json", headers=headers)
    missing = client.post("/api/test/bff/nothing-here", {}, content_type="application/json")
    assert response.status_code == 404
    assert reached_views == []
    # Byte for byte the answer of a route that does not exist: no Allow, same rendering.
    assert "Allow" not in response
    assert as_missing_route(response) == as_missing_route(missing)


@pytest.mark.parametrize("method", ["get", "put", "delete", "options"])
def test_bff_endpoint_is_404_for_any_method_without_credential(client: Client, method: str) -> None:
    response = getattr(client, method)(START)
    missing = getattr(client, method)("/api/test/bff/nothing-here")
    assert as_missing_route(response) == as_missing_route(missing)


def test_is_bff_caller_alone_still_refuses_with_404() -> None:
    with pytest.raises(NotFound):
        IsBffCaller().has_permission(rest_request({}), APIView())


@pytest.mark.parametrize("credential", [CURRENT, PREVIOUS])
def test_bff_endpoint_accepts_current_and_previous_credential(
    client: Client, credential: str
) -> None:
    headers = {"X-Hub-Bff-Credential": credential}
    response = client.post(START, {}, content_type="application/json", headers=headers)
    assert response.status_code == 200


def test_bff_endpoint_without_configured_credentials_refuses_everyone(
    client: Client, settings: SettingsWrapper
) -> None:
    settings.IDENTITY_BFF_CREDENTIALS = ()
    assert bff_post(client, START, "203.0.113.1").status_code == 404


def test_rejected_caller_consumes_no_quota(client: Client) -> None:
    headers = {"X-Hub-Client-IP": "203.0.113.1"}
    for _ in range(11):
        response = client.post(START, {}, content_type="application/json", headers=headers)
        assert response.status_code == 404
    assert bff_post(client, START, "203.0.113.1").status_code == 200


def test_RN_IDA_16_credentials_are_masked_and_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDENTITY_BFF_CREDENTIALS", f"{CURRENT}, {PREVIOUS}")
    assert [item.get_secret_value() for item in load_bff_credentials()] == [CURRENT, PREVIOUS]
    env = load_env(PlatformEnv)
    for text in (repr(env), env.model_dump_json(), repr(load_bff_credentials())):
        assert CURRENT not in text
        assert PREVIOUS not in text


def test_bff_credentials_empty_means_none_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDENTITY_BFF_CREDENTIALS", "")
    assert load_bff_credentials() == ()


@pytest.mark.parametrize("value", ["a-value,,b-value", "a-value,b-value,c-value"])
def test_RN_IDA_16_bad_credentials_stop_the_start_without_showing_them(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("IDENTITY_BFF_CREDENTIALS", value)
    with pytest.raises(ImproperlyConfigured) as info:
        load_bff_credentials()
    assert "IDENTITY_BFF_CREDENTIALS" in str(info.value)
    assert "a-value" not in str(info.value)


# --- Client IP -------------------------------------------------------------------------------


def test_client_ip_header_ignored_without_credential() -> None:
    forged = rest_request({"X-Hub-Client-IP": "203.0.113.7"})
    assert client_ip_for(forged) == "10.0.0.5"
    wrong = rest_request({"X-Hub-Client-IP": "203.0.113.7", "X-Hub-Bff-Credential": "wrong"})
    assert client_ip_for(wrong) == "10.0.0.5"


def test_client_ip_header_used_with_previous_credential_too() -> None:
    request = rest_request({"X-Hub-Client-IP": "203.0.113.7", "X-Hub-Bff-Credential": PREVIOUS})
    assert client_ip_for(request) == "203.0.113.7"


def test_client_ip_never_reads_x_forwarded_for() -> None:
    assert client_ip_for(rest_request({"X-Forwarded-For": "203.0.113.7"})) == "10.0.0.5"
    request = rest_request({**BFF, "X-Forwarded-For": "203.0.113.7"})
    assert client_ip_for(request) == "10.0.0.5"


@pytest.mark.parametrize(
    "value", ["not-an-ip", "203.0.113.7, 10.0.0.1", "203.0.113.7/24", "999.1.1.1"]
)
def test_malformed_client_ip_falls_back_to_remote_addr_without_logging_it(value: str) -> None:
    with capture_logs() as logs:
        ip = client_ip_for(rest_request({**BFF, "X-Hub-Client-IP": value}))
    assert ip == "10.0.0.5"
    assert [entry["event"] for entry in logs] == [INVALID_CLIENT_IP_EVENT]
    assert value not in str(logs)


@pytest.mark.parametrize(
    ("reported", "canonical"),
    [
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("2001:DB8:0:0::1", "2001:db8::1"),
    ],
)
def test_one_client_ip_has_one_spelling(reported: str, canonical: str) -> None:
    assert client_ip_for(rest_request({**BFF, "X-Hub-Client-IP": reported})) == canonical


# --- Throttles -------------------------------------------------------------------------------


@pytest.mark.parametrize("url", [START, COMPLETE])
def test_AC_IDA_20_eleventh_from_one_ip_is_429_with_retry_after(client: Client, url: str) -> None:
    statuses = [bff_post(client, url, "203.0.113.1").status_code for _ in range(10)]
    assert statuses == [200] * 10

    response = bff_post(client, url, "203.0.113.1")

    assert response.status_code == 429
    assert problem(response)["code"] == "rate_limited"  # design.md §6.1, allowlist of §6.3
    assert 0 < int(response["Retry-After"]) <= 60
    assert len(reached_views) == 10  # the throttle stops it before the view, so before Google


def test_AC_IDA_20_key_is_per_ip_and_scope(client: Client) -> None:
    for _ in range(11):
        bff_post(client, START, "203.0.113.1")
    assert bff_post(client, START, "203.0.113.1").status_code == 429
    assert bff_post(client, START, "203.0.113.2").status_code == 200
    assert bff_post(client, COMPLETE, "203.0.113.1").status_code == 200

    digest = hashlib.sha256(b"203.0.113.1").hexdigest()[:16]
    request = rest_request({**BFF, "X-Hub-Client-IP": "203.0.113.1"})
    view = APIView()
    start_key = LoginStartIpThrottle().get_cache_key(request, view)
    complete_key = LoginCompleteIpThrottle().get_cache_key(request, view)
    assert start_key == f"throttle_login_start_ip_{digest}"
    assert complete_key == f"throttle_login_complete_ip_{digest}"


def test_AC_IDA_20_thirty_first_refresh_of_a_session_is_429(client: Client) -> None:
    token = generate_refresh_token(UUID(SESSION_A))
    statuses = [
        bff_post(client, REFRESH, "203.0.113.1", refresh_token=token).status_code for _ in range(30)
    ]
    assert statuses == [200] * 30

    response = bff_post(client, REFRESH, "203.0.113.2", refresh_token=token)

    assert response.status_code == 429  # by session: another IP does not help
    assert problem(response)["code"] == "rate_limited"
    assert int(response["Retry-After"]) > 0
    other = generate_refresh_token(UUID(SESSION_B))
    assert bff_post(client, REFRESH, "203.0.113.1", refresh_token=other).status_code == 200


def test_AC_IDA_20_refresh_key_is_the_session_and_never_the_secret() -> None:
    token = generate_refresh_token(UUID(SESSION_A))
    body = json.dumps({"refresh_token": token})
    view = _Refresh()
    request = view.initialize_request(
        APIRequestFactory().post("/", body, content_type="application/json")
    )

    key = RefreshSessionThrottle().get_cache_key(request, view)

    assert key == f"throttle_refresh_session_{SESSION_A}"
    assert token.rsplit(".", 1)[1] not in key


@pytest.mark.parametrize(
    "body",
    [
        "[]",
        "null",
        "{}",
        '{"refresh_token": 7}',
        '{"refresh_token": "garbage"}',
        f'{{"refresh_token": "rt2.{SESSION_A}.x"}}',
        '{"refresh_token": "rt1.not-a-session.x"}',
        f'{{"refresh_token": "rt1.{SESSION_A}"}}',
        # A canonical UUID in place of its base64url: not the format, whatever the old parser took.
        f'{{"refresh_token": "rt1.{SESSION_A}.{SECRET_PART}"}}',
    ],
)
def test_malformed_refresh_body_reaches_the_view(client: Client, body: str) -> None:
    # No session to count against: the real view answers token_invalid without touching the BD.
    for _ in range(31):
        response = client.post(REFRESH, body, content_type="application/json", headers=BFF)
        assert response.status_code == 200


def test_AC_IDA_37_ten_client_ips_share_no_quota(client: Client) -> None:
    responses = [bff_post(client, START, f"203.0.113.{host}") for host in range(1, 11)]
    assert [response.status_code for response in responses] == [200] * 10
    # One of them spends its quota; the others keep theirs, because it is not the BFF's.
    for _ in range(9):
        assert bff_post(client, START, "203.0.113.1").status_code == 200
    assert bff_post(client, START, "203.0.113.1").status_code == 429
    assert bff_post(client, START, "203.0.113.2").status_code == 200


def test_one_client_ip_spelled_twice_shares_its_quota(client: Client) -> None:
    for _ in range(10):
        bff_post(client, START, "203.0.113.1")
    assert bff_post(client, START, "::ffff:203.0.113.1").status_code == 429


def test_forged_client_ip_does_not_multiply_the_quota() -> None:
    # Without the credential the key is REMOTE_ADDR's, whatever the header says.
    view = APIView()
    keys = {
        LoginStartIpThrottle().get_cache_key(
            rest_request({"X-Hub-Client-IP": f"203.0.113.{host}"}), view
        )
        for host in range(1, 4)
    }
    assert len(keys) == 1


class _FailingCache:
    def get(self, *args: object, **kwargs: object) -> None:
        raise RedisConnectionError


def test_redis_failure_lets_the_login_through(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D-06: SPEC-01 does not choose fail-closed, so the platform's fail-open stands.
    monkeypatch.setattr(LoginStartIpThrottle, "cache", _FailingCache())
    assert bff_post(client, START, "203.0.113.1").status_code == 200


def test_login_flag_is_registered_and_off_by_default() -> None:
    assert "IDENTITY_GOOGLE_LOGIN" in feature_flags.REGISTRY
    assert feature_flags.is_enabled("IDENTITY_GOOGLE_LOGIN") is False
