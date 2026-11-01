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
access log (``middleware/access_log.py``) reports the same requests with the route template.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Any, TextIO

import structlog
from structlog.typing import Processor

from apps.common.logging.processors import add_component, add_record_extras, redact_event

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
SILENCED_LOGGERS = ("django.request", "django.security.csrf", "django.server")


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
            structlog.processors.JSONRenderer(),
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
        },
    }


def configure_logging(config: dict[str, Any]) -> None:
    """Apply ``config`` (``logging_config(...)``) and send structlog through the same handler."""
    logging.config.dictConfig(config)
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
