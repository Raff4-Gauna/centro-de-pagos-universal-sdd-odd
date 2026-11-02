"""Celery records that would log a message body, kept out (C-06; T-PLT-17 review B-1).

When the worker will not run a message, Celery logs its whole body (the task args and kwargs, via
``dump_body``) or ``req.info(safe=True)`` (``argsrepr``/``kwargsrepr``): unregistered, invalid,
unknown-format and undecodable messages in ``celery.worker.consumer.consumer``, an ETA it cannot
convert in ``celery.worker.strategy``. ``CeleryMessageBodyFilter`` sits on those two loggers
(``setup.py``) and works by allowlist, so a message Celery adds or rewords fails safe:

- ``UNKNOWN_TASK_ERROR``, ``INVALID_TASK_ERROR`` and ``UNKNOWN_FORMAT`` are dropped: Celery also
  sends ``task_unknown``/``task_rejected``, and ``celery_signals.py`` logs ``celery.task.rejected``
  from there (reason, task name and id).
- Known safe templates pass untouched, args included: ``CONNECTION_ERROR`` (``consumer: Cannot
  connect to ...``, whose URL comes without its password), ``CONNECTION_RETRY`` and
  ``LOG_RECEIVED`` (``Task name[id] received``: its args carry ``argsrepr``, but the template
  renders only the name and id).
- Any other record loses its args and traceback (only ``error_type`` stays). If it was about a
  task message (``MESSAGE_DECODE_ERROR``, or args holding ``bytes`` or a dict with ``args`` or
  ``kwargs``, like the ETA one) it becomes ``celery.task.rejected`` with the task name and id when
  known; otherwise it keeps its bare template as the message.

Celery's templates are read at first use (they are not in celery-types' stubs); one that is gone
is skipped, and its records take the safe path. The filter never raises inside ``Logger.filter``.
"""

from __future__ import annotations

import functools
import importlib
import logging
from collections.abc import Mapping
from typing import Any

REJECTED_EVENT = "celery.task.rejected"
CONSUMER_LOGGER = "celery.worker.consumer.consumer"
STRATEGY_LOGGER = "celery.worker.strategy"
FILTERED_LOGGERS = (CONSUMER_LOGGER, STRATEGY_LOGGER)
_SIGNALLED = ("UNKNOWN_TASK_ERROR", "INVALID_TASK_ERROR", "UNKNOWN_FORMAT")
_SAFE = (
    ("celery.worker.consumer.consumer", "CONNECTION_ERROR"),
    ("celery.worker.consumer.consumer", "CONNECTION_RETRY"),
    ("celery.app.trace", "LOG_RECEIVED"),
)
_BODY_KEYS = frozenset({"args", "kwargs", "argsrepr", "kwargsrepr", "body"})


def _template(module: str, name: str) -> str | None:
    try:
        value = getattr(importlib.import_module(module), name, None)
    except Exception:  # Celery moved or renamed it: its records take the safe path
        return None
    return value if isinstance(value, str) else None


@functools.cache
def _templates() -> tuple[frozenset[str], frozenset[str], str | None]:
    """(dropped, passed as they are, the decode-error template) of the installed Celery."""
    signalled = {_template(CONSUMER_LOGGER, name) for name in _SIGNALLED}
    safe = {_template(module, name) for module, name in _SAFE}
    return (
        frozenset(t for t in signalled if t),
        frozenset(t for t in safe if t),
        _template(CONSUMER_LOGGER, "MESSAGE_DECODE_ERROR"),
    )


def _task_info(values: tuple[Any, ...]) -> dict[str, Any] | None:
    """The first dict that describes a task message (has args/kwargs/body keys), if any."""
    for value in values:
        if isinstance(value, Mapping) and _BODY_KEYS & set(value):
            return dict(value)
    return None


def _strip(record: logging.LogRecord) -> None:
    """No args, no traceback: only the type of the exception, if there was one."""
    if record.exc_info and record.exc_info[1] is not None:
        record.error_type = type(record.exc_info[1]).__name__
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None


def _sanitize(record: logging.LogRecord, decode_error: str | None) -> None:
    args = record.args
    values: tuple[Any, ...] = (args,) if isinstance(args, Mapping) else tuple(args or ())
    info = _task_info(values)
    is_body = info is not None or any(isinstance(v, bytes | bytearray) for v in values)
    is_decode = record.msg == decode_error
    _strip(record)
    if not (is_body or is_decode):
        return  # an unknown template: kept, bare
    record.reason = "undecodable" if is_decode else "message_not_run"
    if record.name == STRATEGY_LOGGER and info is not None:
        record.reason = "invalid_eta"  # the only such record of the strategy today
    record.msg = REJECTED_EVENT
    for field, key in (("task_id", "id"), ("task_name", "name")):
        if info is not None and isinstance(info.get(key), str):
            setattr(record, field, info[key])


class CeleryMessageBodyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            signalled, safe, decode_error = _templates()
            if record.msg in signalled:
                return False
            if record.msg not in safe:
                _sanitize(record, decode_error)
        except Exception:  # never fail the caller's log call; fail closed on the content
            record.args, record.exc_info, record.exc_text = (), None, None
            record.msg = REJECTED_EVENT
        return True
