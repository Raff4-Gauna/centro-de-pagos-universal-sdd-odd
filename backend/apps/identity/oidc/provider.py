"""The process's Google gateway and ID token verifier, built from settings (design.md §8.3).

One of each per process and configuration: the verifier holds the JWKS cache (RNF-IDA-01), which a
verifier built per request would throw away, fetching Google's keys on every login. The cache key is
the configuration itself, so a settings change (a test) gets instances of its own.

Fails closed: without a registered client there is no URL to send anybody to, and the fake provider
(``IDENTITY_OIDC_PROVIDER=fake``, Q-122) has no endpoints until T-IDA-20 brings ``dev_oidc``; it is
never answered with Google's. Tests replace the gateway with an in-memory fake (ADR-0004 §14).
"""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.identity.oidc.google_gateway import GoogleGateway, GoogleOidcConfig
from apps.identity.oidc.id_token import IdTokenVerifier

GOOGLE = "google"


def google_oidc_config() -> GoogleOidcConfig:
    """What the settings register with Google; the error names settings, never a value (C-06)."""
    if settings.IDENTITY_OIDC_PROVIDER != GOOGLE:
        raise ImproperlyConfigured("IDENTITY_OIDC_PROVIDER: only 'google' has endpoints so far")
    values: dict[str, str] = {
        "IDENTITY_GOOGLE_CLIENT_ID": settings.IDENTITY_GOOGLE_CLIENT_ID,
        "IDENTITY_GOOGLE_CLIENT_SECRET": settings.IDENTITY_GOOGLE_CLIENT_SECRET,
        "IDENTITY_GOOGLE_REDIRECT_URI": settings.IDENTITY_GOOGLE_REDIRECT_URI,
    }
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ImproperlyConfigured(f"Login with Google is not configured: {', '.join(missing)}")
    return GoogleOidcConfig(
        client_id=values["IDENTITY_GOOGLE_CLIENT_ID"],
        client_secret=values["IDENTITY_GOOGLE_CLIENT_SECRET"],
        redirect_uri=values["IDENTITY_GOOGLE_REDIRECT_URI"],
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
