"""Production settings: ``DJANGO_SETTINGS_MODULE=config.settings.prod`` (image default, wsgi.py).

``ProdEnv`` is stricter than ``PlatformEnv`` (RN-PLT-02, Q-040): ``DJANGO_ALLOWED_HOSTS`` has no
default and ``DJANGO_DEBUG=true`` does not start. A missing or malformed variable stops the process
with an error that names it and shows no value (AC-PLT-03). The rest of the hardening (SSL, HSTS,
cookies, strong ``SECRET_KEY``, ``check --deploy``) comes with T-PLT-09.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_core import PydanticCustomError

from config.settings.base import *  # noqa: F403
from config.settings.base import CACHE_KEY_PREFIX
from config.settings.env import CsvList, PlatformEnv, load_env


class ProdEnv(PlatformEnv):
    DJANGO_ALLOWED_HOSTS: CsvList

    @field_validator("DJANGO_DEBUG")
    @classmethod
    def _debug_is_off(cls, value: bool) -> bool:
        if value:
            raise PydanticCustomError("debug_on_in_prod", "DEBUG must be false in prod")
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
APP_VERSION = _env.APP_VERSION

# Drop the env object: it must not outlive the settings it fed (C-06).
del _env
