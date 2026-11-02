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
from unittest import mock

from django.conf import settings

from apps.common.logging import get_logger
from apps.common.logging.setup import StdoutHandler
from config import celery_app
from tests.logging.conftest import CapturedLog, StdoutLog

# What args, kwargs, a return value or an exception message may carry. Joined at runtime.
SENTINEL = "celery-" + "sentinel-9b4e"


def assert_no_sentinel(log: CapturedLog) -> None:
    assert SENTINEL not in log.out
    assert SENTINEL not in log.err


def test_AC_PLT_11_celery_trace_logger_is_silenced(stdout_log: StdoutLog) -> None:
    logging.getLogger("celery.app.trace").error("Task x raised unexpected: %r", SENTINEL)
    log = stdout_log.read()
    assert log.out == ""
    assert_no_sentinel(log)


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
