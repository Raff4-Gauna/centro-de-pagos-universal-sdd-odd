"""``POST /api/auth/bff/refresh/`` (RF-IDA-04; AC-IDA-09, 14, 16, 22, 23 at the API; design §6.1).

The real route of the public URLconf on the wall clock, so the access tokens it answers verify. The
decisions behind each answer are ``tests/identity/test_refresh.py``'s; here, what the BFF sees: the
status, the code, the body and the throttles. Throttle history lives in LocMemCache, cleared around
each test.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import yaml
from django.core.cache import cache
from django.test import Client
from django.urls import resolve
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.secrets_format import generate_refresh_token
from apps.identity.domain.session_policy import IDLE_LIFETIME
from apps.identity.models import AuthSession, SessionStatus, User
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import issue_access_token, verify_access_token
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT

pytestmark = pytest.mark.django_db

REFRESH = "/api/auth/bff/refresh/"
CREDENTIAL = "bff-value-of-the-refresh-test"
BFF = {"X-Hub-Bff-Credential": CREDENTIAL, "X-Hub-Client-IP": "203.0.113.1"}


@pytest.fixture(autouse=True)
def bff(settings: SettingsWrapper) -> Iterator[None]:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-refresh-api", email="ana@example.com")


@pytest.fixture
def opened(user: User) -> OpenedSession:
    return open_session(user, now=timezone.now())


def post(client: Client, body: object, headers: dict[str, str] | None = None) -> Any:
    payload = json.dumps(body)
    return client.post(REFRESH, payload, content_type="application/json", headers=headers or BFF)


def assert_refused(response: Any, code: str, *secrets: str) -> None:
    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"
    assert json.loads(response.content)["code"] == code
    for secret in secrets:
        assert secret not in response.content.decode()


def test_AC_IDA_14_refresh_answers_a_new_pair(client: Client, opened: OpenedSession) -> None:
    response = post(client, {"refresh_token": opened.refresh_token})

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == {"access_token", "access_expires_in", "refresh_token", "session_expires_in"}
    assert body["access_expires_in"] == 900
    assert body["refresh_token"] not in (None, opened.refresh_token)
    identity = verify_access_token(body["access_token"])
    assert (identity.user_id, identity.session_id) == (opened.session.user_id, opened.session.pk)
    assert body["session_expires_in"] == IDLE_LIFETIME.total_seconds()  # the idle deadline moved
    # The old one, presented right away, is the grace window: access only. The new one rotates.
    grace = post(client, {"refresh_token": opened.refresh_token})
    assert grace.status_code == 200
    assert grace.json()["refresh_token"] is None
    assert verify_access_token(grace.json()["access_token"]).session_id == opened.session.pk
    assert post(client, {"refresh_token": body["refresh_token"]}).json()["refresh_token"]


def test_AC_IDA_16_expired_session_refresh_is_session_revoked(
    client: Client, opened: OpenedSession
) -> None:
    past = timezone.now() - timedelta(seconds=1)
    AuthSession.objects.filter(pk=opened.session.pk).update(idle_expires_at=past)

    assert_refused(post(client, {"refresh_token": opened.refresh_token}), "session_revoked")
    assert AuthSession.objects.get(pk=opened.session.pk).status == SessionStatus.EXPIRED


def test_AC_IDA_09_inactive_user_refresh_via_api(
    client: Client, opened: OpenedSession, user: User
) -> None:
    User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=timezone.now())
    response = post(client, {"refresh_token": opened.refresh_token})
    assert_refused(response, "session_revoked", opened.refresh_token)
    assert "access_token" not in response.content.decode()


@pytest.mark.parametrize(
    "authorization", ["Bearer erp-key-1234", "Api-Key erp-key-1234", "Token erp-key-1234"]
)
def test_AC_IDA_22_api_key_on_refresh(client: Client, authorization: str) -> None:
    headers = {**BFF, "Authorization": authorization}
    # Neither in the header (not read) nor in the body (not a refresh token).
    assert_refused(post(client, {}, headers), "token_invalid")
    response = post(client, {"refresh_token": "erp-key-1234"}, headers)
    assert_refused(response, "token_invalid", "erp-key-1234")


def test_AC_IDA_22_a_persons_jwt_is_no_refresh(client: Client, opened: OpenedSession) -> None:
    access = issue_access_token(user_id=opened.session.user_id, session_id=opened.session.pk)
    headers = {**BFF, "Authorization": f"Bearer {access}"}
    assert_refused(post(client, {}, headers), "token_invalid")
    assert_refused(post(client, {"refresh_token": access}), "token_invalid", access)


@pytest.mark.parametrize(
    "body", [[], None, 7, "rt1", {"refresh_token": None}, {"refresh_token": 7}, {"other": "x"}]
)
def test_body_without_a_refresh_token_is_401_not_400(client: Client, body: object) -> None:
    assert_refused(post(client, body), "token_invalid")


def test_unknown_refresh_token_is_token_invalid(client: Client, opened: OpenedSession) -> None:
    forged = generate_refresh_token(opened.session.pk)
    assert_refused(post(client, {"refresh_token": forged}), "token_invalid", forged)


def test_refresh_without_credential_is_a_missing_route(
    client: Client, opened: OpenedSession
) -> None:
    body = json.dumps({"refresh_token": opened.refresh_token})
    response = client.post(REFRESH, body, content_type="application/json")
    assert response.status_code == 404
    assert "Allow" not in response


def test_refresh_route_opts_out_of_atomic_requests() -> None:
    # A request-wide transaction would roll back the expiry or revocation of a refused refresh.
    match = resolve(REFRESH)
    assert "default" in getattr(match.func, "_non_atomic_requests", set())


def test_refresh_works_with_the_login_flag_off(
    client: Client, opened: OpenedSession, settings: SettingsWrapper
) -> None:
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": False}  # ADR-0004 §14
    assert post(client, {"refresh_token": opened.refresh_token}).status_code == 200


def test_AC_IDA_23_refresh_logs_and_errors_carry_no_token(
    client: Client, opened: OpenedSession
) -> None:
    with capture_logs() as logs:
        body = post(client, {"refresh_token": opened.refresh_token}).json()
        refused = post(client, {"refresh_token": f"{opened.refresh_token}x"})
    text = str(logs) + refused.content.decode()
    for secret in (opened.refresh_token, body["refresh_token"], body["access_token"]):
        assert secret not in text


# --- Throttle per client IP (planner's decision, T-IDA-14) ---------------------------------------


def made_up(client: Client, ip: str) -> int:
    """A refresh with a well-formed token of a session that does not exist."""
    headers = {**BFF, "X-Hub-Client-IP": ip}
    response = post(client, {"refresh_token": generate_refresh_token(uuid4())}, headers)
    status: int = response.status_code
    return status


def test_made_up_session_ids_hit_the_ip_ceiling(client: Client) -> None:
    statuses = [made_up(client, "203.0.113.9") for _ in range(60)]
    assert statuses == [401] * 60  # each a new sid: the session quota alone never stops them

    response = post(
        client,
        {"refresh_token": "rt1.garbage"},
        {**BFF, "X-Hub-Client-IP": "203.0.113.9"},
    )

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert 0 < int(response["Retry-After"]) <= 60
    assert made_up(client, "203.0.113.10") == 401  # another client keeps its quota


def test_ip_ceiling_follows_the_setting(client: Client, settings: SettingsWrapper) -> None:
    settings.IDENTITY_REFRESH_IP_RATE = "3/min"
    assert [made_up(client, "203.0.113.20") for _ in range(4)] == [401, 401, 401, 429]


def test_default_ip_ceiling_is_generous(settings: SettingsWrapper) -> None:
    assert settings.IDENTITY_REFRESH_IP_RATE == "60/min"


# --- The contract --------------------------------------------------------------------------------


def test_contract_publishes_refresh_as_bff_internal() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    operation = contract["paths"][REFRESH]["post"]
    assert operation["tags"] == ["bff-internal"]
    assert operation["security"] == [{"BffCredential": []}]
    assert {"200", "401", "429"} <= set(operation["responses"])
    schemas = contract["components"]["schemas"]
    assert schemas["RefreshRequest"]["required"] == ["refresh_token"]
    answer = schemas["RefreshResponse"]
    assert set(answer["properties"]) == {
        "access_token",
        "access_expires_in",
        "refresh_token",
        "session_expires_in",
    }
    assert answer["properties"]["refresh_token"]["nullable"] is True
    assert contract["info"]["version"] == "0.7.0"
