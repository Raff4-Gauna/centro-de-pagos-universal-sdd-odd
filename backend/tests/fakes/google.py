"""A fake Google for tests: Google is never called in CI (design.md sec. 9).

It signs ID tokens with an RSA key of its own and serves its JWKS from memory. Both of the
gateway's network paths are faked at their edge, so the code under test is the real one:

* token endpoint: ``FakeGoogle.transport`` (``httpx.MockTransport``) for ``GoogleGateway``;
* JWKS: ``FakeGoogle.install_jwks(monkeypatch)`` replaces the urllib opener ``PyJWKClient``
  builds, so its own fetch, cache, cooldown and error handling run unchanged.

Failures are queued per endpoint (``fail_token`` / ``fail_jwks``): a status code, or an exception
raised instead of answering (a timeout, a connection error).
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from functools import cache
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.identity.oidc.google_gateway import GoogleOidcConfig

CLIENT_ID = "hub-test.apps.googleusercontent.com"
OTHER_CLIENT_ID = "someone-else.apps.googleusercontent.com"
ISSUER = "https://accounts.google.com"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
SUB = "109876543210987654321"


@cache
def rsa_key(index: int) -> rsa.RSAPrivateKey:
    """Generated once per run and index (RSA generation is slow); never a key from the repo."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def config(**overrides: Any) -> GoogleOidcConfig:
    values: dict[str, Any] = {
        "client_id": CLIENT_ID,
        "client_secret": "fake-client-secret",
        "redirect_uri": "https://hub.test/api/auth/google/callback",
    }
    return GoogleOidcConfig(**(values | overrides))


@dataclass
class FakeGoogle:
    key_index: int = 0
    token_requests: list[httpx.Request] = field(default_factory=list)
    jwks_fetches: list[float | None] = field(default_factory=list)
    _token_failures: list[int | Exception] = field(default_factory=list)
    _jwks_failures: list[int | Exception] = field(default_factory=list)
    next_id_token: str | None = None

    @property
    def kid(self) -> str:
        return f"fake-google-{self.key_index}"

    def rotate_key(self) -> None:
        """Google starts signing with a new key and publishes only that one."""
        self.key_index += 1

    # --- ID tokens ---

    def claims(self, *, nonce: str, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        return {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "azp": CLIENT_ID,
            "sub": SUB,
            "email": "ana@example.com",
            "email_verified": True,
            "name": "Ana",
            "picture": "https://lh3.googleusercontent.com/a/ana",
            "nonce": nonce,
            "iat": now,
            "exp": now + 3600,
        } | overrides

    def id_token(
        self,
        *,
        nonce: str,
        key: rsa.RSAPrivateKey | None = None,
        kid: str | None = None,
        **overrides: Any,
    ) -> str:
        """Signed like Google signs (RS256, ``kid``); ``key`` forges it with another key."""
        signer = key or rsa_key(self.key_index)
        headers = {"kid": kid or self.kid}
        return jwt.encode(
            self.claims(nonce=nonce, **overrides), signer, algorithm="RS256", headers=headers
        )

    def jwks(self) -> dict[str, Any]:
        public = rsa_key(self.key_index).public_key()
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public))
        return {"keys": [jwk | {"kid": self.kid, "alg": "RS256", "use": "sig"}]}

    # --- token endpoint (httpx) ---

    def fail_token(self, *failures: int | Exception) -> None:
        self._token_failures.extend(failures)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._token_endpoint)

    def _token_endpoint(self, request: httpx.Request) -> httpx.Response:
        self.token_requests.append(request)
        if self._token_failures:
            failure = self._token_failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return httpx.Response(failure, json={"error": "fake_failure"})
        token = self.next_id_token or self.id_token(nonce="unset")
        return httpx.Response(200, json={"id_token": token, "token_type": "Bearer"})

    # --- JWKS (urllib, as PyJWKClient fetches it) ---

    def fail_jwks(self, *failures: int | Exception) -> None:
        self._jwks_failures.extend(failures)

    def install_jwks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: _Opener(self))

    def _jwks_endpoint(self, url: str, timeout: float | None) -> io.BytesIO:
        self.jwks_fetches.append(timeout)
        if url != JWKS_URI:
            raise urllib.error.URLError("unexpected host")
        if self._jwks_failures:
            failure = self._jwks_failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            raise urllib.error.HTTPError(url, failure, "fake failure", Message(), None)
        return io.BytesIO(json.dumps(self.jwks()).encode())


class _Opener:
    def __init__(self, google: FakeGoogle) -> None:
        self._google = google

    def open(self, request: urllib.request.Request, timeout: float | None = None) -> io.BytesIO:
        return self._google._jwks_endpoint(request.full_url, timeout)
