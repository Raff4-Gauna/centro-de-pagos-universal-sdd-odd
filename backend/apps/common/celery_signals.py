"""Celery signal handlers: ``request_id`` propagation and one log event per task (T-PLT-17).

design.md §3.2.3, AC-PLT-11, RN-PLT-05/07, RNF-PLT-03, Q-041. Connected by ``CommonConfig.ready``.

- ``before_task_publish``: the ``request_id`` bound in the publishing process (the request's, or the
  task's when a task enqueues another) goes into the message headers. Without one, no header.
- ``task_prerun``: the header is read from ``task.request`` (an attribute for worker messages, under
  ``headers`` for ``Task.apply``) and validated like ``X-Request-ID`` (``domain.request_id``): a
  missing or invalid value becomes a new UUIDv4. The context starts empty and gets ``request_id``,
  ``task_id`` and ``task_name``: every event the task logs carries them.
- ``task_failure``: keeps the description of the exception (``describe_exception``: types and
  frames of the exception and its causes) for the end-of-task event.
- ``task_postrun``: the ``celery.task`` event, ``result`` (the final state: ``SUCCESS``,
  ``FAILURE``, ``RETRY``...) and ``duration_ms``; ERROR for a failure. Then the context is cleared.

Never logged: args, kwargs, the return value, the exception message or its ``repr`` (they may carry
anything, C-06). Celery's own ``celery.app.trace`` logger, which logs them, is silenced
(``logging/setup.py``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import states
from celery.signals import before_task_publish, task_failure, task_postrun, task_prerun
from structlog.contextvars import bind_contextvars

from apps.common.domain.request_id import resolve_request_id
from apps.common.logging import context, get_logger
from apps.common.middleware.access_log import describe_exception

TASK_EVENT = "celery.task"
REQUEST_ID_HEADER = "request_id"

logger = get_logger(__name__)
# Per task id, from prerun to postrun (a worker runs several at once with threads or gevent).
_started: dict[str, float] = {}
_failures: dict[str, dict[str, Any]] = {}


@before_task_publish.connect(dispatch_uid="apps.common.celery_signals.publish")
def add_request_id_header(headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
    request_id = context.current_request_id()
    if headers is not None and request_id is not None:
        headers[REQUEST_ID_HEADER] = request_id


def _incoming_request_id(task: Any) -> str | None:
    request = getattr(task, "request", None)
    value = getattr(request, REQUEST_ID_HEADER, None)
    if value is None:
        headers = getattr(request, "headers", None)
        value = headers.get(REQUEST_ID_HEADER) if isinstance(headers, dict) else None
    return value if isinstance(value, str) else None


@task_prerun.connect(dispatch_uid="apps.common.celery_signals.prerun")
def bind_task_context(task_id: str | None = None, task: Any = None, **kwargs: Any) -> None:
    context.bind_request(resolve_request_id(_incoming_request_id(task)))
    bind_contextvars(task_id=str(task_id), task_name=str(getattr(task, "name", "")))
    _started[str(task_id)] = time.perf_counter()


@task_failure.connect(dispatch_uid="apps.common.celery_signals.failure")
def keep_task_failure(
    task_id: str | None = None, exception: BaseException | None = None, **kwargs: Any
) -> None:
    if exception is not None:
        _failures[str(task_id)] = describe_exception(exception)


@task_postrun.connect(dispatch_uid="apps.common.celery_signals.postrun")
def log_task_end(task_id: str | None = None, state: str | None = None, **kwargs: Any) -> None:
    try:
        started = _started.pop(str(task_id), None)
        failure = _failures.pop(str(task_id), {})
        duration_ms = None if started is None else round((time.perf_counter() - started) * 1000, 2)
        level = logging.ERROR if state == states.FAILURE else logging.INFO
        logger.log(level, TASK_EVENT, result=str(state), duration_ms=duration_ms, **failure)
    finally:
        context.clear()
