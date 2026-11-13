"""Test settings: ``DJANGO_SETTINGS_MODULE=config.settings.test`` (pytest, CI ``tests`` job).

Same validation as dev: the CI job sets non-secret values for the required variables. The cache
is in memory so unit tests never need Redis (the throttle counts there too); integration tests that
do (throttling, /readyz) override it with the job's Redis. Each process generates its JWT key pair:
no key in the repo nor in the CI job (C-06).
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

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
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
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
# The Hub's access JWT (ADR-0004 sec. 5), read through apps.identity.tokens.
IDENTITY_JWT_ISSUER = _env.IDENTITY_JWT_ISSUER
IDENTITY_JWT_AUDIENCE = _env.IDENTITY_JWT_AUDIENCE
_jwt_key = ec.generate_private_key(ec.SECP256R1())
IDENTITY_JWT_SIGNING_KID = "test-key"
IDENTITY_JWT_SIGNING_KEY = _jwt_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
IDENTITY_JWT_VERIFICATION_KEYS = {
    IDENTITY_JWT_SIGNING_KID: _jwt_key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
}
del _jwt_key

# Login with Google (design.md sec. 8.3), read through apps.identity.oidc.provider. The secret is
# masked in error reports by the SECRET rule of CredentialSafeReporterFilter (C-06).
IDENTITY_OIDC_PROVIDER = _env.IDENTITY_OIDC_PROVIDER
IDENTITY_GOOGLE_CLIENT_ID = _env.IDENTITY_GOOGLE_CLIENT_ID
IDENTITY_GOOGLE_CLIENT_SECRET = _env.IDENTITY_GOOGLE_CLIENT_SECRET.get_secret_value()
IDENTITY_GOOGLE_REDIRECT_URI = _env.IDENTITY_GOOGLE_REDIRECT_URI

# The fake OIDC provider may run here (Q-122), on the host of Django's test client.
IDENTITY_FAKE_OIDC_ALLOWED = True
IDENTITY_FAKE_OIDC_BASE_URL = "http://testserver"

# Every audit event of the suite stays in memory, where the tests read it (design.md §9).
AUDIT_SINK = "apps.common.audit.sinks.RecordingSink"

# Drop the env object: it must not outlive the settings it fed (C-06).
del _env
