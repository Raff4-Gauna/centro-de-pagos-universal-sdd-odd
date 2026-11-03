"""Test settings: ``DJANGO_SETTINGS_MODULE=config.settings.test`` (pytest, CI ``tests`` job).

Same validation as dev: the CI job sets non-secret values for the required variables. The cache
is in memory so unit tests never need Redis; integration tests that do (throttling, /readyz)
override it.
"""

from __future__ import annotations

from apps.common.logging.setup import logging_config
from config.settings.base import *  # noqa: F403
from config.settings.base import CACHE_KEY_PREFIX
from config.settings.env import PlatformEnv, load_env

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
APP_VERSION = _env.APP_VERSION
LOGGING = logging_config(_env.LOG_LEVEL)

# Drop the env object: it must not outlive the settings it fed (C-06).
del _env
