"""The process's OIDC gateway and ID token verifier, built from settings (design.md §8.3).

One of each per process and configuration: the verifier holds the JWKS cache (RNF-IDA-01), which a
verifier built per request would throw away, fetching the keys on every login. The cache key is
the configuration itself, so a settings change (a test) gets instances of its own.

Two providers, one gateway (Q-122): ``google``, with Google's endpoints, and ``fake``, the OIDC
provider of dev and test (``apps.identity.dev_oidc``), which speaks the same protocol on endpoints
of its own. The fake one is only answered where the settings allow it
(``IDENTITY_FAKE_OIDC_ALLOWED``, ``True`` only in ``dev.py`` and ``test.py``); anywhere else it
fails closed, and ``IdentityConfig.ready()`` does not even let the process start. Without a
registered client there is no URL to send anybody to: that fails closed too. Pytest does not use
the fake over HTTP for the login itself: it replaces the gateway with an in-memory fake (ADR-0004
§14).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.identity.oidc.google_gateway import (
    GOOGLE_AUTHORIZATION_ENDPOINT,
    GOOGLE_ISSUERS,
    GOOGLE_JWKS_URI,
    GOOGLE_TOKEN_ENDPOINT,
    GoogleGateway,
    GoogleOidcConfig,
)
from apps.identity.oidc.id_token import IdTokenVerifier

GOOGLE: Final = "google"
FAKE: Final = "fake"
DEV_OIDC_PATH: Final = "/dev-oidc"
FAKE_NOT_ALLOWED: Final = (
    "IDENTITY_OIDC_PROVIDER: 'fake' is only for the dev and test settings (Q-122)"
)


@dataclass(frozen=True, slots=True)
class OidcEndpoints:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    issuers: frozenset[str]


GOOGLE_ENDPOINTS: Final = OidcEndpoints(
    authorization_endpoint=GOOGLE_AUTHORIZATION_ENDPOINT,
    token_endpoint=GOOGLE_TOKEN_ENDPOINT,
    jwks_uri=GOOGLE_JWKS_URI,
    issuers=GOOGLE_ISSUERS,
)


def fake_oidc_allowed() -> bool:
    return settings.IDENTITY_FAKE_OIDC_ALLOWED is True


def fake_oidc_active() -> bool:
    return settings.IDENTITY_OIDC_PROVIDER == FAKE and fake_oidc_allowed()


def fake_issuer() -> str:
    """``<IDENTITY_FAKE_OIDC_BASE_URL>/dev-oidc``: the browser and this backend both reach it."""
    base = settings.IDENTITY_FAKE_OIDC_BASE_URL.rstrip("/")
    if not base:
        raise ImproperlyConfigured("IDENTITY_FAKE_OIDC_BASE_URL is not set")
    return f"{base}{DEV_OIDC_PATH}"


def oidc_endpoints() -> OidcEndpoints:
    """The endpoints of the configured provider; the error names settings, never a value."""
    if settings.IDENTITY_OIDC_PROVIDER == GOOGLE:
        return GOOGLE_ENDPOINTS
    if not fake_oidc_active():
        raise ImproperlyConfigured(FAKE_NOT_ALLOWED)
    issuer = fake_issuer()
    return OidcEndpoints(
        authorization_endpoint=f"{issuer}/authorize",
        token_endpoint=f"{issuer}/token",
        jwks_uri=f"{issuer}/jwks",
        issuers=frozenset({issuer}),
    )


def missing_client_settings() -> list[str]:
    """The client settings left empty: with any of them, nobody can log in."""
    values = {
        "IDENTITY_GOOGLE_CLIENT_ID": settings.IDENTITY_GOOGLE_CLIENT_ID,
        "IDENTITY_GOOGLE_CLIENT_SECRET": settings.IDENTITY_GOOGLE_CLIENT_SECRET,
        "IDENTITY_GOOGLE_REDIRECT_URI": settings.IDENTITY_GOOGLE_REDIRECT_URI,
    }
    return sorted(name for name, value in values.items() if not value)


def google_oidc_config() -> GoogleOidcConfig:
    """What the settings register with the provider (C-06: errors name settings only)."""
    endpoints = oidc_endpoints()
    missing = missing_client_settings()
    if missing:
        raise ImproperlyConfigured(f"Login with Google is not configured: {', '.join(missing)}")
    return GoogleOidcConfig(
        client_id=settings.IDENTITY_GOOGLE_CLIENT_ID,
        client_secret=settings.IDENTITY_GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.IDENTITY_GOOGLE_REDIRECT_URI,
        authorization_endpoint=endpoints.authorization_endpoint,
        token_endpoint=endpoints.token_endpoint,
        jwks_uri=endpoints.jwks_uri,
        issuers=endpoints.issuers,
    )


@lru_cache(maxsize=1)
def _gateway_for(config: GoogleOidcConfig) -> GoogleGateway:
    return GoogleGateway(config)


@lru_cache(maxsize=1)
def _verifier_for(config: GoogleOidcConfig) -> IdTokenVerifier:
    return IdTokenVerifier(config)


def get_google_gateway() -> GoogleGateway:
    return _gateway_for(google_oidc_config())


def get_id_token_verifier() -> IdTokenVerifier:
    return _verifier_for(google_oidc_config())
