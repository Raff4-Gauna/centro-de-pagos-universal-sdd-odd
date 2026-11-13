"""``POST /api/auth/bff/login/start/`` (RF-IDA-01; AC-IDA-19 server side, AC-IDA-20, AC-IDA-37).

The real route of the public URLconf, with the real gateway: starting a login only builds a URL, so
Google is not involved; ``gateway_calls`` counts how many times the gateway was even asked for.
The throttle history lives in LocMemCache, cleared around each test.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.utils import timezone
from django.views.debug import ExceptionReporter
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.secrets_format import code_challenge_s256, hash_secret
from apps.identity.models import LoginAttempt
from apps.identity.oidc.google_gateway import GOOGLE_AUTHORIZATION_ENDPOINT
from apps.identity.services import login_start
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.fakes import google

pytestmark = pytest.mark.django_db

START = "/api/auth/bff/login/start/"
CREDENTIAL = "bff-value-of-this-test"
BINDING = "b" * 43
CLIENT_VALUE = "a-client-value-nobody-should-read"
HOSTILE_PATHS = [
    "https://evil.example/cobros",  # absolute
    "javascript:alert(1)",  # scheme
    "//evil.example/cobros",  # //host
    "evil.example/cobros",  # another domain
    "/\\evil.example",
]

gateway_calls: list[None] = []


@pytest.fixture(autouse=True)
def login_enabled(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    config = google.config()
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": True}
    settings.IDENTITY_OIDC_PROVIDER = "google"
    settings.IDENTITY_GOOGLE_CLIENT_ID = config.client_id
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = CLIENT_VALUE
    settings.IDENTITY_GOOGLE_REDIRECT_URI = config.redirect_uri
    real = login_start.get_google_gateway

    def counted() -> Any:
        gateway_calls.append(None)
        return real()

    monkeypatch.setattr(login_start, "get_google_gateway", counted)
    gateway_calls.clear()
    cache.clear()
    yield
    cache.clear()


def start(client: Client, ip: str = "203.0.113.1", **body: object) -> Any:
    headers = {"X-Hub-Bff-Credential": CREDENTIAL, "X-Hub-Client-IP": ip}
    payload = {"login_binding": BINDING, **body}
    return client.post(START, payload, content_type="application/json", headers=headers)


def query_of(response: Any) -> dict[str, str]:
    url = urlsplit(response.json()["authorization_url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == GOOGLE_AUTHORIZATION_ENDPOINT
    return {name: values[0] for name, values in parse_qs(url.query).items()}


def test_RF_IDA_01_start_ties_state_nonce_and_pkce_to_one_attempt(client: Client) -> None:
    before = timezone.now()
    response = start(client, return_path="/cobros?estado=paid")

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert list(response.json()) == ["authorization_url"]
    query = query_of(response)
    attempt = LoginAttempt.objects.get()
    assert attempt.state_hash == hash_secret(query["state"])
    assert attempt.nonce_hash == hash_secret(query["nonce"])
    assert attempt.binding_hash == hash_secret(BINDING)
    assert query["code_challenge"] == code_challenge_s256(attempt.code_verifier)
    assert query["code_challenge_method"] == "S256"
    assert query["client_id"] == google.CLIENT_ID
    assert query["redirect_uri"] == google.config().redirect_uri
    assert query["scope"] == "openid email profile"
    assert query["response_type"] == "code"
    assert attempt.return_path == "/cobros?estado=paid"
    assert before <= attempt.created_at <= timezone.now()
    assert attempt.expires_at == attempt.created_at + timedelta(minutes=10)


def test_RF_IDA_01_only_hashes_are_stored_and_nothing_secret_is_answered(client: Client) -> None:
    response = start(client)

    query = query_of(response)
    attempt = LoginAttempt.objects.get()
    stored = [str(value) for value in LoginAttempt.objects.values().get().values()]
    for raw in (query["state"], query["nonce"], BINDING):
        assert raw not in stored
    answered = response.content.decode()
    for kept in (attempt.code_verifier, BINDING, CLIENT_VALUE, CREDENTIAL):
        assert kept not in answered
    assert len({query["state"], query["nonce"], attempt.code_verifier}) == 3


def test_RF_IDA_01_each_start_is_a_new_attempt_even_with_the_same_binding(client: Client) -> None:
    # Double click or two tabs: the BFF reuses its binding (design.md §6.3), never the state.
    first, second = query_of(start(client)), query_of(start(client))
    assert first["state"] != second["state"]
    assert first["nonce"] != second["nonce"]
    assert LoginAttempt.objects.filter(binding_hash=hash_secret(BINDING)).count() == 2


@pytest.mark.parametrize("hostile", HOSTILE_PATHS)
def test_AC_IDA_19_hostile_return_path_goes_home(client: Client, hostile: str) -> None:
    response = start(client, return_path=hostile)

    assert response.status_code == 200  # not an error: the attempt keeps "Inicio"
    assert LoginAttempt.objects.get().return_path == "/"
    assert "evil.example" not in response.content.decode()


@pytest.mark.parametrize("body", [{}, {"return_path": None}, {"return_path": ""}])
def test_AC_IDA_19_missing_return_path_goes_home(client: Client, body: dict[str, Any]) -> None:
    assert start(client, **body).status_code == 200
    assert LoginAttempt.objects.get().return_path == "/"


def test_AC_IDA_20_eleventh_start_is_429_without_google(client: Client) -> None:
    statuses = [start(client).status_code for _ in range(10)]
    assert statuses == [200] * 10

    response = start(client)

    assert response.status_code == 429
    assert response["Content-Type"] == "application/problem+json"
    problem = response.json()
    assert problem["code"] == "rate_limited"
    assert problem["title"] == "Demasiadas solicitudes"
    assert 0 < int(response["Retry-After"]) <= 60
    assert len(gateway_calls) == 10  # the 11th never reached the gateway
    assert LoginAttempt.objects.count() == 10


def test_AC_IDA_37_ten_ips_via_bff_no_429(client: Client) -> None:
    # One BFF (one REMOTE_ADDR), ten browsers: nobody shares a quota. Then each uses its own up.
    for _ in range(10):
        statuses = [start(client, ip=f"203.0.113.{host}").status_code for host in range(1, 11)]
        assert statuses == [200] * 10
    assert start(client, ip="203.0.113.1").status_code == 429
    assert start(client, ip="203.0.113.11").status_code == 200


def test_RNF_IDA_06_flag_off_is_503(client: Client, settings: SettingsWrapper) -> None:
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": False}

    responses = [start(client), start(client, login_binding="malformed")]

    for response in responses:
        assert response.status_code == 503
        assert response["Content-Type"] == "application/problem+json"
        assert response.json()["code"] == "login_disabled"
        assert response.json()["title"] == "Ingreso deshabilitado"
        assert "detail" not in response.json()
    assert gateway_calls == []
    assert not LoginAttempt.objects.exists()


def test_RNF_IDA_06_service_refuses_by_itself_with_the_flag_off(settings: SettingsWrapper) -> None:
    settings.FEATURE_FLAGS = {}
    with pytest.raises(login_start.LoginDisabledError):
        login_start.start_login(return_path="/", login_binding=BINDING)
    assert not LoginAttempt.objects.exists()


def test_start_without_credential_is_a_missing_route(client: Client) -> None:
    body = {"login_binding": BINDING}
    for headers in ({}, {"X-Hub-Bff-Credential": "wrong"}):
        response = client.post(START, body, content_type="application/json", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
        assert "Allow" not in response
    assert gateway_calls == []
    assert not LoginAttempt.objects.exists()


@pytest.mark.parametrize(
    "binding", ["short-binding-value", "b" * 44, "b" * 42 + "!", "", None, 7, ["b" * 43]]
)
def test_malformed_binding_is_400_without_echoing_it(client: Client, binding: object) -> None:
    response = start(client, login_binding=binding)

    assert response.status_code == 400
    problem = response.json()
    assert problem["code"] == "validation_error"
    assert {error["field"] for error in problem["errors"]} == {"login_binding"}
    if isinstance(binding, str) and binding:
        assert binding not in response.content.decode()
    assert not LoginAttempt.objects.exists()


def test_start_without_binding_or_with_a_body_that_is_no_object_is_400(client: Client) -> None:
    headers = {"X-Hub-Bff-Credential": CREDENTIAL}
    for body in ({"return_path": "/cobros"}, ["x"], "text"):
        response = client.post(
            START, json.dumps(body), content_type="application/json", headers=headers
        )
        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"
    assert not LoginAttempt.objects.exists()


def test_AC_IDA_23_start_logs_no_secret(client: Client) -> None:
    with capture_logs() as logs:
        response = start(client, return_path="/cobros")

    query = query_of(response)
    attempt = LoginAttempt.objects.get()
    assert login_start.LOGIN_STARTED_EVENT in [entry["event"] for entry in logs]
    logged = str(logs)
    secrets = (query["state"], query["nonce"], attempt.code_verifier, BINDING, CREDENTIAL)
    for value in (*secrets, CLIENT_VALUE, attempt.state_hash):
        assert value not in logged


def test_RN_IDA_16_hub_without_google_client_starts_nothing(settings: SettingsWrapper) -> None:
    settings.IDENTITY_GOOGLE_CLIENT_ID = ""

    response = start(Client(raise_request_exception=False))

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "IDENTITY_GOOGLE" not in response.content.decode()
    assert not LoginAttempt.objects.exists()


def test_C_06_error_report_hides_the_bff_credential(settings: SettingsWrapper) -> None:
    request = RequestFactory().post(START, headers={"X-Hub-Bff-Credential": CREDENTIAL})
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        reporter = ExceptionReporter(request, *sys.exc_info())
        report = reporter.get_traceback_text() + reporter.get_traceback_html()
    assert "HTTP_X_HUB_BFF_CREDENTIAL" in report  # the key is shown, its value is not
    assert "IDENTITY_BFF_CREDENTIALS" in report
    assert CREDENTIAL not in report


# --- The table (design.md §5) ------------------------------------------------------------------


def make_attempt(**overrides: Any) -> LoginAttempt:
    now = timezone.now()
    values: dict[str, Any] = {
        "state_hash": hash_secret("state"),
        "nonce_hash": hash_secret("nonce"),
        "binding_hash": hash_secret(BINDING),
        "code_verifier": "v" * 43,
        "return_path": "/",
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
    }
    return LoginAttempt.objects.create(**(values | overrides))


def test_RF_IDA_01_state_is_unique() -> None:
    make_attempt()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_attempt()


@pytest.mark.parametrize("column", ["state_hash", "nonce_hash", "binding_hash"])
def test_RF_IDA_01_database_refuses_a_raw_secret_where_a_hash_goes(column: str) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_attempt(**{column: "s" * 43})
    with pytest.raises(IntegrityError), transaction.atomic():
        make_attempt(**{column: hash_secret("x").upper()})


@pytest.mark.parametrize("minutes", [9, 11, 60 * 24])
def test_RF_IDA_01_attempt_lives_exactly_ten_minutes(minutes: int) -> None:
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_attempt(created_at=now, expires_at=now + timedelta(minutes=minutes))


# --- The contract ------------------------------------------------------------------------------


def test_contract_publishes_start_as_bff_internal() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    operation = contract["paths"][START]["post"]
    assert operation["tags"] == ["bff-internal"]
    assert operation["security"] == [{"BffCredential": []}]
    assert {"200", "429", "503"} <= set(operation["responses"])
    scheme = contract["components"]["securitySchemes"]["BffCredential"]
    assert (scheme["type"], scheme["in"], scheme["name"]) == (
        "apiKey",
        "header",
        "X-Hub-Bff-Credential",
    )
    request = contract["components"]["schemas"]["LoginStartRequest"]
    assert request["required"] == ["login_binding"]
    assert set(request["properties"]) == {"login_binding", "return_path"}
    assert contract["info"]["version"] == "0.3.0"
