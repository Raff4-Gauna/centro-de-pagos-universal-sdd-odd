"""``/api/auth/sessions/*``, "Seguridad" (RF-IDA-07, RN-IDA-24; AC-IDA-25, 26 and 33 API).

Each session is opened with ``open_session`` and its access JWT issued as a login would; the
requests go through the real route with that Bearer, so the authentication of every request is the
real one too (``HubJWTAuthentication``).
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
import yaml
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from structlog.testing import capture_logs

from apps.common.api.pagination import MAX_PAGE_SIZE, PAGE_SIZE, HubPageNumberPagination
from apps.identity.domain.audit_events import AuditActorType, IdentityAuditAction
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.models import AuthSession, RevokeReason, SessionStatus, User
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import issue_access_token
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.identity.fakes import Ports, install_ports

pytestmark = pytest.mark.django_db

SESSIONS = "/api/auth/sessions/"
REVOKE_OTHERS = "/api/auth/sessions/revoke-others/"
CHALLENGE = 'Bearer realm="hub"'
FIELDS = {"id", "browser", "os", "created_at", "last_used_at", "is_current"}


def revoke_url(session_id: object) -> str:
    return f"/api/auth/sessions/{session_id}/revoke/"


def make_user(sub: str, email: str) -> User:
    return User.objects.create_user(google_sub=sub, email=email)


class Device:
    """One login of a person: its session, refresh token and a Bearer of that session."""

    def __init__(
        self, user: User, *, browser: str = "", os: str = "", ago: timedelta = timedelta(0)
    ) -> None:
        now = timezone.now() - ago
        self.opened: OpenedSession = open_session(
            user, now=now, client_browser=browser, client_os=os
        )
        self.id = self.opened.session.pk
        token = issue_access_token(user_id=user.pk, session_id=self.id)
        self.headers = {"Authorization": f"Bearer {token}"}

    def status(self) -> str:
        return AuthSession.objects.get(pk=self.id).status


@pytest.fixture
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


@pytest.fixture
def ana() -> User:
    return make_user("sub-ana", "ana@example.com")


@pytest.fixture
def beto() -> User:
    return make_user("sub-beto", "beto@example.com")


def assert_401(response: Any, code: IdentityErrorCode) -> None:
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == CHALLENGE
    assert json.loads(response.content)["code"] == code.value


def problem_without_request_id(response: Any) -> dict[str, Any]:
    assert response.status_code == 404
    assert response["Content-Type"] == "application/problem+json"
    problem: dict[str, Any] = json.loads(response.content)
    problem.pop("request_id")
    return problem


def revocations(ports: Ports) -> list[Any]:
    return [
        event for event in ports.audit.events if event.action == IdentityAuditAction.SESSION_REVOKED
    ]


def test_AC_IDA_25_foreign_session_is_404(client: Client, ana: User, beto: User) -> None:
    mine = Device(ana)
    theirs = Device(beto)

    foreign = client.post(revoke_url(theirs.id), headers=mine.headers)
    unknown = client.post(revoke_url(uuid4()), headers=mine.headers)

    # Foreign and unknown answer alike: nothing tells A that B's session exists.
    assert problem_without_request_id(foreign) == problem_without_request_id(unknown)
    assert problem_without_request_id(foreign)["code"] == "not_found"
    assert theirs.status() == SessionStatus.ACTIVE
    listed = client.get(SESSIONS, headers=mine.headers).json()["results"]
    assert [row["id"] for row in listed] == [str(mine.id)]


def test_AC_IDA_25_ended_session_is_404(client: Client, ana: User) -> None:
    current = Device(ana)
    other = Device(ana)
    assert client.post(revoke_url(other.id), headers=current.headers).status_code == 204

    again = client.post(revoke_url(other.id), headers=current.headers)

    assert problem_without_request_id(again)["code"] == "not_found"


def test_AC_IDA_25_malformed_id_is_404(client: Client, ana: User) -> None:
    response = client.post(revoke_url("not-a-uuid"), headers=Device(ana).headers)
    assert response.status_code == 404


def test_AC_IDA_26_revoked_from_security_next_request(
    client: Client, ana: User, ports: Ports
) -> None:
    laptop = Device(ana)
    phone = Device(ana)
    # The phone's JWT works until the laptop ends that session.
    assert client.get(SESSIONS, headers=phone.headers).status_code == 200

    response = client.post(revoke_url(phone.id), headers=laptop.headers)

    assert response.status_code == 204
    assert response["Cache-Control"] == "no-store"
    assert_401(client.get(SESSIONS, headers=phone.headers), IdentityErrorCode.SESSION_REVOKED)
    assert client.get(SESSIONS, headers=laptop.headers).status_code == 200
    session = AuthSession.objects.get(pk=phone.id)
    assert session.status == SessionStatus.REVOKED
    assert session.revoke_reason == RevokeReason.USER_REVOKED
    [event] = revocations(ports)
    assert event.reason == "user_revoked"
    assert event.actor_type == AuditActorType.USER
    assert event.actor_id == ana.pk
    assert event.organization_id is None
    assert event.metadata == {"sid": str(phone.id)}


def test_AC_IDA_26_revoking_the_current_session_ends_it(client: Client, ana: User) -> None:
    current = Device(ana)

    assert client.post(revoke_url(current.id), headers=current.headers).status_code == 204

    assert_401(client.get(SESSIONS, headers=current.headers), IdentityErrorCode.SESSION_REVOKED)


def test_AC_IDA_33_revoke_others_keeps_current(
    client: Client, ana: User, beto: User, ports: Ports
) -> None:
    current, second, third = Device(ana), Device(ana), Device(ana)
    beto_session = Device(beto)

    response = client.post(REVOKE_OTHERS, headers=current.headers)

    assert response.status_code == 204
    active = AuthSession.objects.filter(user=ana, status=SessionStatus.ACTIVE)
    assert list(active.values_list("pk", flat=True)) == [current.id]
    for ended in (second, third):
        session = AuthSession.objects.get(pk=ended.id)
        assert session.revoke_reason == RevokeReason.REVOKED_OTHERS
        assert_401(client.get(SESSIONS, headers=ended.headers), IdentityErrorCode.SESSION_REVOKED)
    assert beto_session.status() == SessionStatus.ACTIVE
    events = revocations(ports)
    assert {event.metadata["sid"] for event in events} == {str(second.id), str(third.id)}
    assert {event.reason for event in events} == {"revoked_others"}
    assert {event.actor_id for event in events} == {ana.pk}


def test_AC_IDA_33_revoke_others_alone_is_a_noop(client: Client, ana: User, ports: Ports) -> None:
    current = Device(ana)

    assert client.post(REVOKE_OTHERS, headers=current.headers).status_code == 204

    assert current.status() == SessionStatus.ACTIVE
    assert revocations(ports) == []


def test_AC_IDA_33_list_has_no_ip(client: Client, ana: User, beto: User) -> None:
    older = Device(ana, browser="Firefox", os="Linux", ago=timedelta(hours=2))
    current = Device(ana, browser="Chrome", os="Windows", ago=timedelta(hours=1))
    unknown = Device(ana)
    Device(beto, browser="Safari", os="iOS")
    ended = Device(ana)
    client.post(revoke_url(ended.id), headers=current.headers)

    response = client.get(SESSIONS, headers=current.headers)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    page = response.json()
    assert (page["count"], page["next"], page["previous"]) == (3, None, None)
    rows = page["results"]
    # Last used first; only the live sessions of the person; browser, OS and dates only.
    assert [row["id"] for row in rows] == [str(unknown.id), str(current.id), str(older.id)]
    for row in rows:
        assert set(row) == FIELDS
    by_id = {row["id"]: row for row in rows}
    assert by_id[str(current.id)] | {"created_at": None, "last_used_at": None} == {
        "id": str(current.id),
        "browser": "Chrome",
        "os": "Windows",
        "created_at": None,
        "last_used_at": None,
        "is_current": True,
    }
    assert (by_id[str(unknown.id)]["browser"], by_id[str(unknown.id)]["os"]) == (None, None)
    assert [row["is_current"] for row in rows] == [False, True, False]
    assert "127.0.0.1" not in response.content.decode()


def test_AC_IDA_33_list_skips_sessions_past_a_deadline(client: Client, ana: User) -> None:
    current = Device(ana)
    stale = Device(ana)
    AuthSession.objects.filter(pk=stale.id).update(idle_expires_at=timezone.now())

    rows = client.get(SESSIONS, headers=current.headers).json()["results"]

    assert [row["id"] for row in rows] == [str(current.id)]


def test_RF_IDA_07_list_is_paginated_with_relative_links(client: Client, ana: User) -> None:
    current = Device(ana)
    for _ in range(PAGE_SIZE):
        Device(ana)

    first = client.get(SESSIONS, headers=current.headers).json()
    second = client.get(first["next"], headers=current.headers).json()
    small = client.get(f"{SESSIONS}?page_size=2", headers=current.headers).json()

    assert first["count"] == PAGE_SIZE + 1
    assert len(first["results"]) == PAGE_SIZE
    # Relative: the browser reaches Django through the BFF, never by Django's own host.
    assert first["next"] == f"{SESSIONS}?page=2"
    assert first["previous"] is None
    assert len(second["results"]) == 1
    assert second["previous"] == SESSIONS
    assert len(small["results"]) == 2
    assert small["next"] == f"{SESSIONS}?page=2&page_size=2"
    ids = [row["id"] for row in first["results"] + second["results"]]
    assert len(set(ids)) == PAGE_SIZE + 1


def test_RF_IDA_07_page_size_is_capped() -> None:
    request = Request(APIRequestFactory().get(SESSIONS, {"page_size": "10000"}))
    assert HubPageNumberPagination().get_page_size(request) == MAX_PAGE_SIZE == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", SESSIONS), ("post", REVOKE_OTHERS), ("post", revoke_url(uuid4()))],
)
def test_sessions_routes_refuse_anonymous(client: Client, method: str, path: str) -> None:
    response = getattr(client, method)(path)
    assert_401(response, IdentityErrorCode.UNAUTHENTICATED)


def test_revocations_log_ids_and_never_tokens(client: Client, ana: User) -> None:
    current, other = Device(ana), Device(ana)
    with capture_logs() as logs:
        client.post(revoke_url(other.id), headers=current.headers)
        client.post(REVOKE_OTHERS, headers=current.headers)

    [revoked] = [log for log in logs if log["event"] == "auth.session_revoked"]
    assert revoked["sid"] == str(other.id)
    assert revoked["reason"] == "user_revoked"
    [others] = [log for log in logs if log["event"] == "auth.other_sessions_revoked"]
    assert others["revoked"] == 0
    logged = json.dumps(logs, default=str)
    for secret in (
        current.opened.refresh_token,
        other.opened.refresh_token,
        current.headers["Authorization"].split()[1],
    ):
        assert secret not in logged


def test_contract_publishes_the_sessions_routes() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    paths = contract["paths"]
    listing = paths[SESSIONS]["get"]
    assert listing["security"] == [{"HubBearer": []}]
    assert {"200", "401"} <= set(listing["responses"])
    assert {"204", "401", "404"} <= set(
        paths["/api/auth/sessions/{session_id}/revoke/"]["post"]["responses"]
    )
    assert {"204", "401"} <= set(paths[REVOKE_OTHERS]["post"]["responses"])
    schemas = contract["components"]["schemas"]
    assert set(schemas["Session"]["properties"]) == FIELDS
    page = listing["responses"]["200"]["content"]["application/json"]["schema"]
    assert page == {"$ref": "#/components/schemas/PaginatedSessionList"}
    assert set(schemas["PaginatedSessionList"]["properties"]) == {
        "count",
        "next",
        "previous",
        "results",
    }
    assert {parameter["name"] for parameter in listing["parameters"]} == {"page", "page_size"}
    assert contract["info"]["version"] == "0.7.0"
