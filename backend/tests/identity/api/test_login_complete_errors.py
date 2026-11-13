"""``login/complete``: Google's side, the flag, the body, the logs and the contract (RF-IDA-02).

Steps 3 and 4 of design.md §4.2 (what Google answers), what reaches the logs (AC-IDA-23), how the
audit event of a rejection survives the rollback with the real ``LogAuditPort`` (design.md §7.4)
and the published operation.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import yaml
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.models import AuthSession, LoginAttempt, User
from apps.identity.services import login_complete
from apps.identity.services.user_provisioning import UserProvisioningError
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.identity.api.login_flow import (
    BINDING,
    CLIENT_VALUE,
    CODE,
    COMPLETE,
    CREDENTIAL,
    Flow,
    make_user,
)

pytestmark = pytest.mark.django_db


def code_of(response: Any) -> str:
    assert response["Content-Type"] == "application/problem+json"
    code: str = response.json()["code"]
    return code


def audited_reasons(flow: Flow) -> list[str | None]:
    return [event.reason for event in flow.ports.audit.events]


def test_RF_IDA_02_cancelled_at_google_is_not_a_rejection(flow: Flow) -> None:
    state, _ = flow.begin()

    response = flow.finish(state, code=None, error="access_denied")

    assert (response.status_code, code_of(response)) == (400, "login_cancelled")
    assert flow.google.token_requests == []
    assert flow.ports.audit.events == []  # not a rejection of the Hub (design.md §4.2)
    assert not LoginAttempt.objects.exists()  # consumed all the same


@pytest.mark.parametrize(
    "redirect",
    [{"error": "server_error"}, {"code": None}, {"code": ""}, {"error": "x", "code": "c"}],
)
def test_RF_IDA_02_other_error_or_no_code_is_auth_failed(
    flow: Flow, redirect: dict[str, Any]
) -> None:
    state, _ = flow.begin()

    response = flow.finish(state, **redirect)

    assert (response.status_code, code_of(response)) == (400, "google_auth_failed")
    assert flow.google.token_requests == []
    assert audited_reasons(flow) == ["google_auth_failed"]


def test_AC_IDA_08_cancel_with_a_bad_state_is_auth_failed(flow: Flow) -> None:
    # The attempt is step 2, the redirect's error step 3: a forged cancel proves nothing.
    response = flow.finish("not-an-attempt", code=None, error="access_denied")
    assert code_of(response) == "google_auth_failed"


@pytest.mark.parametrize("failure", [503, 429, httpx.ConnectTimeout("slow")])
def test_RF_IDA_02_google_unavailable_is_503_and_not_audited(
    flow: Flow, failure: int | Exception
) -> None:
    make_user()
    state, _ = flow.begin()
    flow.google.fail_token(failure)

    response = flow.finish(state)

    assert (response.status_code, code_of(response)) == (503, "google_unavailable")
    assert "detail" not in response.json()
    assert flow.ports.audit.events == []  # logs and metrics only (Q-111)
    assert not AuthSession.objects.exists()


def test_RF_IDA_02_refused_code_is_auth_failed_and_audited(flow: Flow) -> None:
    make_user()
    state, _ = flow.begin()
    flow.google.fail_token(400)  # invalid_grant: used, expired or not ours

    response = flow.finish(state)

    assert (response.status_code, code_of(response)) == (400, "google_auth_failed")
    assert audited_reasons(flow) == ["google_auth_failed"]
    assert not AuthSession.objects.exists()


def test_RF_IDA_02_exchange_sends_the_attempts_verifier(flow: Flow) -> None:
    make_user()
    state, nonce = flow.begin()
    verifier = LoginAttempt.objects.get().code_verifier
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)

    assert flow.finish(state).status_code == 200

    [request] = flow.google.token_requests
    form = dict(httpx.QueryParams(request.content.decode()))
    assert (form["code"], form["code_verifier"]) == (CODE, verifier)


def test_RNF_IDA_06_flag_off_is_503_and_consumes_nothing(
    flow: Flow, settings: SettingsWrapper
) -> None:
    state, _ = flow.begin()
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": False}

    for body in ({}, {"login_binding": "malformed"}):
        response = flow.finish(state, **body)
        assert (response.status_code, code_of(response)) == (503, "login_disabled")
    assert LoginAttempt.objects.exists()
    assert flow.gateway_calls == []


def test_complete_without_credential_is_a_missing_route(flow: Flow, client: Client) -> None:
    state, _ = flow.begin()
    body = {"state": state, "login_binding": BINDING, "code": CODE}
    for headers in ({}, {"X-Hub-Bff-Credential": "wrong"}):
        response = client.post(COMPLETE, body, content_type="application/json", headers=headers)
        assert response.status_code == 404
        assert "Allow" not in response
    assert LoginAttempt.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {"login_binding": "short"},
        {"login_binding": None},
        {"state": None},
        {"state": "s" * 513},
        {"code": "c" * 2049},
    ],
)
def test_malformed_body_is_400_without_echo_and_consumes_nothing(
    flow: Flow, body: dict[str, Any]
) -> None:
    state, _ = flow.begin()

    response = flow.finish(state, **body)

    assert (response.status_code, code_of(response)) == (400, "validation_error")
    assert state not in response.content.decode()
    assert LoginAttempt.objects.exists()
    assert flow.ports.audit.events == []


def test_RF_IDA_02_provisioning_error_is_500_without_detail(
    flow: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> User:
        raise UserProvisioningError("a new user could not be inserted")

    monkeypatch.setattr(login_complete, "provision_user", broken)
    flow.client.raise_request_exception = False

    response = flow.login()

    assert (response.status_code, code_of(response)) == (500, "internal_error")
    assert "detail" not in response.json()
    assert flow.ports.audit.events == []  # no rule explains it: not a login rejection
    assert not AuthSession.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_AC_IDA_03_rejection_event_survives_the_rollback(
    flow: Flow, settings: SettingsWrapper, capsys: pytest.CaptureFixture[str]
) -> None:
    # The real LogAuditPort writes on commit: an event recorded inside the rolled-back
    # transaction would vanish. Accepting fails after the user is inserted (RN-IDA-06).
    settings.IDENTITY_AUDIT_PORT = "apps.identity.ports.stubs.LogAuditPort"
    invitation = flow.ports.invitations.invite("ana@example.com", now=timezone.now())
    invitation.fails_on_accept = True
    capsys.readouterr()

    response = flow.login()

    assert code_of(response) == "not_invited"
    assert not User.objects.exists()
    assert not LoginAttempt.objects.exists()  # its own commit: the rollback did not return it
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    audit = [line for line in lines if line.get("component") == "audit"]
    assert [(line["action"], line["reason"]) for line in audit] == [
        ("identity.login_rejected", "not_invited")
    ]


def test_AC_IDA_23_callback_logs_no_secret(flow: Flow, capsys: pytest.CaptureFixture[str]) -> None:
    make_user()
    state, nonce = flow.begin()
    verifier = LoginAttempt.objects.get().code_verifier
    id_token = flow.google.id_token(nonce=nonce)
    flow.google.next_id_token = id_token
    capsys.readouterr()

    body = flow.finish(state).json()
    flow.finish(state)  # and a rejection

    captured = capsys.readouterr()
    logged = captured.out + captured.err
    assert "auth.login_succeeded" in logged
    assert "auth.login_rejected" in logged
    secrets = (state, nonce, verifier, BINDING, CODE, id_token, CREDENTIAL, CLIENT_VALUE)
    for value in (*secrets, body["access_token"], body["refresh_token"]):
        assert value not in logged


def test_contract_publishes_complete_as_bff_internal() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    operation = contract["paths"][COMPLETE]["post"]
    assert operation["tags"] == ["bff-internal"]
    assert operation["security"] == [{"BffCredential": []}]
    assert {"200", "400", "403", "409", "429", "503"} <= set(operation["responses"])
    schemas = contract["components"]["schemas"]
    request = schemas["LoginCompleteRequest"]
    assert set(request["required"]) == {"state", "login_binding"}
    assert set(request["properties"]) == {"state", "login_binding", "code", "error"}
    response = schemas["LoginCompleteResponse"]
    assert set(response["properties"]) == {
        "access_token",
        "access_expires_in",
        "refresh_token",
        "session_id",
        "session_expires_in",
        "return_path",
    }
    assert contract["info"]["version"] == "0.5.0"
