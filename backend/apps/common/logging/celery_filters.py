"""Celery records that would log a message body, kept out (C-06; T-PLT-17 review B-1).

When the worker will not run a message, Celery logs its whole body (the task args and kwargs, via
``dump_body``) or ``req.info(safe=True)`` (``argsrepr``/``kwargsrepr``):

- ``celery.worker.consumer.consumer``: ``UNKNOWN_TASK_ERROR`` (unregistered task),
  ``INVALID_TASK_ERROR`` (e.g. a malformed ETA header), ``UNKNOWN_FORMAT`` (no task header) and
  ``MESSAGE_DECODE_ERROR`` (a body that does not decode);
- ``celery.worker.strategy``: ``"Couldn't convert ETA ..."``.

``CeleryMessageBodyFilter`` sits on those two loggers (``setup.py``). The first three records are
dropped: Celery also sends ``task_unknown``/``task_rejected`` for them, and ``celery_signals.py``
logs ``celery.task.rejected`` from there, with the reason and the task name and id only. The other
two send no signal: the record is rewritten in place into that same event (reason, and the task
name and id for the ETA one), with no args and no traceback (an exception message may quote the
body). Any other record of those loggers (``consumer: Cannot connect to ...``, whose URL comes
without its password) passes untouched.

The consumer messages are compared with Celery's own constants, read at first use (they are not in
celery-types' stubs, and importing the consumer module costs nothing until a worker logs).
"""

from __future__ import annotations

import functools
import importlib
import logging

REJECTED_EVENT = "celery.task.rejected"
CONSUMER_LOGGER = "celery.worker.consumer.consumer"
STRATEGY_LOGGER = "celery.worker.strategy"
FILTERED_LOGGERS = (CONSUMER_LOGGER, STRATEGY_LOGGER)
# celery/worker/strategy.py logs this one as a literal, with no constant to import.
_INVALID_ETA_PREFIX = "Couldn't convert ETA"


@functools.cache
def _consumer_messages() -> tuple[frozenset[str], str]:
    """(messages reported by a signal, the decode-error message) of Celery's consumer."""
    consumer = importlib.import_module("celery.worker.consumer.consumer")
    signalled = frozenset(
        {consumer.UNKNOWN_TASK_ERROR, consumer.INVALID_TASK_ERROR, consumer.UNKNOWN_FORMAT}
    )
    return signalled, str(consumer.MESSAGE_DECODE_ERROR)


def _rewrite(record: logging.LogRecord, reason: str, info: object = None) -> None:
    record.msg = REJECTED_EVENT
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    record.reason = reason
    if isinstance(info, dict):
        for field, key in (("task_id", "id"), ("task_name", "name")):
            if isinstance(info.get(key), str):
                setattr(record, field, info[key])


class CeleryMessageBodyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.msg
        if not isinstance(message, str):
            return True
        signalled, decode_error = _consumer_messages()
        if message in signalled:
            return False
        if message == decode_error:
            _rewrite(record, "undecodable")
        elif record.name == STRATEGY_LOGGER and message.startswith(_INVALID_ETA_PREFIX):
            args = record.args
            info = args[2] if isinstance(args, tuple) and len(args) > 2 else None
            _rewrite(record, "invalid_eta", info)
        return True
