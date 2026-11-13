"""The fake OIDC provider of dev and test (Q-122, RN-IDA-01, RNF-IDA-06, ADR-0004 §14).

``/dev-oidc/*`` exists only in ``config.urls_dev`` and only with ``IDENTITY_OIDC_PROVIDER=fake``;
prod's URLconf never has it. A login against it runs the real gateway and the real verifier: the
token endpoint is reached through ``httpx.MockTransport`` handing the request to Django's test
client, and the JWKS through the verifier's own ``PyJWKClient``, fed by the JWKS view.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from django.test import Client
from django.urls import Resolver404, resolve
from jwt import PyJWKClient
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.secrets_format import (
    generate_code_verifier,
    generate_nonce,
    generate_state,
    hash_secret,
)
from apps.identity.oidc.google_gateway import GoogleAuthFailedError, GoogleGateway
from apps.identity.oidc.id_token import IdTokenVerifier
from apps.identity.oidc.provider import google_oidc_config
from tests.api.test_Q056_dev_routes_absent_in_prod import _PROD_PROBE
from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.conftest import RunDjango

AUTHORIZE = "/dev-oidc/authorize"
TOKEN = "/dev-oidc/token"  # noqa: S105 - a path
JWKS = "/dev-oidc/jwks"
DEV_OIDC_ROUTES = (AUTHORIZE, TOKEN, JWKS)
REDIRECT_URI = "http://localhost:3000/api/auth/google/callback"
CLIENT_VALUE = "dev-oidc-client-value"
OTHER_CLIENT_VALUE = "another-client-value"
DEV = "config.settings.dev"
VALID_DEV_ENV = {
    "DJANGO_SECRET_KEY": "dev-only-not-a-secret-" * 3,
    "DATABASE_URL": "postgres://hub:hub@localhost:5432/hub",
    "REDIS_URL": "redis://localhost:6379/0",
}


@pytest.fixture
def fake_provider(settings: SettingsWrapper) -> SettingsWrapper:
    settings.IDENTITY_OIDC_PROVIDER = "fake"
    settings.IDENTITY_GOOGLE_CLIENT_ID = "hub-dev-oidc-client"
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = CLIENT_VALUE
    settings.IDENTITY_GOOGLE_REDIRECT_URI = REDIRECT_URI
    return settings


def _via_django(client: Client) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        content_type = request.headers["content-type"]
        answer = client.post(request.url.path, data=request.content, content_type=content_type)
        headers = {"content-type": answer["Content-Type"]}
        return httpx.Response(answer.status_code, content=answer.content, headers=headers)

    return httpx.MockTransport(handle)


def _jwks_from(client: Client, monkeypatch: pytest.MonkeyPatch) -> PyJWKClient:
    jwks = PyJWKClient(google_oidc_config().jwks_uri)
    monkeypatch.setattr(jwks, "fetch_data", lambda: client.get(JWKS).json())
    return jwks


def _authorize(client: Client, gateway: GoogleGateway, **person: str) -> tuple[str, str, str]:
    """Code, state and nonce of a login through the fake's authorization endpoint."""
    state, nonce, verifier = generate_state(), generate_nonce(), generate_code_verifier()
    url = gateway.build_authorization_url(state=state, nonce=nonce, code_verifier=verifier)
    response = client.get(f"{url}&{urlencode(person)}")
    assert response.status_code == 302
    location = urlsplit(response["Location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == REDIRECT_URI
    query = parse_qs(location.query)
    assert query["state"] == [state]
    return query["code"][0], verifier, nonce


@pytest.mark.urls("config.urls")
@pytest.mark.parametrize("path", DEV_OIDC_ROUTES)
def test_RN_IDA_01_dev_oidc_routes_absent_in_prod(client: Client, path: str) -> None:
    with pytest.raises(Resolver404):
        resolve(path)
    assert client.get(path).status_code == 404


def test_RN_IDA_01_prod_process_has_no_dev_oidc_route(run_django: RunDjango) -> None:
    result = run_django(
        "-c",
        _PROD_PROBE.format(routes=DEV_OIDC_ROUTES),
        settings_module=PROD,
        values=VALID_PROD_ENV,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "config.urls []"


@pytest.mark.parametrize(("oidc_provider", "mounted"), [("google", []), ("fake", DEV_OIDC_ROUTES)])
def test_RNF_IDA_06_dev_mounts_dev_oidc_only_with_the_fake_provider(
    run_django: RunDjango, oidc_provider: str, mounted: tuple[str, ...]
) -> None:
    values = {**VALID_DEV_ENV, "IDENTITY_OIDC_PROVIDER": oidc_provider}
    result = run_django(
        "-c", _PROD_PROBE.format(routes=DEV_OIDC_ROUTES), settings_module=DEV, values=values
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f"config.urls_dev {list(mounted)}"


@pytest.mark.urls("apps.identity.dev_oidc.urls")
@pytest.mark.parametrize("path", DEV_OIDC_ROUTES)
def test_RNF_IDA_06_dev_oidc_answers_404_with_google(client: Client, path: str) -> None:
    # Mounted by mistake next to Google: it still answers nobody.
    assert client.get(path).status_code == 404
    assert client.post(path).status_code == 404


@pytest.mark.urls("apps.identity.dev_oidc.urls")
@pytest.mark.usefixtures("fake_provider")
def test_RNF_IDA_06_fake_login_passes_the_real_gateway_and_verifier(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = google_oidc_config()
    assert config.authorization_endpoint == f"http://testserver{AUTHORIZE}"
    gateway = GoogleGateway(config, transport=_via_django(client))
    form = client.get(gateway.build_authorization_url(state="s", nonce="n", code_verifier="v" * 43))
    assert form.status_code == 200
    assert b'name="email"' in form.content
    code, verifier, nonce = _authorize(client, gateway, email="Ana@Example.com", name="Ana")
    id_token = gateway.exchange_code(code=code, code_verifier=verifier)
    verifier_ = IdTokenVerifier(config, jwks_client=_jwks_from(client, monkeypatch))
    identity = verifier_.verify(id_token, expected_nonce_hash=hash_secret(nonce))
    assert (identity.email, identity.name, identity.email_verified) == (
        "Ana@Example.com",
        "Ana",
        True,
    )
    assert identity.sub.startswith("dev-")
    # The sub is stable per email, so the same person logs in again as the same user.
    code, verifier, nonce = _authorize(client, gateway, email="ana@example.com")
    again = verifier_.verify(
        gateway.exchange_code(code=code, code_verifier=verifier),
        expected_nonce_hash=hash_secret(nonce),
    )
    assert again.sub == identity.sub


@pytest.mark.urls("apps.identity.dev_oidc.urls")
@pytest.mark.usefixtures("fake_provider")
def test_RNF_IDA_06_fake_code_is_single_use_and_bound_to_its_verifier(client: Client) -> None:
    gateway = GoogleGateway(google_oidc_config(), transport=_via_django(client))
    code, verifier, _ = _authorize(client, gateway, email="ana@example.com", email_verified="false")
    with pytest.raises(GoogleAuthFailedError):
        gateway.exchange_code(code=code, code_verifier=generate_code_verifier())
    assert gateway.exchange_code(code=code, code_verifier=verifier)
    with pytest.raises(GoogleAuthFailedError):
        gateway.exchange_code(code=code, code_verifier=verifier)
    with pytest.raises(GoogleAuthFailedError):
        gateway.exchange_code(code="not-a-code", code_verifier=verifier)


@pytest.mark.urls("apps.identity.dev_oidc.urls")
def test_RNF_IDA_06_fake_refuses_other_clients(
    client: Client, fake_provider: SettingsWrapper
) -> None:
    config = google_oidc_config()
    good = GoogleGateway(config, transport=_via_django(client))
    code, verifier, _ = _authorize(client, good, email="ana@example.com")
    fake_provider.IDENTITY_GOOGLE_CLIENT_SECRET = OTHER_CLIENT_VALUE
    with pytest.raises(GoogleAuthFailedError):
        good.exchange_code(code=code, code_verifier=verifier)
    # An unregistered redirect_uri is never redirected to.
    url = good.build_authorization_url(state="s", nonce="n", code_verifier="v" * 43)
    hostile = url.replace("localhost%3A3000", "evil.example")
    response = client.get(f"{hostile}&email=ana%40example.com")
    assert response.status_code == 400
    assert "Location" not in response


@pytest.mark.urls("apps.identity.dev_oidc.urls")
@pytest.mark.usefixtures("fake_provider")
def test_RNF_IDA_06_fake_cancel_is_access_denied(client: Client) -> None:
    gateway = GoogleGateway(google_oidc_config())
    url = gateway.build_authorization_url(state="the-state", nonce="n", code_verifier="v" * 43)
    response = client.get(f"{url}&cancel=1")
    assert response.status_code == 302
    query = parse_qs(urlsplit(response["Location"]).query)
    assert query == {"error": ["access_denied"], "state": ["the-state"]}


@pytest.mark.urls("apps.identity.dev_oidc.urls")
@pytest.mark.usefixtures("fake_provider")
def test_RNF_IDA_06_fake_refuses_malformed_requests(client: Client) -> None:
    gateway = GoogleGateway(google_oidc_config())
    url = gateway.build_authorization_url(state="the-state", nonce="n", code_verifier="v" * 43)
    plain = url.replace("code_challenge_method=S256", "code_challenge_method=plain")
    query = parse_qs(urlsplit(client.get(f"{plain}&email=a%40b.c")["Location"]).query)
    assert query == {"error": ["invalid_request"], "state": ["the-state"]}
    form = {"client_id": "hub-dev-oidc-client", "client_secret": CLIENT_VALUE}
    refresh = client.post(TOKEN, {**form, "grant_type": "refresh_token"})
    assert (refresh.status_code, refresh.json()) == (400, {"error": "unsupported_grant_type"})
    code, _, _ = _authorize(client, GoogleGateway(google_oidc_config()), email="a@b.c")
    exchange = {**form, "grant_type": "authorization_code", "code": code}
    answer = client.post(TOKEN, {**exchange, "redirect_uri": REDIRECT_URI, "code_verifier": "ñ"})
    assert (answer.status_code, answer.json()) == (400, {"error": "invalid_grant"})
    assert answer["Cache-Control"] == "no-store"
