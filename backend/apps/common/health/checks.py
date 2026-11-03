"""Readiness checks behind /readyz (design.md §3.2.5, RN-PLT-17, Q-039).

Each check raises on failure. ``failed_checks()`` runs all of them and returns the names of the
ones that failed; the cause goes to the ``health.not_ready`` WARNING log as the check name and the
exception *type* only. Exception messages are never logged: a driver error can carry a host, a
user or a DSN (C-06), and the response body never carries anything (views.py).

Bounded time, never a hang: PostgreSQL uses the ``connect_timeout=2`` of ``DATABASES`` (env.py)
and Redis gets a client of its own with 1 s timeouts and no retries. Both timeouts apply per
resolved address (libpq tries each address a host name resolves to, e.g. ``::1`` and
``127.0.0.1`` for ``localhost``; redis-py does the same), so a dead dependency can take /readyz
past 3 s; the bound is per address, not a total.

The Redis bounds are forced on the pool *after* parsing the URL: redis-py lets the URL query string
win over ``from_url()`` kwargs, so a ``REDIS_URL`` with ``?socket_timeout=30`` would otherwise
lift them. Connections built through ``from_url`` already default to ``Retry(NoBackoff(), 0)``
(the 3 retries with backoff are only for a pool that ``Redis()`` builds itself); the explicit
no-retry policy is defence in depth, and also wins over ``?retry_on_timeout=true``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.db import connections
from redis import ConnectionPool, Redis
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


def redis_client(url: str) -> Redis:
    """A one-off client for ``url`` with the /readyz bounds, whatever the URL query says."""
    pool = ConnectionPool.from_url(url)
    pool.connection_kwargs.update(
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), 0),
    )
    client = Redis(connection_pool=pool)
    # Closing the client also disconnects its private pool (as with Redis.from_url).
    client.auto_close_connection_pool = True
    return client


def check_redis() -> None:
    for url in redis_urls():
        client = redis_client(url)
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
