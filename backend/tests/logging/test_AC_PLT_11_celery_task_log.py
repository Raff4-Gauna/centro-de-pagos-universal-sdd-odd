"""AC-PLT-11 (RN-PLT-05, RN-PLT-07, RNF-PLT-03, Q-056): the log of a Celery task (T-PLT-17).

A request that enqueues a task passes its ``request_id`` as a message header
(``before_task_publish``); the worker binds it with the ``task_id`` and the task name
(``task_prerun``), so every event the task logs carries them, and the task ends with one
``celery.task`` event: ``result`` (the final state) and ``duration_ms``, never the args, kwargs,
return value nor the exception message (C-06). An invalid header is replaced by a new UUIDv4, as
``X-Request-ID`` is. ``celery.app.trace`` is silenced: its messages carry ``repr(exception)``, the
return value and, in some paths, the args.

Most tests run the task in-process with ``Task.apply`` (same signals, no broker) or publish to
kombu's in-memory transport. The ``integration`` ones run a real worker thread (``start_worker``)
against the Redis of ``REDIS_URL``: what ``celery -A config worker`` does with a message, minus the
process.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
from celery.contrib.testing.worker import start_worker
from celery.signals import after_task_publish, task_postrun
from django.conf import settings
from django.test import Client

from apps.common.logging import context, get_logger
from apps.common.logging.setup import StdoutHandler
from apps.common.middleware.request_id import REQUEST_ID_HEADER
from config import celery_app
from tests.logging.conftest import CapturedLog, StdoutLog

VALID = "3f2b8c1e-9d4a-4b7e-8f21-6c0d5e9a7b13"
TASK_EVENT = "celery.task"
INNER_EVENT = "test.inside_task"
DIAGNOSTIC_URL = "/api/dev/diagnostic-task/"
# What args, kwargs, a return value or an exception message may carry. Joined at runtime.
SENTINEL = "celery-" + "sentinel-9b4e"
# The only fields of the end-of-task event besides the shared ones and the exception description.
TASK_FIELDS = {"timestamp", "level", "component", "message", "request_id", "task_id", "task_name"}
FAILURE_FIELDS = {"exception_type", "exception_chain", "exception_frames", "exception_chain_frames"}


@celery_app.task(name="tests.echo")
def echo(secret: str, *, token: str) -> str:
    get_logger("tests.celery").info(INNER_EVENT)
    return f"{secret}:{token}"


@celery_app.task(name="tests.boom")
def boom(secret: str, *, token: str) -> None:
    get_logger("tests.celery").info(INNER_EVENT)
    # Plain text, no "key=value" shape: the redaction would not catch it, only the silencing does.
    raise RuntimeError(f"failed for {secret} and {token}")


def task_event(log: CapturedLog) -> dict[str, Any]:
    (event,) = log.find(TASK_EVENT)
    return event


def assert_no_sentinel(log: CapturedLog) -> None:
    assert SENTINEL not in log.out
    assert SENTINEL not in log.err


# --- in-process: Task.apply runs the task through the same trace and signals as a worker ---


def test_AC_PLT_11_task_log_has_duration_ms_and_result_without_args(stdout_log: StdoutLog) -> None:
    result = echo.apply(args=(SENTINEL,), kwargs={"token": SENTINEL}, headers={"request_id": VALID})
    assert result.get() == f"{SENTINEL}:{SENTINEL}"
    log = stdout_log.read()
    event = task_event(log)
    assert set(event) == TASK_FIELDS | {"result", "duration_ms"}
    assert (event["level"], event["result"]) == ("info", "SUCCESS")
    assert isinstance(event["duration_ms"], float)
    assert event["duration_ms"] >= 0
    assert (event["task_id"], event["task_name"]) == (result.id, "tests.echo")
    assert event["request_id"] == VALID
    (inner,) = log.find(INNER_EVENT)
    assert (inner["task_id"], inner["request_id"]) == (result.id, VALID)
    assert_no_sentinel(log)


def test_AC_PLT_11_failed_task_log_has_exception_type_only(stdout_log: StdoutLog) -> None:
    result = boom.apply(args=(SENTINEL,), kwargs={"token": SENTINEL}, headers={"request_id": VALID})
    assert result.state == "FAILURE"
    log = stdout_log.read()
    event = task_event(log)
    assert set(event) == TASK_FIELDS | {"result", "duration_ms"} | FAILURE_FIELDS
    assert (event["level"], event["result"]) == ("error", "FAILURE")
    assert event["exception_type"] == "RuntimeError"
    assert any("in boom" in frame for frame in event["exception_frames"])
    # Nothing else: celery.app.trace ("raised unexpected: RuntimeError(...)") is silenced.
    assert {e["message"] for e in log.events} == {INNER_EVENT, TASK_EVENT}
    assert_no_sentinel(log)


@pytest.mark.parametrize(
    "header",
    ["not-a-uuid", VALID + "\n", str(uuid.uuid1()), '","level":"error","message":"forged', 42],
)
def test_AC_PLT_11_invalid_request_id_in_task_header_is_replaced(
    stdout_log: StdoutLog, header: object
) -> None:
    headers: dict[str, Any] = {"request_id": header}
    echo.apply(args=("a",), kwargs={"token": "b"}, headers=headers)
    log = stdout_log.read()
    request_id = task_event(log)["request_id"]
    assert request_id != header
    assert str(uuid.UUID(request_id)) == request_id
    assert uuid.UUID(request_id).version == 4
    assert log.find(INNER_EVENT)[0]["request_id"] == request_id
    assert "forged" not in log.out


def test_AC_PLT_11_task_without_origin_request_gets_a_new_request_id(stdout_log: StdoutLog) -> None:
    echo.apply(args=("a",), kwargs={"token": "b"})
    request_id = task_event(stdout_log.read())["request_id"]
    assert uuid.UUID(request_id).version == 4


def test_AC_PLT_11_task_context_does_not_outlive_the_task(stdout_log: StdoutLog) -> None:
    context.bind_request(VALID)
    echo.apply(args=("a",), kwargs={"token": "b"})
    assert context.current_request_id() is None
    get_logger("tests.after_task").info("test.after_task")
    (event,) = stdout_log.read().find("test.after_task")
    assert "task_id" not in event
    assert "request_id" not in event


def test_AC_PLT_11_celery_trace_logger_is_silenced(stdout_log: StdoutLog) -> None:
    logging.getLogger("celery.app.trace").error("Task x raised unexpected: %r", SENTINEL)
    log = stdout_log.read()
    assert log.out == ""
    assert_no_sentinel(log)


# --- publishing: the request_id travels as a message header ---


def use_broker(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """Point the app at ``url``, dropping the pooled connections to the previous broker."""
    monkeypatch.setattr(celery_app.conf, "broker_url", url)
    drop_broker_connections()


def drop_broker_connections() -> None:
    # The app's connection pool (close) and the AMQP helper with its producer pool, rebuilt from
    # the current broker_url on next use: Celery's own reset after a fork does the same.
    celery_app.close()
    celery_app.__dict__.pop("amqp", None)


@pytest.fixture
def memory_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """kombu's in-memory transport; yields the headers of every message published meanwhile."""
    published: list[dict[str, Any]] = []

    def keep(sender: object = None, headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
        published.append(dict(headers or {}))

    use_broker(monkeypatch, "memory://")
    after_task_publish.connect(keep, weak=False)
    try:
        yield published
    finally:
        after_task_publish.disconnect(keep)
        celery_app.control.purge()  # the in-memory queue outlives the connection
        drop_broker_connections()


def test_AC_PLT_11_diagnostic_endpoint_returns_202_with_task_id_and_request_id(
    client: Client, memory_broker: list[dict[str, Any]]
) -> None:
    response = client.post(DIAGNOSTIC_URL, headers={REQUEST_ID_HEADER: VALID})
    assert response.status_code == 202
    body = response.json()
    assert body["request_id"] == VALID
    assert uuid.UUID(body["task_id"]).version == 4
    assert response[REQUEST_ID_HEADER] == VALID
    (headers,) = memory_broker
    assert (headers["id"], headers["task"]) == (body["task_id"], "common.diagnostic_ping")
    assert headers["request_id"] == VALID


def test_AC_PLT_11_publish_outside_a_request_adds_no_header(
    memory_broker: list[dict[str, Any]],
) -> None:
    echo.apply_async(args=("a",), kwargs={"token": "b"})
    (headers,) = memory_broker
    assert "request_id" not in headers


# --- configuration: Celery uses the platform's logging, never its own ---


def test_RN_PLT_05_celery_settings_keep_root_logger_and_retry_broker() -> None:
    assert celery_app.conf.worker_hijack_root_logger is False
    assert celery_app.conf.broker_connection_retry_on_startup is True
    assert celery_app.conf.broker_connection_max_retries is None


def test_RN_PLT_05_celery_logging_setup_keeps_the_json_handler(stdout_log: StdoutLog) -> None:
    with mock.patch.dict(os.environ):  # Celery's setup exports _MP_FORK_* variables
        # What celery.contrib.testing.worker.setup_app_for_worker does before each worker start.
        type(celery_app.log)._setup = False  # type: ignore[attr-defined]
        celery_app.log.setup(loglevel=logging.ERROR)
    root = logging.getLogger()
    assert [type(handler) for handler in root.handlers] == [StdoutHandler]
    assert root.level == logging.getLevelName(settings.LOGGING["root"]["level"])
    get_logger("tests.celery").info("test.after_setup")
    assert stdout_log.read().find("test.after_setup")


# --- integration: a real worker thread consuming from Redis ---


@pytest.fixture
def redis_worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[threading.Event]:
    """A worker on the Redis of ``REDIS_URL``; yields an event set when a task finishes."""
    done = threading.Event()

    def finished(**kwargs: Any) -> None:
        done.set()

    use_broker(monkeypatch, os.environ["REDIS_URL"])
    celery_app.control.purge()
    task_postrun.connect(finished, weak=False)
    try:
        with mock.patch.dict(os.environ), start_worker(celery_app, perform_ping_check=False):
            yield done
    finally:
        task_postrun.disconnect(finished)
        drop_broker_connections()


def captured(capfd: pytest.CaptureFixture[str]) -> CapturedLog:
    out, err = capfd.readouterr()
    return CapturedLog(out=out, err=err)


@pytest.mark.integration
def test_AC_PLT_11_task_log_is_json_with_task_id_and_origin_request_id(
    client: Client, redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    response = client.post(DIAGNOSTIC_URL, headers={REQUEST_ID_HEADER: VALID})
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    assert redis_worker.wait(timeout=30)
    log = captured(capfd)  # every line must parse as one JSON object
    (ping,) = log.find("diagnostic.ping")
    event = task_event(log)
    for item in (ping, event):
        assert (item["task_id"], item["request_id"]) == (task_id, VALID)
        assert item["task_name"] == "common.diagnostic_ping"
    assert (event["result"], event["level"]) == ("SUCCESS", "info")
    assert event["duration_ms"] >= 0
    assert "pong" not in log.out


@pytest.mark.integration
def test_AC_PLT_11_failed_task_on_worker_logs_no_args_nor_exception_message(
    redis_worker: threading.Event, capfd: pytest.CaptureFixture[str]
) -> None:
    context.bind_request(VALID)
    sent = boom.apply_async(args=(SENTINEL,), kwargs={"token": SENTINEL})
    context.clear()
    assert redis_worker.wait(timeout=30)
    log = captured(capfd)
    event = task_event(log)
    assert set(event) == TASK_FIELDS | {"result", "duration_ms"} | FAILURE_FIELDS
    assert (event["task_id"], event["request_id"], event["result"]) == (sent.id, VALID, "FAILURE")
    assert event["exception_type"] == "RuntimeError"
    assert_no_sentinel(log)
