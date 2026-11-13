"""Development settings: ``DJANGO_SETTINGS_MODULE=config.settings.dev`` (Compose, T-PLT-26).

``DJANGO_DEBUG`` defaults to false here too: Compose sets it to ``true`` for dev on purpose.
"""

from __future__ import annotations

from apps.common.feature_flags import REGISTRY as FEATURE_REGISTRY
from apps.common.logging.setup import logging_config
from config.settings.base import *  # noqa: F403
from config.settings.base import CACHE_KEY_PREFIX, REST_FRAMEWORK
from config.settings.env import PlatformEnv, load_env, load_feature_flags

ROOT_URLCONF = "config.urls_dev"

_env = load_env(PlatformEnv)

SECRET_KEY = _env.DJANGO_SECRET_KEY.get_secret_value()
DEBUG = _env.DJANGO_DEBUG
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
