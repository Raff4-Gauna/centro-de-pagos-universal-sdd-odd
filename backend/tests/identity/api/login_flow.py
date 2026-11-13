"""A login through the BFF endpoints with a fake Google in memory (ADR-0004 §14, design.md §9).

``Flow.begin`` calls the real ``login/start`` and reads ``state`` and ``nonce`` from the URL it
returns, as Google would; ``Flow.finish`` relays the redirect to ``login/complete``. The gateway is
the real one over ``FakeGoogle.transport`` and the verifier the real one over its JWKS, so the code
exchange and the ID token checks run unchanged; only the network is fake. The ports are the
in-memory ones of ``tests/identity/fakes.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.cache import cache
from django.test import Client
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.models import User
from apps.identity.oidc.google_gateway import GoogleGateway
from apps.identity.oidc.id_token import IdTokenVerifier
from apps.identity.services import login_complete
from tests.fakes import google
from tests.identity.fakes import Ports, install_ports

START = "/api/auth/bff/login/start/"
COMPLETE = "/api/auth/bff/login/complete/"
CREDENTIAL = "bff-value-of-this-test"
BINDING = "b" * 43
OTHER_BINDING = "c" * 43
CLIENT_VALUE = "a-client-value-nobody-should-read"
IP = "203.0.113.1"
EMAIL = "ana@example.com"
CODE = "google-code-of-this-test"


@dataclass
class Flow:
    client: Client
    google: google.FakeGoogle
    ports: Ports
    gateway_calls: list[None] = field(default_factory=list)

    def begin(self, *, binding: str = BINDING) -> tuple[str, str]:
        """A new attempt; its ``state`` and ``nonce`` as they travel to Google."""
        response = self.post(START, {"login_binding": binding, "return_path": "/cobros"})
        assert response.status_code == 200
        query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
        return query["state"][0], query["nonce"][0]

    def finish(self, state: str, /, *, binding: str = BINDING, ip: str = IP, **body: Any) -> Any:
        payload: dict[str, object] = {"state": state, "login_binding": binding, "code": CODE}
        return self.post(COMPLETE, payload | body, ip=ip)

    def login(self, **claims: Any) -> Any:
        """``begin`` and ``finish``, Google vouching for ``claims`` over the defaults."""
        state, nonce = self.begin()
        self.google.next_id_token = self.google.id_token(nonce=nonce, **claims)
        return self.finish(state)

    def post(self, path: str, body: dict[str, object], *, ip: str = IP) -> Any:
        headers = {"X-Hub-Bff-Credential": CREDENTIAL, "X-Hub-Client-IP": ip}
        return self.client.post(path, body, content_type="application/json", headers=headers)


@pytest.fixture
def flow(
    client: Client, settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Flow]:
    config = google.config()
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    settings.FEATURE_FLAGS = {"IDENTITY_GOOGLE_LOGIN": True}
    settings.IDENTITY_OIDC_PROVIDER = "google"
    settings.IDENTITY_GOOGLE_CLIENT_ID = config.client_id
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = CLIENT_VALUE
    settings.IDENTITY_GOOGLE_REDIRECT_URI = config.redirect_uri
    fake = google.FakeGoogle()
    fake.install_jwks(monkeypatch)
    current = Flow(client=client, google=fake, ports=install_ports(settings))
    verifier = IdTokenVerifier(config)

    def gateway() -> GoogleGateway:
        current.gateway_calls.append(None)
        return GoogleGateway(config, transport=fake.transport)

    monkeypatch.setattr(login_complete, "get_google_gateway", gateway)
    monkeypatch.setattr(login_complete, "get_id_token_verifier", lambda: verifier)
    cache.clear()
    yield current
    cache.clear()


def make_user(sub: str = google.SUB, email: str = EMAIL, *, active: bool = True) -> User:
    user = User.objects.create_user(google_sub=sub, email=email)
    if not active:
        User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=user.created_at)
        user.refresh_from_db()
    return user
