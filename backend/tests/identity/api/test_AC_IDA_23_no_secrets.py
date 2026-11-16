"""No secret in the logs nor in the errors of a whole session (AC-IDA-23, RN-IDA-16, RNF-IDA-03).

A login, a refresh, a logout and rejections of each, through the real ``auth/bff/*`` routes with
the real ``LogAuditPort`` (the audit channel is a log too, so it is captured with the rest), and a
login that fails with an unexpected error whose message quotes the ``state``. Everything the
process writes and every body it answers is searched for each secret of the session: ``state``,
``nonce``, PKCE verifier, binding, Google's code and ID token, the Hub's tokens, the cookie the
browser sent, the BFF credential, Google's client secret and the JWT signing key.

``transaction=True``: ``LogAuditPort`` writes on commit, which a test transaction never reaches.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.conf import settings as django_settings
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.models import LoginAttempt
from apps.identity.services import login_complete
from tests.identity.api.login_flow import (
    BINDING,
    CLIENT_VALUE,
    CODE,
    CREDENTIAL,
    IP,
    Flow,
    make_user,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

REFRESH = "/api/auth/bff/refresh/"
LOGOUT = "/api/auth/bff/logout/"
COOKIE_VALUE = "cookie-value-the-browser-sent"


def signing_key_lines() -> list[str]:
    """The base64 lines of the PEM: any of them in a log would be a piece of the key."""
    pem = django_settings.IDENTITY_JWT_SIGNING_KEY
    text = pem.decode() if isinstance(pem, bytes) else str(pem)
    return [line for line in text.splitlines() if line and not line.startswith("-----")]


def post(flow: Flow, path: str, body: dict[str, object]) -> Any:
    headers = {
        "X-Hub-Bff-Credential": CREDENTIAL,
        "X-Hub-Client-IP": IP,
        "Cookie": f"__Host-cpu_rt={COOKIE_VALUE}",
    }
    return flow.client.post(path, body, content_type="application/json", headers=headers)


def test_AC_IDA_23_no_secret_in_logs_or_errors(
    flow: Flow,
    settings: SettingsWrapper,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.IDENTITY_AUDIT_PORT = "apps.identity.ports.stubs.LogAuditPort"
    make_user()
    capsys.readouterr()
    secrets: list[str] = [BINDING, CODE, CREDENTIAL, CLIENT_VALUE, COOKIE_VALUE]
    bodies: list[str] = []

    # Login.
    state, nonce = flow.begin()
    secrets += [state, nonce, LoginAttempt.objects.get().code_verifier]
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)
    secrets.append(flow.google.next_id_token)
    login = flow.finish(state)
    assert login.status_code == 200
    first = login.json()
    secrets += [first["access_token"], first["refresh_token"]]
    # Login rejected: the same callback again (its attempt is gone).
    again = flow.finish(state)
    assert again.status_code == 400
    bodies.append(again.content.decode())

    # Refresh, and a refresh rejected (a made-up secret for that session).
    refreshed = post(flow, REFRESH, {"refresh_token": first["refresh_token"]})
    assert refreshed.status_code == 200
    second = refreshed.json()
    secrets += [second["access_token"], second["refresh_token"]]
    forged = first["refresh_token"].rsplit(".", 1)[0] + ".x" + "A" * 42
    secrets.append(forged)
    refused = post(flow, REFRESH, {"refresh_token": forged})
    assert refused.status_code == 401
    bodies.append(refused.content.decode())

    # Logout, and a second one that finds the session ended.
    for _ in range(2):
        tokens = {"refresh_token": second["refresh_token"], "access_token": second["access_token"]}
        assert post(flow, LOGOUT, tokens).status_code == 204

    # A login that fails with an error nobody expected, whose message quotes the state.
    state, nonce = flow.begin()
    secrets += [state, nonce]
    flow.google.next_id_token = flow.google.id_token(nonce=nonce)

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"broken while handling state={state} code={CODE}")

    monkeypatch.setattr(login_complete, "provision_user", broken)
    flow.client.raise_request_exception = False
    failed = flow.finish(state)
    assert failed.status_code == 500
    bodies.append(failed.content.decode())

    captured = capsys.readouterr()
    logged = captured.out + captured.err
    lines = [json.loads(line) for line in captured.out.splitlines()]
    # What was captured is the session: its audit and auth events and the failure's access log.
    assert {"auth.login_succeeded", "auth.refresh_rejected", "auth.logout"} <= {
        line.get("message") for line in lines
    }
    assert any(line.get("component") == "audit" for line in lines)
    # RNF-IDA-03: each auth event carries the request and its outcome; a refusal, its reason.
    auth = [line for line in lines if str(line.get("message", "")).startswith("auth.")]
    for line in auth:
        assert line["request_id"]
        assert line["outcome"]
        if line["outcome"] == "rejected":
            assert line["reason"]
    assert any(line.get("exception_type") == "RuntimeError" for line in lines)
    for secret in [*secrets, *signing_key_lines()]:
        assert secret not in logged
        for body in bodies:
            assert secret not in body
