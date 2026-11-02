"""The single logging configuration (design.md §3.2.3, RN-PLT-05, RF-PLT-05, Q-034, C-16).

``logging_config(level)`` is the ``dictConfig`` of every process: Django (``LOGGING``, built by each
settings module from ``LOG_LEVEL``), gunicorn (``logconfig_dict``, T-PLT-25) and Celery (T-PLT-17).
``configure_logging`` is Django's ``LOGGING_CONFIG``: it applies that dict and configures structlog.

One handler, on the root logger: ``StdoutHandler``, one JSON object per line on stdout, no file.
structlog loggers and stdlib loggers (Django, libraries) share the processors and the renderer:
``merge_contextvars`` -> ``level`` -> ``component`` -> ``timestamp`` (ISO-8601 UTC) ->
``format_exc_info`` -> redaction (T-PLT-14, AC-PLT-08) -> ``message`` -> ``JSONRenderer``. The
redaction runs after the traceback is rendered, so the traceback text is scrubbed too (design.md
§3.2.3 lists it before ``format_exc_info``). Tracebacks and line breaks are escaped inside the JSON
string, so an event never spans two lines.

Django applies its ``DEFAULT_LOGGING`` before this one; here the ``django`` logger loses those
handlers (a text console handler and ``mail_admins``, whose e-mail embeds the error report with the
settings, C-06) and propagates to the root handler. ``django.request``, ``django.security.csrf`` and
``django.server`` are silenced (T-PLT-13): they log the raw path (``"Not Found: /path"``), and the
access log (``middleware/access_log.py``) reports the same requests with the route template. So is
``celery.app.trace`` (T-PLT-17): its messages carry the exception ``repr`` and task values; the
``celery.task`` event (``celery_signals.py``) replaces it. ``celery.worker.consumer.consumer`` and
``celery.worker.strategy`` keep logging, minus the records that dump a message body
(``celery_filters.py``, T-PLT-17 review B-1).
``django.db.backends`` is held at INFO (T-PLT-14): with ``DEBUG`` on it logs every query with its
parameters at DEBUG; its errors still propagate. ``django.security.DisallowedHost`` (an invalid
``Host`` header, what scanners send) goes out as one WARNING line without the traceback instead
of an ERROR with it (T-PLT-13 review N-a); the access log still reports the 400.

An event that cannot be rendered (bad ``%`` args, a failing formatter) becomes one fixed JSON line,
``log.render_failed``, instead of logging's text traceback on stderr with the message and its args
(``StdoutHandler.handleError``, T-PLT-12 review N-2). ``NaN``/``Infinity`` never reach the
renderer as floats (redaction) and the renderer rejects them anyway (``allow_nan=False``, N-4).
Python warnings are captured (``logging.captureWarnings``, T-PLT-14 review N-1): they become
``py.warnings`` events, JSON on stdout and redacted, instead of plain text on stderr.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

import structlog
from structlog.typing import Processor

from apps.common.logging import context
from apps.common.logging.celery_filters import FILTERED_LOGGERS
from apps.common.logging.processors import add_component, add_record_extras, redact_event

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# celery.app.trace (T-PLT-17): "Task x[id] raised unexpected: <repr(exc)>", the return value and,
# on some paths, the args; apps/common/celery_signals.py logs each task without them.
SILENCED_LOGGERS = ("django.request", "django.security.csrf", "django.server", "celery.app.trace")
# DEBUG records of these carry SQL with its parameters (C-06); INFO and up still go out. A logger
# level holds for its children too: this also cuts django.db.backends.schema, which logs each DDL
# statement (migrations) with its parameters at DEBUG.
SQL_LOGGERS = ("django.db.backends",)
# Loggers whose records are noise from outside, not faults: WARNING, no traceback (N-a).
DOWNGRADED_LOGGERS = ("django.security.DisallowedHost",)
RENDER_FAILED_EVENT = "log.render_failed"


class StdoutHandler(logging.StreamHandler[TextIO]):
    """Writes each record to the *current* ``sys.stdout``, looked up on every emit.

    Not bound at configuration time, so a replaced stdout (pytest's capture, a re-opened stream)
    still gets the lines; and it cannot be pointed at anything else.
    """

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self) -> TextIO:
        return sys.stdout

    @stream.setter
    def stream(self, value: TextIO) -> None:
        """Ignored: the target is always the current stdout."""

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 - logging's API
        """One fixed JSON line for a record that failed to render; never raises.

        Only fields known to be safe: the logger name and level of the record and the type of
        the error, never ``record.msg``, its args nor the error message (they may carry
        anything, C-06). Replaces logging's default, a text traceback on stderr.
        """
        error = sys.exc_info()[1]
        event = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": "error",
            "component": __name__,
            "message": RENDER_FAILED_EVENT,
            "failed_component": str(record.name),
            "failed_level": str(record.levelname).lower(),
            "error_type": type(error).__name__ if error is not None else "unknown",
        }
        request_id = context.current_request_id()
        if request_id is not None:
            event["request_id"] = request_id
        try:
            self.stream.write(json.dumps(event) + self.terminator)
            self.flush()
        except Exception:  # noqa: S110 - stdout itself failed: nowhere left to report it
            pass


class WarningWithoutTraceback(logging.Filter):
    """Turns a record above WARNING into a WARNING and drops its traceback and stack.

    A logger filter: it runs after the logger's level check, which passed for the original level,
    so it checks again for WARNING (``LOG_LEVEL=ERROR`` drops the record).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno > logging.WARNING:
            record.levelno = logging.WARNING
            record.levelname = logging.getLevelName(logging.WARNING)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return logging.getLogger(record.name).isEnabledFor(record.levelno)


def _shared_processors() -> list[Processor]:
    """What both kinds of event get first: context, level, component and UTC timestamp."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        add_component,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    ]


def json_formatter() -> structlog.stdlib.ProcessorFormatter:
    """The formatter of ``StdoutHandler``: renders structlog and stdlib records alike."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*_shared_processors(), add_record_extras],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            redact_event,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(allow_nan=False),
        ],
    )


def logging_config(level: str) -> dict[str, Any]:
    """The ``dictConfig`` dict with the root logger at ``level`` (one of ``LOG_LEVELS``)."""
    if level not in LOG_LEVELS:
        raise ValueError(f"unknown log level: {level!r}")
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": f"{__name__}.json_formatter"}},
        "filters": {
            "warning_without_traceback": {"()": f"{__name__}.WarningWithoutTraceback"},
            # Celery records that would dump a message body (C-06, T-PLT-17 review B-1).
            "celery_message_body": {
                "()": "apps.common.logging.celery_filters.CeleryMessageBodyFilter"
            },
        },
        "handlers": {
            "stdout": {"()": f"{__name__}.StdoutHandler", "formatter": "json"},
            # A real handler, not just propagate=False: with none, logging's lastResort would
            # still write WARNING+ to stderr.
            "silenced": {"class": "logging.NullHandler"},
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            # Drops DEFAULT_LOGGING's console and mail_admins handlers; inherits the root level.
            "django": {"handlers": [], "level": "NOTSET", "propagate": True},
            # They log the raw path (RN-PLT-06); the access log replaces them.
            **{name: {"handlers": ["silenced"], "propagate": False} for name in SILENCED_LOGGERS},
            # A level of their own: the root's DEBUG (LOG_LEVEL) must not let SQL through.
            **{name: {"handlers": [], "level": "INFO", "propagate": True} for name in SQL_LOGGERS},
            # Inherit the root level; the filter downgrades and re-checks it (N-a).
            **{
                name: {"handlers": [], "filters": ["warning_without_traceback"], "propagate": True}
                for name in DOWNGRADED_LOGGERS
            },
            # Their message-body dumps dropped or rewritten; everything else passes.
            **{
                name: {"handlers": [], "filters": ["celery_message_body"], "propagate": True}
                for name in FILTERED_LOGGERS
            },
        },
    }


def configure_logging(config: dict[str, Any]) -> None:
    """Apply ``config`` (``logging_config(...)``) and send structlog through the same handler."""
    logging.config.dictConfig(config)
    # warnings.warn(...) -> the "py.warnings" logger -> the same handler and redaction (N-1).
    logging.captureWarnings(True)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *_shared_processors(),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
