"""RN-PLT-05 (T-PLT-13 review N-a, T-PLT-09): an invalid ``Host`` header is one WARNING line.

Django logs ``DisallowedHost`` on ``django.security.DisallowedHost`` as ERROR with the traceback;
in prod that is what every scanner hitting the IP sends. The logger keeps its message (it names the
host, which is how a wrong ``ALLOWED_HOSTS`` is found) but goes out as WARNING without
``exception``; with ``LOG_LEVEL=ERROR`` it is dropped. The access log still reports the 400.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper

from tests.logging.conftest import CapturedLog, StdoutLog

LOGGER = "django.security.DisallowedHost"


def bad_host_request(settings: SettingsWrapper, stdout_log: StdoutLog) -> CapturedLog:
    settings.ALLOWED_HOSTS = ["localhost"]
    response = Client().get("/healthz", HTTP_HOST="scanner.example")
    assert response.status_code == 400
    return stdout_log.read()


def test_RN_PLT_05_disallowed_host_is_a_warning_without_traceback(
    settings: SettingsWrapper, stdout_log: StdoutLog
) -> None:
    log = bad_host_request(settings, stdout_log)
    events = [event for event in log.events if event.get("component") == LOGGER]
    assert len(events) == 1
    event = events[0]
    assert event["level"] == "warning"
    assert "exception" not in event
    assert "Traceback" not in log.out
    assert event["message"].startswith("Invalid HTTP_HOST header: 'scanner.example'")
    assert [event["status"] for event in log.find("http.request")] == [400]
    assert log.err == ""


@pytest.fixture
def logger_at_error() -> Iterator[None]:
    logger = logging.getLogger(LOGGER)
    logger.setLevel(logging.ERROR)
    yield
    logger.setLevel(logging.NOTSET)


@pytest.mark.usefixtures("logger_at_error")
def test_RN_PLT_05_disallowed_host_respects_the_level(
    settings: SettingsWrapper, stdout_log: StdoutLog
) -> None:
    # Logged as ERROR, so the level check passes; once a WARNING, the level must still hold.
    log = bad_host_request(settings, stdout_log)
    assert [event for event in log.events if event.get("component") == LOGGER] == []
    assert [event["status"] for event in log.find("http.request")] == [400]


def test_RN_PLT_05_other_security_loggers_keep_their_level(stdout_log: StdoutLog) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("django.security.SuspiciousOperation").exception("bad")
    (event,) = stdout_log.read().events
    assert event["level"] == "error"
    assert "ValueError" in event["exception"]
