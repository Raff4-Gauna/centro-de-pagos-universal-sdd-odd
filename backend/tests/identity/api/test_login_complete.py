"""``POST /api/auth/bff/login/complete/`` (RF-IDA-02, RN-IDA-17; AC-IDA-01, 03, 06, 08, 09, 20, 24).

The table of design.md §4.2 through the real route, with Google faked at the network
(``login_flow.py``). The errors of Google's side, the flag, the logs and the contract are in
``test_login_complete_errors.py`` (C-14).
"""

from __future__ import annotations

import json
from datetime import UTC, timedelta
from typing import Any

import pytest
from django.db.models import F
from django.test import Client
from django.utils import timezone

from apps.identity.domain.audit_events import AuditActorType, IdentityAuditAction
from apps.identity.domain.secrets_format import hash_secret
from apps.identity.models import AuthSession, LoginAttempt, RefreshToken, SessionStatus, User
from apps.identity.ports.audit import AuditEvent
from apps.identity.tokens.access_token import verify_access_token
from tests.fakes import google
from tests.identity.api.login_flow import (
    EMAIL,
    OTHER_BINDING,
    Flow,
    make_user,
)

pytestmark = pytest.mark.django_db

NEW_SUB = "200000000000000000002"
TOKEN_FIELDS = ("access_token", "refresh_token")


def problem_of(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response["Content-Type"] == "application/problem+json"
    problem: dict[str, Any] = response.json()
    assert problem["code"] == code
    for name in TOKEN_FIELDS:
        assert name not in problem
    return problem


def rejections(flow: Flow) -> list[AuditEvent]:
    return [
        event
        for event in flow.ports.audit.events
        if event.action == IdentityAuditAction.LOGIN_REJECTED
    ]


def assert_rejected_once(flow: Flow, reason: str, *, actor_id: object = None) -> AuditEvent:
    [event] = rejections(flow)
    assert event.reason == reason
    assert event.result == "failure"
    assert event.actor_id == actor_id
    expected = AuditActorType.ANONYMOUS if actor_id is None else AuditActorType.USER
    assert event.actor_type == expected
    assert event.organization_id is None
    assert event.metadata == {}
    return event


def test_AC_IDA_01_active_user_gets_session(flow: Flow) -> None:
    ana = make_user()

    response = flow.login()

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "access_token",
        "access_expires_in",
        "refresh_token",
        "session_id",
        "session_expires_in",
        "return_path",
    }
    session = AuthSession.objects.get()
    assert session.status == SessionStatus.ACTIVE
    assert session.user_id == ana.pk
    assert body["session_id"] == str(session.pk)
    assert body["access_expires_in"] == 900
    assert body["session_expires_in"] == 7 * 24 * 3600
    assert body["return_path"] == "/cobros"
    identity = verify_access_token(body["access_token"])
    assert (identity.user_id, identity.session_id) == (ana.pk, session.pk)
    assert RefreshToken.objects.get().token_hash == hash_secret(body["refresh_token"])
    assert not LoginAttempt.objects.exists()  # consumed
    [event] = flow.ports.audit.events
    assert event.action == IdentityAuditAction.LOGIN_SUCCEEDED
    assert (event.actor_type, event.actor_id, event.result) == ("user", ana.pk, "success")
    assert flow.ports.invitations.calls == []  # case (a), Q-121


def test_AC_IDA_01_invited_login_end_to_end_reaches_me(flow: Flow, client: Client) -> None:
    # The whole login by API: start, Google (fake), callback, and the Bearer it gives works.
    flow.ports.invitations.invite(EMAIL, now=timezone.now())

    body = flow.login().json()
    me = client.get("/api/me/", headers={"Authorization": f"Bearer {body['access_token']}"})

    assert me.status_code == 200
    assert me.json()["email"] == EMAIL
    user = User.objects.get()
    assert user.google_sub == google.SUB
    assert flow.ports.invitations.invitations[0].accepted_by == user.pk
    actions = [event.action for event in flow.ports.audit.events]
    assert actions == [
        IdentityAuditAction.USER_CREATED_BY_INVITATION,
        IdentityAuditAction.LOGIN_SUCCEEDED,
    ]


def test_AC_IDA_03_rejected_is_audited(flow: Flow) -> None:
    response = flow.login()

    problem_of(response, 403, "not_invited")
    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert_rejected_once(flow, "not_invited")
    # The rollback took the user away; the rejection is written after it, so it stays.
    assert [event.action for event in flow.ports.audit.events] == ["identity.login_rejected"]


@pytest.mark.parametrize("unverified", [False, "false", 1, None])
def test_AC_IDA_06_unverified_email(flow: Flow, unverified: object) -> None:
    flow.ports.invitations.invite(EMAIL, now=timezone.now())

    problem_of(flow.login(email_verified=unverified), 403, "email_not_verified")

    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert_rejected_once(flow, "email_not_verified")


def test_AC_IDA_08_bad_state_never_calls_google(flow: Flow) -> None:
    state, _ = flow.begin()
    stale, _ = flow.begin()
    LoginAttempt.objects.filter(state_hash=hash_secret(stale)).update(
        created_at=F("created_at") - timedelta(minutes=11),
        expires_at=F("expires_at") - timedelta(minutes=11),
    )

    responses = [
        flow.finish("state-that-was-never-issued"),
        flow.finish(""),
        flow.finish(state, binding=OTHER_BINDING),  # another browser's binding
        flow.finish(stale),  # past its 10 minutes
    ]

    for response in responses:
        problem = problem_of(response, 400, "google_auth_failed")
        assert problem["title"] == "Ingreso con Google fallido"
    assert flow.gateway_calls == []
    assert flow.google.token_requests == []
    assert not AuthSession.objects.exists()
    assert [event.reason for event in rejections(flow)] == ["google_auth_failed"] * 4
    # A wrong binding does not burn the attempt of the browser that owns it.
    assert LoginAttempt.objects.filter(state_hash=hash_secret(state)).exists()


def test_AC_IDA_08_repeated_callback(flow: Flow) -> None:
    make_user()
    state, nonce = flow.begin()
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)

    first = flow.finish(state)
    again = flow.finish(state)

    assert first.status_code == 200
    problem_of(again, 400, "google_auth_failed")
    assert AuthSession.objects.count() == 1
    assert len(flow.google.token_requests) == 1  # the repeat never reached Google


def test_AC_IDA_08_nonce_of_another_attempt_is_refused(flow: Flow) -> None:
    make_user()
    state, _ = flow.begin()
    _, other_nonce = flow.begin()
    flow.google.next_id_token = flow.google.id_token(nonce=other_nonce)

    problem_of(flow.finish(state), 400, "google_auth_failed")

    assert not AuthSession.objects.exists()
    assert_rejected_once(flow, "google_auth_failed")


def test_AC_IDA_09_inactive_gets_no_tokens(flow: Flow) -> None:
    ana = make_user(active=False)

    response = flow.login()

    problem = problem_of(response, 403, "user_inactive")
    assert problem["title"] == "Usuario desactivado"
    assert not AuthSession.objects.exists()
    assert not RefreshToken.objects.exists()
    # The person is known: the event names the user, by id (design.md §7.4).
    assert_rejected_once(flow, "user_inactive", actor_id=ana.pk)


def test_AC_IDA_20_eleventh_callback_is_429(flow: Flow) -> None:
    statuses = [flow.finish(f"bad-state-{n}").status_code for n in range(10)]
    assert statuses == [400] * 10
    make_user()
    state, nonce = flow.begin()  # start has a quota of its own
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)

    response = flow.finish(state)

    problem_of(response, 429, "rate_limited")
    assert 0 < int(response["Retry-After"]) <= 60
    assert flow.google.token_requests == []
    assert LoginAttempt.objects.filter(state_hash=hash_secret(state)).exists()
    assert len(rejections(flow)) == 10  # the 429 is no audit event (Q-111)
    assert flow.finish(state, ip="203.0.113.2").status_code == 200  # another client's quota


def test_AC_IDA_24_login_events_have_null_org(flow: Flow) -> None:
    make_user()
    flow.login()
    flow.finish("bad-state")

    events = flow.ports.audit.events
    assert [event.action for event in events] == [
        IdentityAuditAction.LOGIN_SUCCEEDED,
        IdentityAuditAction.LOGIN_REJECTED,
    ]
    for event in events:
        assert event.organization_id is None
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.utcoffset() == timedelta(0)
        assert event.occurred_at.astimezone(UTC) == event.occurred_at


@pytest.mark.parametrize("case", ["identity_conflict", "not_invited", "user_inactive"])
def test_Q_125_rejection_has_no_email_nor_sub(
    flow: Flow, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    if case == "identity_conflict":
        make_user(sub="300000000000000000003")  # Ana's address, someone else's account
    elif case == "user_inactive":
        make_user(active=False)
    capsys.readouterr()

    response = flow.login(sub=NEW_SUB if case != "user_inactive" else google.SUB)

    status = 409 if case == "identity_conflict" else 403
    problem_of(response, status, case)
    [event] = rejections(flow)
    text = repr(event) + json.dumps(response.json()) + capsys.readouterr().out
    for personal in (EMAIL, NEW_SUB, google.SUB):
        assert personal not in text
    assert event.reason == case


def test_RNF_IDA_04_conflict_alert_and_one_rejection_line(
    flow: Flow, capsys: pytest.CaptureFixture[str]
) -> None:
    owner = make_user(sub="300000000000000000003")
    capsys.readouterr()

    flow.login(sub=NEW_SUB)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    [alert] = [line for line in lines if line.get("alert") is True]
    assert (alert["message"], alert["outcome"], alert["reason"]) == (
        "auth.identity_conflict",
        "rejected",
        "identity_conflict",
    )
    assert alert["existing_user_id"] == str(owner.pk)
    [rejected] = [line for line in lines if line.get("message") == "auth.login_rejected"]
    assert (rejected["outcome"], rejected["reason"]) == ("rejected", "identity_conflict")
