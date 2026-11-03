"""RN-PLT-05 (RF-PLT-05, Q-034, C-16): one JSON event per line on stdout, for every logger.

structlog loggers (``get_logger``) and plain stdlib loggers (Django, libraries) go through the same
``ProcessorFormatter`` and the same only handler: ``timestamp`` (ISO-8601 UTC), ``level``,
``component``, ``message``, plus the ``request_id``/``organization_id`` bound in the context.
``LOG_LEVEL`` (env.py) sets the level. C-06 / T-PLT-08 review N-9: nothing that logging or the
error report emits shows a setting with credentials (the Redis password of ``CACHES``).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory
from django.utils.log import AdminEmailHandler
from django.views.debug import ExceptionReporter
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.logging import context, get_logger
from apps.common.logging.setup import StdoutHandler, configure_logging, logging_config
from apps.common.middleware.access_log import ACCESS_EVENT
from config.settings.env import PlatformEnv, load_env
from tests.logging.conftest import StdoutLog

REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f21-6c0d5e9a7b13"
REQUIRED_FIELDS = {"timestamp", "level", "component", "message"}
SENTINEL = "sentinel-redis-pass"
# Module constants: the error report shows the source lines around each frame, so the test body
# must not spell the secret out.
REDIS_HOST = "redis.example"
REDIS_URL_WITH_PASSWORD = f"redis://:{SENTINEL}@{REDIS_HOST}:6379/0"
REQUIRED_ENV = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DATABASE_URL": "postgres://db.example/hub",
    "REDIS_URL": "redis://redis.example:6379/0",
}


def assert_utc_iso_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset() == UTC.utcoffset(None)


def test_RN_PLT_05_one_json_event_per_line_on_stdout(stdout_log: StdoutLog) -> None:
    context.bind_request(REQUEST_ID)
    logger = get_logger("apps.demo.services")
    logger.info("demo.multiline", note="first line\nsecond line")
    try:
        raise ValueError("demo failure")
    except ValueError:
        logger.exception("demo.failed")
    logger.warning("demo.with_args %s", "formatted")

    log = stdout_log.read()
    assert log.err == ""  # stdout only
    events = log.events  # every line is one JSON object: tracebacks and \n never split an event
    assert [event["message"] for event in events] == [
        "demo.multiline",
        "demo.failed",
        "demo.with_args formatted",
    ]
    assert len(log.lines) == 3
    for event in events:
        assert event.keys() >= REQUIRED_FIELDS
        assert event["component"] == "apps.demo.services"
        assert event["request_id"] == REQUEST_ID
        assert "organization_id" not in event  # only when bound
        assert_utc_iso_timestamp(event["timestamp"])
    assert [event["level"] for event in events] == ["info", "error", "warning"]
    assert events[0]["note"] == "first line\nsecond line"
    assert "ValueError: demo failure" in events[1]["exception"]


def test_RN_PLT_05_stdlib_logger_goes_through_same_renderer(stdout_log: StdoutLog) -> None:
    context.bind_request(REQUEST_ID)
    get_logger("apps.demo").warning("demo.structlog")
    logging.getLogger("thirdparty.lib").warning(
        "disk %s", "low", extra={"check": "redis", "attempt": 2, "request": object()}
    )

    structlog_event, stdlib_event = stdout_log.read().events
    assert stdlib_event["message"] == "disk low"
    assert stdlib_event["level"] == "warning"
    assert stdlib_event["component"] == "thirdparty.lib"
    assert stdlib_event["request_id"] == REQUEST_ID
    assert_utc_iso_timestamp(stdlib_event["timestamp"])
    # extra= scalars become fields; an object (Django attaches the request) is never rendered.
    assert (stdlib_event["check"], stdlib_event["attempt"]) == ("redis", 2)
    assert "request" not in stdlib_event
    # Same shape as a structlog event: same renderer, same fields.
    assert set(structlog_event) == set(stdlib_event) - {"check", "attempt"}


def test_RN_PLT_05_organization_id_is_logged_once_bound(stdout_log: StdoutLog) -> None:
    context.bind_request(REQUEST_ID)
    context.bind_organization("org-1")
    logging.getLogger("thirdparty.lib").info("demo.org")
    (event,) = stdout_log.read().events
    assert event["organization_id"] == "org-1"


def own_handlers(logger: logging.Logger | logging.PlaceHolder) -> list[logging.Handler]:
    """The handlers of ``logger`` minus pytest's capture handlers, added while a test runs."""
    handlers: list[logging.Handler] = getattr(logger, "handlers", [])
    return [handler for handler in handlers if type(handler).__module__ != "_pytest.logging"]


def test_RN_PLT_05_only_handler_is_stdout() -> None:
    root_handlers = own_handlers(logging.getLogger())
    assert len(root_handlers) == 1
    assert all(isinstance(handler, StdoutHandler) for handler in root_handlers)
    assert all(handler.stream is sys.stdout for handler in root_handlers)
    # Django's own defaults (a text console handler, mail_admins) are replaced: its records go
    # through the root handler. django.server/django.request are silenced by T-PLT-13.
    assert logging.getLogger("django").handlers == []
    for name in [None, *logging.root.manager.loggerDict]:
        for handler in own_handlers(logging.getLogger(name)):
            assert not isinstance(handler, logging.FileHandler | AdminEmailHandler), name


@pytest.fixture
def warning_level() -> Iterator[None]:
    configure_logging(logging_config("WARNING"))
    yield
    configure_logging(settings.LOGGING)


def test_RN_PLT_05_log_level_filters_both_kinds_of_logger(
    warning_level: None, stdout_log: StdoutLog
) -> None:
    get_logger("apps.demo").info("demo.hidden")
    logging.getLogger("thirdparty.lib").info("demo.hidden_stdlib")
    get_logger("apps.demo").warning("demo.shown")
    logging.getLogger("thirdparty.lib").warning("demo.shown_stdlib")
    messages = [event["message"] for event in stdout_log.read().events]
    assert messages == ["demo.shown", "demo.shown_stdlib"]


def test_RN_PLT_05_log_level_defaults_to_info_and_is_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert PlatformEnv().LOG_LEVEL == "INFO"
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert PlatformEnv().LOG_LEVEL == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "chatty-sentinel")
    with pytest.raises(ImproperlyConfigured) as error:
        load_env(PlatformEnv)
    assert "LOG_LEVEL" in str(error.value)
    assert "chatty-sentinel" not in str(error.value)


def redis_caches_with_password() -> dict[str, dict[str, Any]]:
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL_WITH_PASSWORD,
        }
    }


def test_C_06_error_report_never_shows_the_redis_password(settings: SettingsWrapper) -> None:
    # The debug page (DEBUG=true, dev only) and any error report render the settings and
    # request.META (runserver copies the process environment into it): N-9 of the T-PLT-08 review.
    settings.CACHES = redis_caches_with_password()
    request = RequestFactory().get("/", REDIS_URL=REDIS_URL_WITH_PASSWORD)
    try:
        raise RuntimeError("demo")
    except RuntimeError:
        reporter = ExceptionReporter(request, *sys.exc_info())
        report = reporter.get_traceback_text() + reporter.get_traceback_html()
    assert REDIS_HOST not in report
    assert SENTINEL not in report


@pytest.mark.urls("tests.api.urls_test")
def test_C_06_error_log_never_carries_the_settings(
    settings: SettingsWrapper, stdout_log: StdoutLog
) -> None:
    settings.CACHES = redis_caches_with_password()
    response = Client(raise_request_exception=False).get("/test/error")
    assert response.status_code == 500
    log = stdout_log.read()
    # The access log (T-PLT-13) carries the failure (its type); django.request is silenced.
    (access,) = log.find(ACCESS_EVENT)
    assert (access["status"], access["exception_type"]) == (500, "RuntimeError")
    assert SENTINEL not in log.out + log.err
