"""AC-PLT-30 (RN-PLT-19, RF-PLT-17, Q-038): the global anonymous throttle answers 429 (T-PLT-16).

A DRF view (``/api/test/problems``) is hit past ``API_THROTTLE_ANON_RATE``: ``429 throttled`` as
problem+json with ``Retry-After``. The rate is the one of the running settings, not of import time.
The history lives in the default cache: LocMemCache here (``config.settings.test``), the job's Redis
in the ``integration`` test. If Redis fails the request goes through (fail-open, D-06) and only the
exception type is logged. The health views are plain Django views: never throttled (RN-PLT-17).
"""

from __future__ import annotations

import json
import logging
import os
import socket
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper
from redis import Redis
from rest_framework.settings import api_settings

from apps.common.api.problems import PROBLEM_CONTENT_TYPE
from apps.common.api.throttling import CACHE_UNAVAILABLE_EVENT, HubAnonRateThrottle
from apps.common.middleware.request_id import REQUEST_ID_HEADER
from config.settings.env import PlatformEnv, load_env

pytestmark = pytest.mark.urls("tests.api.urls_test")

PROBLEMS = "/api/test/problems"
# DRF's cache key for an anonymous client of the test client's REMOTE_ADDR.
ANON_HISTORY = "throttle_anon_127.0.0.1"
SENTINEL = "sentinel-7c2a"
THROTTLE_LOGGER = "apps.common.api.throttling"


@pytest.fixture(autouse=True)
def empty_history() -> Iterator[None]:
    """Each test starts without throttle history (LocMemCache lives as long as the process)."""
    cache.clear()
    yield
    cache.clear()


def hit(client: Client, times: int) -> list[int]:
    return [client.get(PROBLEMS).status_code for _ in range(times)]


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


def test_AC_PLT_30_throttle_is_the_default_of_every_drf_view() -> None:
    assert list(api_settings.DEFAULT_THROTTLE_CLASSES) == [HubAnonRateThrottle]
    # Keyed on REMOTE_ADDR unless the environment trusts proxies (TRUSTED_PROXY_COUNT).
    assert api_settings.NUM_PROXIES == 0


def test_AC_PLT_30_exceeding_anon_rate_returns_429_with_retry_after(
    client: Client, settings: SettingsWrapper
) -> None:
    settings.API_THROTTLE_ANON_RATE = "2/min"
    assert hit(client, 2) == [200, 200]
    response = client.get(PROBLEMS)
    assert response.status_code == 429
    assert 1 <= int(response["Retry-After"]) <= 60


def test_AC_PLT_30_429_body_is_problem_json_throttled(
    client: Client, settings: SettingsWrapper
) -> None:
    settings.API_THROTTLE_ANON_RATE = "1/min"
    client.get(PROBLEMS)
    response = client.get(PROBLEMS)
    assert response.status_code == 429
    assert response["Content-Type"] == PROBLEM_CONTENT_TYPE
    body = json.loads(response.content)
    assert body["type"] == "urn:hub:problem:throttled"
    assert (body["code"], body["status"]) == ("throttled", 429)
    assert body["title"] == "Demasiadas solicitudes"
    assert body["request_id"] == response[REQUEST_ID_HEADER]


def test_AC_PLT_30_rate_read_from_settings_at_runtime(
    client: Client, settings: SettingsWrapper
) -> None:
    settings.API_THROTTLE_ANON_RATE = "1/min"
    assert hit(client, 2) == [200, 429]
    cache.clear()
    settings.API_THROTTLE_ANON_RATE = "3/min"
    assert hit(client, 4) == [200, 200, 200, 429]


def test_AC_PLT_30_forged_forwarded_for_does_not_reset_the_count(
    client: Client, settings: SettingsWrapper
) -> None:
    # NUM_PROXIES=0: X-Forwarded-For is ignored, so a client cannot pose as another one.
    settings.API_THROTTLE_ANON_RATE = "1/min"
    first = client.get(PROBLEMS, HTTP_X_FORWARDED_FOR="203.0.113.1")
    second = client.get(PROBLEMS, HTTP_X_FORWARDED_FOR="203.0.113.2")
    assert (first.status_code, second.status_code) == (200, 429)


def test_AC_PLT_30_default_anon_rate_is_300_per_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_THROTTLE_ANON_RATE", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_COUNT", raising=False)
    env = load_env(PlatformEnv)
    assert (env.API_THROTTLE_ANON_RATE, env.TRUSTED_PROXY_COUNT) == ("300/min", 0)


@pytest.mark.parametrize(
    ("variable", "value", "error"),
    [
        ("API_THROTTLE_ANON_RATE", "300/mni", "throttle_rate_format"),
        ("API_THROTTLE_ANON_RATE", "0/min", "throttle_rate_format"),
        ("API_THROTTLE_ANON_RATE", "300", "throttle_rate_format"),
        ("TRUSTED_PROXY_COUNT", "-1", "greater_than_equal"),
        ("TRUSTED_PROXY_COUNT", "two", "int_parsing"),
    ],
)
def test_AC_PLT_30_invalid_throttle_env_does_not_start(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, error: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ImproperlyConfigured) as raised:
        load_env(PlatformEnv)
    assert f"{variable}: {error}" in str(raised.value)
    assert value not in str(raised.value)


@pytest.mark.integration
def test_AC_PLT_30_counts_in_redis(client: Client, settings: SettingsWrapper) -> None:
    settings.CACHES = redis_caches(os.environ["REDIS_URL"])
    settings.API_THROTTLE_ANON_RATE = "2/min"
    key = cache.make_key(ANON_HISTORY)
    assert key == f"hub:1:{ANON_HISTORY}"
    redis = Redis.from_url(os.environ["REDIS_URL"])
    redis.delete(key)
    try:
        assert hit(client, 2) == [200, 200]
        # The history is in Redis, under the platform prefix: one timestamp per request.
        assert redis.exists(key) == 1
        assert len(cache.get(ANON_HISTORY)) == 2
        assert client.get(PROBLEMS).status_code == 429
    finally:
        redis.delete(key)
        redis.close()


def test_D06_throttle_fails_open_when_redis_down(
    client: Client,
    settings: SettingsWrapper,
    closed_port: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings.CACHES = redis_caches(f"redis://:{SENTINEL}-pass@127.0.0.1:{closed_port}/0")
    settings.API_THROTTLE_ANON_RATE = "1/min"
    caplog.set_level(logging.WARNING, logger=THROTTLE_LOGGER)
    assert hit(client, 2) == [200, 200]
    records = [rec for rec in caplog.records if rec.getMessage() == CACHE_UNAVAILABLE_EVENT]
    assert len(records) == 2
    for record in records:
        assert record.levelno == logging.WARNING
        assert record.__dict__["scope"] == "anon"
        assert record.__dict__["error_type"] == "ConnectionError"
        # Only the type: the driver message would carry the address (and the URL its password).
        rendered = str(vars(record))
        for leak in (SENTINEL, str(closed_port)):
            assert leak not in rendered, leak


def test_RN_PLT_17_health_not_throttled(client: Client, settings: SettingsWrapper) -> None:
    settings.API_THROTTLE_ANON_RATE = "1/min"
    assert hit(client, 2) == [200, 429]  # the throttle is on and this client is over it
    assert [client.get("/healthz").status_code for _ in range(3)] == [200, 200, 200]
    # Without the job's services /readyz is 503 (not ready), never 429.
    assert 429 not in [client.get("/readyz").status_code for _ in range(3)]
