"""RF-IDA-09 (RN-IDA-17, T-IDA-11): the ``audit`` channel keeps INFO whatever ``LOG_LEVEL`` says.

``LogAuditPort`` writes each event at INFO. With the root at WARNING (or ERROR) a plain INFO event
is dropped, an audit one still goes out, once: the logger has no handler of its own.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.conf import settings

from apps.common.logging import get_logger
from apps.common.logging.setup import configure_logging, logging_config
from tests.logging.conftest import StdoutLog


@pytest.fixture(params=["WARNING", "ERROR"])
def quiet_level(request: pytest.FixtureRequest) -> Iterator[None]:
    configure_logging(logging_config(request.param))
    yield
    configure_logging(settings.LOGGING)


def test_RF_IDA_09_audit_info_survives_a_quiet_log_level(
    quiet_level: None, stdout_log: StdoutLog
) -> None:
    get_logger("audit").info("audit.event", action="identity.logout")
    get_logger("apps.demo").info("demo.info_dropped")
    log = stdout_log.read()
    assert [event["message"] for event in log.events] == ["audit.event"]
    [event] = log.events
    assert (event["component"], event["level"], event["action"]) == (
        "audit",
        "info",
        "identity.logout",
    )
    assert log.err == ""


def test_RF_IDA_09_audit_events_are_not_duplicated_at_debug(stdout_log: StdoutLog) -> None:
    configure_logging(logging_config("DEBUG"))
    try:
        get_logger("audit").info("audit.event")
        log = stdout_log.read()
    finally:
        configure_logging(settings.LOGGING)
    assert [event["message"] for event in log.events] == ["audit.event"]
