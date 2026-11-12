"""AC-IDA-36 at the code exchange, and the authorization URL (RN-IDA-01, RN-IDA-02, RNF-IDA-03).

No network: the token endpoint is ``FakeGoogle.transport``. What is checked is how the gateway
maps each answer of Google (or its silence) to ``google_unavailable`` or ``google_auth_failed``,
that it never retries, and that no secret reaches the error nor the logs.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.secrets_format import (
    code_challenge_s256,
    generate_code_verifier,
    generate_nonce,
    generate_state,
)
from apps.identity.oidc.google_gateway import (
    GOOGLE_AUTHORIZATION_ENDPOINT,
    TOKEN_ENDPOINT_TIMEOUT,
    GoogleAuthFailedError,
    GoogleGateway,
    GoogleUnavailableError,
)
from tests.fakes.google import FakeGoogle, config

CODE = "4/0Ab-fake-authorization-code"
VERIFIER = generate_code_verifier()


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def gateway(google: FakeGoogle) -> GoogleGateway:
    return GoogleGateway(config(), transport=google.transport)


def exchange(gateway: GoogleGateway) -> str:
    return gateway.exchange_code(code=CODE, code_verifier=VERIFIER)


def test_RF_IDA_01_authorization_url_carries_state_nonce_and_s256_challenge() -> None:
    state, nonce = generate_state(), generate_nonce()
    url = GoogleGateway(config()).build_authorization_url(
        state=state, nonce=nonce, code_verifier=VERIFIER
    )
    parts = urlsplit(url)
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == GOOGLE_AUTHORIZATION_ENDPOINT
    assert query == {
        "client_id": config().client_id,
        "redirect_uri": config().redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge_s256(VERIFIER),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    assert VERIFIER not in url
    assert config().client_secret not in url


def test_RF_IDA_02_exchange_posts_the_code_with_pkce_and_returns_the_id_token(
    google: FakeGoogle, gateway: GoogleGateway
) -> None:
    google.next_id_token = google.id_token(nonce="any")
    assert exchange(gateway) == google.next_id_token
    [request] = google.token_requests
    form = {name: values[0] for name, values in parse_qs(request.content.decode()).items()}
    assert request.method == "POST"
    assert str(request.url) == config().token_endpoint
    assert form == {
        "grant_type": "authorization_code",
        "code": CODE,
        "code_verifier": VERIFIER,
        "client_id": config().client_id,
        "client_secret": config().client_secret,
        "redirect_uri": config().redirect_uri,
    }


def test_AC_IDA_36_exchange_uses_the_fixed_timeouts(
    google: FakeGoogle, gateway: GoogleGateway
) -> None:
    exchange(gateway)
    [request] = google.token_requests
    assert request.extensions["timeout"] == TOKEN_ENDPOINT_TIMEOUT.as_dict()
    assert TOKEN_ENDPOINT_TIMEOUT.connect == 3.0
    assert TOKEN_ENDPOINT_TIMEOUT.read == 5.0


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectTimeout("slow"),
        httpx.PoolTimeout("slow"),
    ],
    ids=["read", "connect", "pool"],
)
def test_AC_IDA_36_timeout_is_unavailable(
    google: FakeGoogle, gateway: GoogleGateway, failure: Exception
) -> None:
    google.fail_token(failure)
    with pytest.raises(GoogleUnavailableError) as raised:
        exchange(gateway)
    assert raised.value.code is IdentityErrorCode.GOOGLE_UNAVAILABLE


def test_AC_IDA_36_connection_error_is_unavailable(
    google: FakeGoogle, gateway: GoogleGateway
) -> None:
    google.fail_token(httpx.ConnectError("refused"))
    with pytest.raises(GoogleUnavailableError):
        exchange(gateway)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_AC_IDA_36_5xx_is_unavailable(
    google: FakeGoogle, gateway: GoogleGateway, status: int
) -> None:
    google.fail_token(status)
    with pytest.raises(GoogleUnavailableError):
        exchange(gateway)


def test_AC_IDA_36_429_is_unavailable(google: FakeGoogle, gateway: GoogleGateway) -> None:
    google.fail_token(429)
    with pytest.raises(GoogleUnavailableError):
        exchange(gateway)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), 503, 429])
def test_AC_IDA_36_exchange_is_never_retried(
    google: FakeGoogle, gateway: GoogleGateway, failure: int | Exception
) -> None:
    """The code is single use: a second attempt could only fail or, worse, double-spend it."""
    google.fail_token(failure)
    with pytest.raises(GoogleUnavailableError):
        exchange(gateway)
    assert len(google.token_requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 302])
def test_AC_IDA_07_refused_exchange_is_auth_failed(
    google: FakeGoogle, gateway: GoogleGateway, status: int
) -> None:
    """400 ``invalid_grant`` (used, expired or foreign code) and any other refusal or redirect."""
    google.fail_token(status)
    with pytest.raises(GoogleAuthFailedError) as raised:
        exchange(gateway)
    assert raised.value.code is IdentityErrorCode.GOOGLE_AUTH_FAILED


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["id_token"]),
        httpx.Response(200, json={"access_token": "only"}),
        httpx.Response(200, json={"id_token": ""}),
        httpx.Response(200, json={"id_token": 42}),
    ],
    ids=["not-json", "list", "missing", "empty", "not-a-string"],
)
def test_AC_IDA_07_answer_without_an_id_token_is_auth_failed(response: httpx.Response) -> None:
    gateway = GoogleGateway(config(), transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(GoogleAuthFailedError):
        exchange(gateway)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), 503, 400])
def test_RNF_IDA_03_exchange_failure_leaks_no_secret(
    google: FakeGoogle,
    gateway: GoogleGateway,
    failure: int | Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    google.fail_token(failure)
    caplog.set_level(logging.DEBUG)
    with pytest.raises((GoogleUnavailableError, GoogleAuthFailedError)) as raised:
        exchange(gateway)
    error = raised.value
    surfaces = [str(error), repr(error), caplog.text, repr(config())]
    for secret in (CODE, VERIFIER, config().client_secret):
        assert all(secret not in text for text in surfaces)
    assert error.__cause__ is None
    assert error.__suppress_context__ or error.__context__ is None
