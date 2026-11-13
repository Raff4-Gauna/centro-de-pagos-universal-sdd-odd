"""System checks of identity (RN-IDA-01, RN-IDA-16, RNF-IDA-06, design.md §7.5, §10).

They run with ``manage.py check`` and before every ``migrate`` (the container command of dev, CI
and prod), and an ``Error`` stops it. What must stop even a process that skips the checks
(gunicorn, Celery) lives elsewhere: ``IdentityConfig.ready()`` refuses the fake provider and
``ProdEnv`` refuses a weak BFF credential. Every message names settings, never a value (C-06).

* ``identity.E001``: two purposes share a secret. The Django secret key, the JWT signing key, the
  Google client secret and the BFF credentials (current and previous) are all distinct.
* ``identity.E002``: outside dev and test (``IDENTITY_FAKE_OIDC_ALLOWED`` off: prod, staging), the
  provider is Google, on exactly its endpoints and issuers. They are written out here again on
  purpose, from design.md §3.5: the check pins them instead of trusting the code it checks.
* ``identity.W001``: login is on and the Google client is not complete, so starting a login
  answers ``500 internal_error``. A warning, not an error: the Hub may start without it.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from typing import Any, Final

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, Warning, register
from django.core.exceptions import ImproperlyConfigured

from apps.common import feature_flags
from apps.identity.oidc import provider

EQUAL_SECRETS: Final = "identity.E001"
NOT_GOOGLE_IN_PROD: Final = "identity.E002"
LOGIN_WITHOUT_CLIENT: Final = "identity.W001"
LOGIN_FLAG: Final = "IDENTITY_GOOGLE_LOGIN"

PINNED_GOOGLE: Final = provider.OidcEndpoints(
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",  # noqa: S106 - a URL
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
    issuers=frozenset({"https://accounts.google.com", "accounts.google.com"}),
)


def _secrets() -> dict[str, set[str]]:
    """The non-empty values of each secret, by the variable that sets it."""
    bff = {credential.get_secret_value() for credential in settings.IDENTITY_BFF_CREDENTIALS}
    values = {
        "DJANGO_SECRET_KEY": {settings.SECRET_KEY},
        "IDENTITY_JWT_SIGNING_KEY": {settings.IDENTITY_JWT_SIGNING_KEY},
        "IDENTITY_GOOGLE_CLIENT_SECRET": {settings.IDENTITY_GOOGLE_CLIENT_SECRET},
        "IDENTITY_BFF_CREDENTIALS": bff,
    }
    return {name: {value for value in found if value} for name, found in values.items()}


@register(Tags.security)
def secrets_are_distinct(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    secrets = _secrets()
    return [
        Error(
            f"{first} and {second} share a value: each secret has a purpose of its own",
            hint="Generate a new value for one of them (RN-IDA-16).",
            id=EQUAL_SECRETS,
        )
        for first, second in combinations(secrets, 2)
        if secrets[first] & secrets[second]
    ]


@register(Tags.security)
def provider_is_google_in_prod(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    if provider.fake_oidc_allowed():
        return []
    try:
        endpoints = provider.oidc_endpoints()
    except ImproperlyConfigured:
        endpoints = None
    if endpoints == PINNED_GOOGLE:
        return []
    return [
        Error(
            "IDENTITY_OIDC_PROVIDER: outside dev and test only Google, on its exact endpoints",
            hint="Set IDENTITY_OIDC_PROVIDER=google (RN-IDA-01, Q-122).",
            id=NOT_GOOGLE_IN_PROD,
        )
    ]


@register(Tags.security)
def login_has_a_client(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    missing = provider.missing_client_settings()
    if not feature_flags.is_enabled(LOGIN_FLAG) or not missing:
        return []
    return [
        Warning(
            f"FEATURE_IDENTITY_GOOGLE_LOGIN is on without {', '.join(missing)}",
            hint="Nobody can log in until the Google client of this environment is set.",
            id=LOGIN_WITHOUT_CLIENT,
        )
    ]
