"""``POST /api/auth/bff/logout/`` (RF-IDA-05, RN-IDA-14; AC-IDA-17 backend, AC-IDA-35; design §6.1).

The real route of the public URLconf. What decides which session ends is
``tests/identity/test_logout.py``'s; here, what the BFF sees: ``204`` with an empty body whatever it
sends, and the session ended when it sent a token of it. The cookies are the BFF's (``T-IDA-25``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import yaml
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.audit_events import IdentityAuditAction
from apps.identity.models import AuthSession, RevokeReason, SessionStatus, User
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import issue_access_token
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.identity.fakes import Ports, install_ports

pytestmark = pytest.mark.django_db

LOGOUT = "/api/auth/bff/logout/"
REFRESH = "/api/auth/bff/refresh/"
CREDENTIAL = "bff-value-of-the-logout-test"
BFF = {"X-Hub-Bff-Credential": CREDENTIAL, "X-Hub-Client-IP": "203.0.113.1"}


@pytest.fixture(autouse=True)
def bff(settings: SettingsWrapper) -> Iterator[None]:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-logout-api", email="ana@example.com")


@pytest.fixture
def opened(user: User) -> OpenedSession:
    return open_session(user, now=timezone.now())


def post(client: Client, body: object, headers: dict[str, str] | None = None) -> Any:
    payload = json.dumps(body)
    return client.post(LOGOUT, payload, content_type="application/json", headers=headers or BFF)


def status_of(opened: OpenedSession) -> str:
    status: str = AuthSession.objects.get(pk=opened.session.pk).status
    return status


def assert_no_content(response: Any) -> None:
    assert response.status_code == 204
    assert response.content == b""


def test_AC_IDA_17_logout_is_204_and_the_refresh_stops(
    client: Client, opened: OpenedSession, ports: Ports
) -> None:
    assert_no_content(post(client, {"refresh_token": opened.refresh_token}))

    assert status_of(opened) == SessionStatus.REVOKED
    refresh = client.post(
        REFRESH,
        json.dumps({"refresh_token": opened.refresh_token}),
        content_type="application/json",
        headers=BFF,
    )
    assert refresh.status_code == 401
    assert refresh.json()["code"] == "session_revoked"
    assert [event.action for event in ports.audit.events] == [IdentityAuditAction.LOGOUT]


def test_AC_IDA_17_second_logout_is_204_without_effects(
    client: Client, opened: OpenedSession, ports: Ports
) -> None:
    post(client, {"refresh_token": opened.refresh_token})
    assert_no_content(post(client, {"refresh_token": opened.refresh_token}))
    assert len(ports.audit.events) == 1


def test_AC_IDA_35_expired_jwt_logs_out_via_api(
    client: Client, opened: OpenedSession, ports: Ports
) -> None:
    an_hour_ago = timezone.now() - timedelta(hours=1)
    expired = issue_access_token(
        user_id=opened.session.user_id, session_id=opened.session.pk, now=an_hour_ago
    )

    assert_no_content(post(client, {"access_token": expired}))
    assert status_of(opened) == SessionStatus.REVOKED


def test_superseded_reason_via_api(client: Client, opened: OpenedSession, ports: Ports) -> None:
    post(client, {"refresh_token": opened.refresh_token, "reason": "superseded"})
    session = AuthSession.objects.get(pk=opened.session.pk)
    assert session.revoke_reason == RevokeReason.SUPERSEDED


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        None,
        7,
        "rt1",
        {"refresh_token": None, "access_token": None},
        {"refresh_token": 7},
        {"other": "x"},
    ],
)
def test_anonymous_logout_is_204_without_effects(
    client: Client, opened: OpenedSession, ports: Ports, body: object
) -> None:
    assert_no_content(post(client, body))
    assert status_of(opened) == SessionStatus.ACTIVE
    assert ports.audit.events == []


@pytest.mark.parametrize("reason", ["user_revoked", "refresh_reuse", "", 7, None])
def test_invalid_reason_still_logs_out(
    client: Client, opened: OpenedSession, ports: Ports, reason: object
) -> None:
    # Planner's decision (2026-11-13): the person asked to leave; a live session is the worse bug.
    with capture_logs() as logs:
        response = post(client, {"refresh_token": opened.refresh_token, "reason": reason})

    assert_no_content(response)
    session = AuthSession.objects.get(pk=opened.session.pk)
    assert (session.status, session.revoke_reason) == (SessionStatus.REVOKED, RevokeReason.LOGOUT)
    assert [event.action for event in ports.audit.events] == [IdentityAuditAction.LOGOUT]
    [warning] = [entry for entry in logs if entry["log_level"] == "warning"]
    assert (warning["event"], warning["result"]) == ("identity.logout", "invalid_reason")
    assert opened.refresh_token not in str(logs)
    assert set(warning) == {"event", "result", "log_level"}  # nothing of the body


def test_missing_reason_is_logout(client: Client, opened: OpenedSession, ports: Ports) -> None:
    with capture_logs() as logs:
        post(client, {"refresh_token": opened.refresh_token})
    session = AuthSession.objects.get(pk=opened.session.pk)
    assert session.revoke_reason == RevokeReason.LOGOUT
    assert all(entry["log_level"] != "warning" for entry in logs)


def test_a_body_that_is_not_json_is_refused_before_the_view(
    client: Client, opened: OpenedSession
) -> None:
    # DRF parses before the view: a 4XX, not the 204 of a JSON body (the BFF clears its cookies).
    malformed = client.post(LOGOUT, "{not json", content_type="application/json", headers=BFF)
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "parse_error"
    other_type = client.post(LOGOUT, "refresh_token=x", content_type="text/plain", headers=BFF)
    assert other_type.status_code == 415
    assert status_of(opened) == SessionStatus.ACTIVE


def test_authorization_header_is_not_read(client: Client, opened: OpenedSession) -> None:
    access = issue_access_token(user_id=opened.session.user_id, session_id=opened.session.pk)
    assert_no_content(post(client, {}, {**BFF, "Authorization": f"Bearer {access}"}))
    assert status_of(opened) == SessionStatus.ACTIVE  # only the body names the session


def test_logout_without_credential_is_a_missing_route(
    client: Client, opened: OpenedSession
) -> None:
    body = json.dumps({"refresh_token": opened.refresh_token})
    response = client.post(LOGOUT, body, content_type="application/json")
    assert response.status_code == 404
    assert "Allow" not in response
    assert status_of(opened) == SessionStatus.ACTIVE


def test_logout_is_never_throttled(client: Client, settings: SettingsWrapper) -> None:
    settings.API_THROTTLE_ANON_RATE = "2/min"  # the platform's default would apply otherwise
    assert {post(client, {}).status_code for _ in range(5)} == {204}


def test_logout_works_with_the_login_flag_off(
    client: Client, opened: OpenedSession, settings: SettingsWrapper
) -> None:
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": False}  # ADR-0004 §14
    post(client, {"refresh_token": opened.refresh_token})
    assert status_of(opened) == SessionStatus.REVOKED


def test_AC_IDA_23_logout_logs_carry_no_token(client: Client, opened: OpenedSession) -> None:
    access = issue_access_token(user_id=opened.session.user_id, session_id=opened.session.pk)
    with capture_logs() as logs:
        post(client, {"refresh_token": opened.refresh_token, "access_token": access})
    text = str(logs)
    assert opened.refresh_token not in text
    assert access not in text


# --- The contract --------------------------------------------------------------------------------


def test_contract_publishes_logout_as_bff_internal() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    operation = contract["paths"][LOGOUT]["post"]
    assert operation["tags"] == ["bff-internal"]
    assert operation["security"] == [{"BffCredential": []}]
    assert "204" in operation["responses"]
    assert "content" not in operation["responses"]["204"]
    request = contract["components"]["schemas"]["LogoutRequest"]
    assert set(request["properties"]) == {"refresh_token", "access_token", "reason"}
    assert "required" not in request
    reason = request["properties"]["reason"]["$ref"]
    assert reason == "#/components/schemas/LogoutReasonEnum"
    assert contract["components"]["schemas"]["LogoutReasonEnum"]["enum"] == ["logout", "superseded"]
    assert contract["info"]["version"] == "0.7.0"
