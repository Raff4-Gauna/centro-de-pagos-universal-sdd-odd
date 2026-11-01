# ruff: noqa: N999 - the module name carries the uppercase AC ID (AGENTS.md); flagged since
# tests/health/ is a package. The repo-wide fix belongs in ruff.toml (T-PLT-08 review).
"""AC-PLT-02 (RN-PLT-17, RF-PLT-07, Q-039): /healthz and /readyz (T-PLT-11).

``/readyz`` answers 200 only when PostgreSQL and Redis answer; otherwise 503 with a fixed body and
the cause only in the ``health.not_ready`` log (check name and exception type, never a host, a DSN
or a message, C-06). ``/healthz`` has no dependencies: it stays 200 with the short SHA while Redis
is down. Both are ``no-store`` and need no credentials.

A service is "down" when its URL points at a closed local port. The ``integration`` tests need the
real services of the CI ``tests`` job (``DATABASE_URL``/``REDIS_URL``): each one keeps the *other*
dependency up, so the log proves which check failed. The rest run without any service: pytest-django
blocks the database, so a /healthz that touched it would fail.
"""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Iterator
from typing import Any

import pytest
from apps.common.health import checks
from django.db import connections
from django.test import Client
from pytest_django import DjangoDbBlocker
from pytest_django.fixtures import Settings as SettingsWrapper

SENTINEL = "sentinel"
FULL_SHA = "0123456789abcdef0123456789abcdef01234567"
HEALTH_LOGGER = "apps.common.health"
BODY_LEAKS = ("127.0.0.1", "localhost", "redis", "postgres", "error", "traceback", SENTINEL)


def redis_caches(location: str) -> dict[str, dict[str, Any]]:
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": location,
            "KEY_PREFIX": "hub",
        }
    }


@pytest.fixture
def closed_port() -> int:
    """A local port nobody listens on: bound by the OS, then released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


@pytest.fixture
def redis_up(settings: SettingsWrapper) -> None:
    """The real Redis of the job (test settings use LocMemCache otherwise)."""
    settings.CACHES = redis_caches(os.environ["REDIS_URL"])


@pytest.fixture
def redis_down(settings: SettingsWrapper, closed_port: int) -> None:
    settings.CACHES = redis_caches(f"redis://:{SENTINEL}-redis-pass@127.0.0.1:{closed_port}/0")


@pytest.fixture
def database_down(
    django_db_blocker: DjangoDbBlocker, closed_port: int, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """The default connection points at a closed port, with database access allowed."""
    connection = connections["default"]
    connection.close()
    monkeypatch.setitem(connection.settings_dict, "HOST", "127.0.0.1")
    monkeypatch.setitem(connection.settings_dict, "PORT", str(closed_port))
    monkeypatch.setitem(connection.settings_dict, "PASSWORD", f"{SENTINEL}-db-pass")
    with django_db_blocker.unblock():
        yield
        connection.close()


@pytest.fixture
def health_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.WARNING, logger=HEALTH_LOGGER)
    return caplog


def not_ready_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == "health.not_ready"]


def failed_checks(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.__dict__["check"] for record in not_ready_records(caplog)]


def assert_not_ready_without_details(response: Any, closed_port: int) -> None:
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    rendered = (response.content.decode() + str(dict(response.headers))).lower()
    for leak in (*BODY_LEAKS, str(closed_port)):
        assert leak not in rendered, leak


def assert_log_has_no_secret(caplog: pytest.LogCaptureFixture, closed_port: int) -> None:
    records = not_ready_records(caplog)
    assert records, "the failure must reach the log"
    for record in records:
        assert record.levelno == logging.WARNING
        assert record.__dict__["error_type"]  # the exception class name, never its message
        # Neither the credentials nor the address: a driver message would carry the host/port.
        rendered = str(vars(record)).lower()
        for leak in (SENTINEL, "127.0.0.1", str(closed_port)):
            assert leak not in rendered, leak
    assert SENTINEL not in caplog.text.lower()


@pytest.mark.integration
@pytest.mark.django_db
def test_AC_PLT_02_readyz_200_when_db_and_redis_up(
    client: Client, redis_up: None, health_log: pytest.LogCaptureFixture
) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert not_ready_records(health_log) == []


@pytest.mark.integration
@pytest.mark.django_db
def test_AC_PLT_02_readyz_503_when_redis_down_without_internal_details(
    client: Client, redis_down: None, closed_port: int, health_log: pytest.LogCaptureFixture
) -> None:
    response = client.get("/readyz")
    assert_not_ready_without_details(response, closed_port)
    # The database is up: only Redis failed.
    assert failed_checks(health_log) == ["redis"]
    assert_log_has_no_secret(health_log, closed_port)


@pytest.mark.integration
def test_AC_PLT_02_readyz_503_when_db_down(
    client: Client,
    database_down: None,
    redis_up: None,
    closed_port: int,
    health_log: pytest.LogCaptureFixture,
) -> None:
    response = client.get("/readyz")
    assert_not_ready_without_details(response, closed_port)
    # Redis is up: only the database failed.
    assert failed_checks(health_log) == ["database"]
    assert_log_has_no_secret(health_log, closed_port)


@pytest.mark.integration
@pytest.mark.django_db
def test_AC_PLT_02_readyz_503_when_cache_is_not_redis(
    client: Client, health_log: pytest.LogCaptureFixture
) -> None:
    # config.settings.test keeps LocMemCache: no Redis was checked, so not ready (fail closed).
    response = client.get("/readyz")
    assert response.status_code == 503
    assert failed_checks(health_log) == ["redis"]


def test_C_06_not_ready_log_has_no_exception_message(
    client: Client, health_log: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A driver message can carry a host, a user or a DSN; only the exception type is logged.
    def fail() -> None:
        raise ConnectionError(f"{SENTINEL}-host:6379 user={SENTINEL}-user")

    for name in checks.CHECKS:
        monkeypatch.setitem(checks.CHECKS, name, fail)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert failed_checks(health_log) == ["database", "redis"]
    for record in not_ready_records(health_log):
        assert record.__dict__["error_type"] == "ConnectionError"
        assert SENTINEL not in str(vars(record)).lower()


def test_AC_PLT_02_healthz_200_with_short_sha_while_redis_down(
    client: Client,
    redis_down: None,
    settings: SettingsWrapper,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.APP_VERSION = FULL_SHA
    ran: list[str] = []
    for name in checks.CHECKS:
        monkeypatch.setitem(checks.CHECKS, name, lambda name=name: ran.append(name))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": FULL_SHA[:7]}
    assert ran == []  # liveness never runs a readiness check


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_AC_PLT_02_health_is_no_store_and_unauthenticated(
    client: Client, redis_down: None, path: str
) -> None:
    # No credentials, cookie nor CSRF token: an orchestrator probes it as is.
    response = client.get(path)
    assert response.status_code in {200, 503}  # never 401/403 nor a redirect to a login
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Type"] == "application/json"
    assert "WWW-Authenticate" not in response
    assert client.head(path).status_code == response.status_code
