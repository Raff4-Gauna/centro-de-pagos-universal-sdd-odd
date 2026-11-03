"""AC-PLT-11, C-06 (T-PLT-17 review B-1): a message the worker will not run never logs its body.

Celery's consumer logs the whole message body (args and kwargs, ``dump_body``) of an unregistered
task (``UNKNOWN_TASK_ERROR``), an invalid one (``INVALID_TASK_ERROR``), one of an unknown format
(``UNKNOWN_FORMAT``) and one it cannot decode (``MESSAGE_DECODE_ERROR``); the strategy logs
``req.info(safe=True)`` (``argsrepr``/``kwargsrepr``) for an ETA it cannot convert. The filter of
``logging/celery_filters.py`` drops the first three, which ``celery_signals.py`` reports as
``celery.task.rejected`` (reason, task name and id) from ``task_unknown``/``task_rejected``, lets
an allowlist of safe templates through (``Cannot connect``, ``received``) and strips the args of
anything else, so a message Celery adds or rewords fails safe. The ETA case runs on a real worker:
if Celery changes that path, CI sees it.

The sentinel goes in a positional arg and under an innocuous kwarg key (``note``): the redaction
by key would not hide it, only the filter does.
"""

from __future__ import annotations

import importlib
import logging
import threading
import uuid
from typing import Any

import pytest

from apps.common.logging import celery_filters
from apps.common.logging.celery_filters import REJECTED_EVENT, STRATEGY_LOGGER
from config import celery_app
from tests.logging.conftest import CapturedLog, StdoutLog, captured

SENTINEL = "rejected-" + "sentinel-41c7"
BODY = [[SENTINEL], {"note": SENTINEL}, {"callbacks": None, "errbacks": None, "chain": None}]
REGISTERED = "common.diagnostic_ping"
# Not in celery-types' stubs: read at runtime, as the filter does.
_consumer = importlib.import_module("celery.worker.consumer.consumer")


def rejected_event(log: CapturedLog) -> dict[str, Any]:
    (event,) = log.find(REJECTED_EVENT)
    return event


def assert_no_sentinel(log: CapturedLog) -> None:
    assert SENTINEL not in log.out
    assert SENTINEL not in log.err


def publish_raw(headers: dict[str, Any]) -> None:
    """A message with exactly these headers and ``BODY``, on the default queue."""
    queue = celery_app.amqp.queues[celery_app.conf.task_default_queue]
    with celery_app.connection_for_write() as connection:
        connection.Producer(serializer="json").publish(
            BODY, routing_key=queue.routing_key, exchange=queue.exchange, declare=[queue],
            headers=headers,
        )  # fmt: skip


# --- integration: what a worker does with each kind of message ---


@pytest.mark.integration
def test_AC_PLT_11_unregistered_task_logs_name_and_id_without_args(
    redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    sent = celery_app.send_task("tests.not_registered", args=[SENTINEL], kwargs={"note": SENTINEL})
    assert redis_worker.wait(timeout=30)
    log = captured(capfd)
    event = rejected_event(log)
    assert (event["level"], event["reason"]) == ("error", "unknown_task")
    assert (event["task_name"], event["task_id"]) == ("tests.not_registered", sent.id)
    assert_no_sentinel(log)


@pytest.mark.integration
def test_AC_PLT_11_invalid_task_message_logs_name_and_id_without_args(
    redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    task_id = str(uuid.uuid4())
    publish_raw({"lang": "py", "task": REGISTERED, "id": task_id, "eta": "not-a-date"})
    assert redis_worker.wait(timeout=30)
    log = captured(capfd)
    event = rejected_event(log)
    assert (event["level"], event["reason"]) == ("error", "invalid_task")
    assert (event["task_name"], event["task_id"]) == (REGISTERED, task_id)
    assert event["error_type"] == "celery.exceptions.InvalidTaskError"
    assert_no_sentinel(log)


@pytest.mark.integration
def test_AC_PLT_11_unknown_format_message_logs_without_body(
    redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    publish_raw({"note": "no task header"})
    assert redis_worker.wait(timeout=30)
    log = captured(capfd)
    event = rejected_event(log)
    assert (event["level"], event["reason"]) == ("warning", "unknown_format")
    assert "task_name" not in event
    assert_no_sentinel(log)


class _RejectedSeen(logging.Handler):
    """Sets ``seen`` when the strategy logs a rejection (the ETA path sends no Celery signal)."""

    def __init__(self) -> None:
        super().__init__()
        self.seen = threading.Event()

    def emit(self, record: logging.LogRecord) -> None:
        if record.msg == REJECTED_EVENT:
            self.seen.set()


@pytest.mark.integration
def test_AC_PLT_11_unconvertible_eta_on_worker_logs_name_and_id_without_args(
    redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    handler = _RejectedSeen()
    logging.getLogger(STRATEGY_LOGGER).addHandler(handler)
    try:
        task_id = str(uuid.uuid4())
        # A valid ISO date that overflows once moved to the local time zone (year 10000).
        eta = "9999-12-31T23:59:59-12:00"
        publish_raw({"lang": "py", "task": REGISTERED, "id": task_id, "eta": eta, "utc": True})
        assert handler.seen.wait(timeout=30)
    finally:
        logging.getLogger(STRATEGY_LOGGER).removeHandler(handler)
    log = captured(capfd)
    event = rejected_event(log)
    assert (event["level"], event["reason"]) == ("error", "invalid_eta")
    assert (event["task_name"], event["task_id"]) == (REGISTERED, task_id)
    assert "exception" not in event
    assert_no_sentinel(log)


# --- the filter itself, record by record ---


def emit(logger_name: str, level: int, msg: str, *args: object) -> None:
    try:
        raise ValueError(SENTINEL)
    except ValueError:
        logging.getLogger(logger_name).log(level, msg, *args, exc_info=True)


@pytest.mark.parametrize("constant", ["UNKNOWN_TASK_ERROR", "INVALID_TASK_ERROR", "UNKNOWN_FORMAT"])
def test_AC_PLT_11_consumer_body_dumps_are_dropped(stdout_log: StdoutLog, constant: str) -> None:
    message = getattr(_consumer, constant)
    emit(_consumer.__name__, logging.ERROR, message, *([repr(BODY)] * message.count("%")))
    log = stdout_log.read()
    assert log.out == ""
    assert_no_sentinel(log)


def test_AC_PLT_11_undecodable_message_is_rewritten_without_body(stdout_log: StdoutLog) -> None:
    args = (ValueError(SENTINEL), "application/json", "utf-8", "{}", repr(BODY))
    emit(_consumer.__name__, logging.CRITICAL, _consumer.MESSAGE_DECODE_ERROR, *args)
    log = stdout_log.read()
    event = rejected_event(log)
    assert (event["level"], event["reason"]) == ("critical", "undecodable")
    assert "exception" not in event
    assert_no_sentinel(log)


def test_AC_PLT_11_invalid_eta_is_rewritten_with_name_and_id_only(stdout_log: StdoutLog) -> None:
    info = {"id": "t-1", "name": REGISTERED, "args": repr([SENTINEL]), "kwargs": repr({"note": 1})}
    eta_message = "Couldn't convert ETA %r to timestamp: %r. Task: %r"  # celery/worker/strategy.py
    emit("celery.worker.strategy", logging.ERROR, eta_message, "eta", OverflowError(SENTINEL), info)
    log = stdout_log.read()
    event = rejected_event(log)
    assert event["reason"] == "invalid_eta"
    assert (event["task_name"], event["task_id"]) == (REGISTERED, "t-1")
    assert_no_sentinel(log)


def test_AC_PLT_11_other_consumer_records_still_pass(stdout_log: StdoutLog) -> None:
    # "consumer: Cannot connect to redis://...": useful, and the URL comes without its password.
    logging.getLogger(_consumer.__name__).error(_consumer.CONNECTION_ERROR, "redis://h", "x", "")
    (line,) = stdout_log.read().events
    assert line["message"].startswith("consumer: Cannot connect to redis://h")


def test_AC_PLT_11_unknown_template_with_task_info_is_rewritten(stdout_log: StdoutLog) -> None:
    # A reworded message (a future Celery) with req.info(safe=True) as its argument.
    info = {"id": "t-2", "name": REGISTERED, "argsrepr": repr([SENTINEL]), "kwargs": {"note": 1}}
    emit(STRATEGY_LOGGER, logging.ERROR, "Could not convert ETA %r: %r. Task: %r", "e", 1, info)
    log = stdout_log.read()
    event = rejected_event(log)
    assert (event["task_name"], event["task_id"]) == (REGISTERED, "t-2")
    assert event["error_type"] == "ValueError"
    assert_no_sentinel(log)


def test_AC_PLT_11_unknown_template_with_bytes_is_rewritten(stdout_log: StdoutLog) -> None:
    emit(_consumer.__name__, logging.ERROR, "Some new dump: %r", SENTINEL.encode())
    log = stdout_log.read()
    assert rejected_event(log)["reason"] == "message_not_run"
    assert_no_sentinel(log)


def test_AC_PLT_11_unknown_template_keeps_only_its_text(stdout_log: StdoutLog) -> None:
    emit(_consumer.__name__, logging.WARNING, "Something new happened: %s", SENTINEL)
    log = stdout_log.read()
    (event,) = log.events
    assert event["message"] == "Something new happened: %s"
    assert_no_sentinel(log)


def test_AC_PLT_11_received_log_keeps_name_and_id(stdout_log: StdoutLog) -> None:
    trace = importlib.import_module("celery.app.trace")
    context = {"id": "t-3", "name": REGISTERED, "args": repr([SENTINEL]), "kwargs": "{}"}
    logging.getLogger(STRATEGY_LOGGER).info(trace.LOG_RECEIVED, context)
    (event,) = stdout_log.read().events
    assert event["message"] == f"Task {REGISTERED}[t-3] received"
    assert SENTINEL not in str(event)


@pytest.fixture
def templates_gone(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Celery without the constants the filter knows (renamed in a future version)."""
    monkeypatch.setattr(celery_filters, "_SIGNALLED", ("GONE_A", "GONE_B"))
    monkeypatch.setattr(celery_filters, "_SAFE", (("celery.not_a_module", "GONE"),))
    celery_filters._templates.cache_clear()
    yield
    celery_filters._templates.cache_clear()


def test_AC_PLT_11_missing_celery_constants_fall_back_safely(
    templates_gone: None, stdout_log: StdoutLog
) -> None:
    message = _consumer.UNKNOWN_TASK_ERROR
    emit(_consumer.__name__, logging.ERROR, message, *([repr(BODY)] * message.count("%")))
    log = stdout_log.read()
    (event,) = log.events
    assert event["message"] == message
    assert_no_sentinel(log)


def test_AC_PLT_11_filter_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, stdout_log: StdoutLog
) -> None:
    def broken() -> None:
        raise RuntimeError("templates unavailable")

    monkeypatch.setattr(celery_filters, "_templates", broken)
    emit(_consumer.__name__, logging.ERROR, "Dump: %s", SENTINEL)
    log = stdout_log.read()
    assert rejected_event(log)["level"] == "error"
    assert_no_sentinel(log)
