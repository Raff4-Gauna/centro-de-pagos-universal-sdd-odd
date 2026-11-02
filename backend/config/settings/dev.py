"""Development settings: ``DJANGO_SETTINGS_MODULE=config.settings.dev`` (Compose, T-PLT-26).

``DJANGO_DEBUG`` defaults to false here too: Compose sets it to ``true`` for dev on purpose.
"""

from __future__ import annotations

from apps.common.feature_flags import REGISTRY as FEATURE_REGISTRY
from apps.common.logging.setup import logging_config
from config.settings.base import *  # noqa: F403
from config.settings.base import CACHE_KEY_PREFIX
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
APP_VERSION = _env.APP_VERSION
LOGGING = logging_config(_env.LOG_LEVEL)
# RF-PLT-19: read through apps.common.feature_flags.is_enabled, never directly.
FEATURE_FLAGS = load_feature_flags(FEATURE_REGISTRY)

# Drop the env object: it must not outlive the settings it fed (C-06).
del _env
