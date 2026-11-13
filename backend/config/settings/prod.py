"""Production settings: ``DJANGO_SETTINGS_MODULE=config.settings.prod`` (image default, wsgi.py).

``ProdEnv`` is stricter than ``PlatformEnv`` (RN-PLT-02, Q-040): ``DJANGO_ALLOWED_HOSTS`` has no
default and no ``*``, ``DJANGO_DEBUG=true`` does not start and ``DJANGO_SECRET_KEY`` must be strong.
A missing or malformed variable stops the process with an error that names it and shows no value
(AC-PLT-03). The rest is the HTTPS hardening that makes ``check --deploy`` pass without warnings
(AC-PLT-04, RNF-PLT-02, design.md §3.2.2).
"""

from __future__ import annotations

from pydantic import SecretStr, field_validator
from pydantic_core import PydanticCustomError

from apps.common.feature_flags import REGISTRY as FEATURE_REGISTRY
from apps.common.logging.setup import logging_config
from config.settings.base import *  # noqa: F403
from config.settings.base import CACHE_KEY_PREFIX, REST_FRAMEWORK
from config.settings.env import CsvList, PlatformEnv, load_env, load_feature_flags

# Django's rule for a usable key (security.W009), checked before start instead of as a warning.
SECRET_KEY_MIN_LENGTH = 50
SECRET_KEY_MIN_DISTINCT = 5
SECRET_KEY_INSECURE_MARK = "django-insecure"  # noqa: S105 - a marker to reject, not a key


class ProdEnv(PlatformEnv):
    DJANGO_ALLOWED_HOSTS: CsvList

    @field_validator("DJANGO_DEBUG")
    @classmethod
    def _debug_is_off(cls, value: bool) -> bool:
        if value:
            raise PydanticCustomError("debug_on_in_prod", "DEBUG must be false in prod")
        return value

    @field_validator("DJANGO_SECRET_KEY")
    @classmethod
    def _secret_key_is_strong(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value()
        if len(key) < SECRET_KEY_MIN_LENGTH:
            raise PydanticCustomError("secret_key_too_short", "the secret key is too short")
        if len(set(key)) < SECRET_KEY_MIN_DISTINCT:
            raise PydanticCustomError("secret_key_few_characters", "too few distinct characters")
        if SECRET_KEY_INSECURE_MARK in key:
            raise PydanticCustomError("secret_key_insecure", "a generated development key")
        return value

    @field_validator("DJANGO_ALLOWED_HOSTS")
    @classmethod
    def _no_wildcard_host(cls, value: list[str]) -> list[str]:
        # "*" would accept any Host header (T-PLT-08 review N-10): prod names its hosts.
        if "*" in value:
            raise PydanticCustomError("allowed_hosts_wildcard", "no '*' in prod")
        return value


ROOT_URLCONF = "config.urls"

_env = load_env(ProdEnv)

SECRET_KEY = _env.DJANGO_SECRET_KEY.get_secret_value()
DEBUG = False
ALLOWED_HOSTS = _env.DJANGO_ALLOWED_HOSTS
DATABASES = _env.databases()
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": str(_env.REDIS_URL.get_secret_value()),
        "KEY_PREFIX": CACHE_KEY_PREFIX,
    }
}
# Celery's broker is the same Redis (design.md §3.2.2). Set here, from the validated env, so Celery
# never reads CELERY_BROKER_URL from the environment itself (AC-PLT-06); hidden in error reports
# by the URL$ rule of CredentialSafeReporterFilter (C-06).
CELERY_BROKER_URL = str(_env.REDIS_URL.get_secret_value())
APP_VERSION = _env.APP_VERSION
# T-PLT-16 (RN-PLT-19): HubAnonRateThrottle reads the rate on every request; the proxies it
# trusts in X-Forwarded-For are DRF's NUM_PROXIES.
API_THROTTLE_ANON_RATE = _env.API_THROTTLE_ANON_RATE
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": _env.TRUSTED_PROXY_COUNT}
LOGGING = logging_config(_env.LOG_LEVEL)
# RF-PLT-19: read through apps.common.feature_flags.is_enabled, never directly.
FEATURE_FLAGS = load_feature_flags(FEATURE_REGISTRY)
# The Hub's access JWT (ADR-0004 sec. 5), read through apps.identity.tokens. Masked in error reports
# by the KEY rule of CredentialSafeReporterFilter (C-06).
IDENTITY_JWT_ISSUER = _env.IDENTITY_JWT_ISSUER
IDENTITY_JWT_AUDIENCE = _env.IDENTITY_JWT_AUDIENCE
IDENTITY_JWT_SIGNING_KID = _env.IDENTITY_JWT_SIGNING_KID
IDENTITY_JWT_SIGNING_KEY = _env.IDENTITY_JWT_SIGNING_KEY.get_secret_value()
IDENTITY_JWT_VERIFICATION_KEYS = _env.IDENTITY_JWT_VERIFICATION_KEYS

# Login with Google (design.md sec. 8.3), read through apps.identity.oidc.provider. The secret is
# masked in error reports by the SECRET rule of CredentialSafeReporterFilter (C-06).
IDENTITY_OIDC_PROVIDER = _env.IDENTITY_OIDC_PROVIDER
IDENTITY_GOOGLE_CLIENT_ID = _env.IDENTITY_GOOGLE_CLIENT_ID
IDENTITY_GOOGLE_CLIENT_SECRET = _env.IDENTITY_GOOGLE_CLIENT_SECRET.get_secret_value()
IDENTITY_GOOGLE_REDIRECT_URI = _env.IDENTITY_GOOGLE_REDIRECT_URI

# Drop the env object: it must not outlive the settings it fed (C-06).
del _env

# HTTPS (design.md §3.2.2, §7). TLS ends at the proxy, which sets X-Forwarded-Proto; everything
# else redirects to https except the internal healthchecks, which speak plain HTTP. The patterns
# match request.path without its leading "/", exactly (the routes have no trailing slash); they
# end in \Z, not $, because $ also matches before a trailing newline ("/healthz%0A").
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz\Z", r"^readyz\Z"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000  # one year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
# The backend sets no cookie in 00; if one appears, it only travels over HTTPS.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# The only silenced check (another one needs an ADR): HSTS preload waits for a domain of our own
# (Q-020); preloading is hard to undo, so it is off on purpose until then.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
