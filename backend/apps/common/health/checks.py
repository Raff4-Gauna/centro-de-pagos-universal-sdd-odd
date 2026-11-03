"""Readiness checks behind /readyz (design.md §3.2.5, RN-PLT-17, Q-039).

Each check raises on failure. ``failed_checks()`` runs all of them and returns the names of the
ones that failed; the cause goes to the ``health.not_ready`` WARNING log as the check name and the
exception *type* only. Exception messages are never logged: a driver error can carry a host, a
user or a DSN (C-06), and the response body never carries anything (views.py).

Bounded time: PostgreSQL uses the ``connect_timeout=2`` of ``DATABASES`` (env.py) and Redis gets
a client of its own with 1 s timeouts and no retries (redis-py retries 3 times with backoff by
default), so a dead dependency makes /readyz slow by ~3 s at most, never hang.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.db import connections
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

logger = logging.getLogger(__name__)

REDIS_CACHE_BACKEND = "django.core.cache.backends.redis.RedisCache"
REDIS_TIMEOUT_SECONDS = 1


class RedisNotConfiguredError(Exception):
    """The default cache is not Redis, so there is no Redis to call ready (fail closed)."""


def check_database() -> None:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def redis_urls() -> list[str]:
    """The Redis servers of the default cache (``REDIS_URL`` in dev/prod; tests override it)."""
    cache = settings.CACHES["default"]
    if cache.get("BACKEND") != REDIS_CACHE_BACKEND:
        raise RedisNotConfiguredError
    location = cache["LOCATION"]
    urls = location.split(",") if isinstance(location, str) else list(location)
    return [url.strip() for url in urls]


def check_redis() -> None:
    for url in redis_urls():
        client = Redis.from_url(
            url,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            retry=Retry(NoBackoff(), 0),
        )
        try:
            client.ping()
        finally:
            client.close()


CHECKS: dict[str, Callable[[], None]] = {
    "database": check_database,
    "redis": check_redis,
}


def failed_checks() -> list[str]:
    """Names of the checks that failed, in ``CHECKS`` order; empty when ready."""
    failed = []
    for name, check in CHECKS.items():
        try:
            check()
        # Any failure means "not ready" (503), never a 500 with a trace.
        except Exception as error:
            failed.append(name)
            logger.warning(
                "health.not_ready",
                extra={"check": name, "error_type": type(error).__name__},
            )
    return failed
