"""gunicorn settings (T-PLT-25, design.md §3.2.3, D-05).

``gunicorn -c config/gunicorn.conf.py config.wsgi``: the same server in dev and prod; dev adds
``--reload --reload-engine poll`` on the command line (Compose, the ``dev`` image).

Logging is the platform's (RN-PLT-05, C-16): ``logconfig_dict`` is ``logging_config(LOG_LEVEL)``
from ``apps/common/logging/setup.py``, the dict Django and Celery apply, plus the two gunicorn
loggers:

- ``gunicorn.error`` (start-up, signals, workers that die or fail to boot, tracebacks outside
  Django) loses gunicorn's text handler on stderr and propagates to the root ``StdoutHandler``:
  JSON on stdout, through the redaction (T-PLT-14 review). gunicorn creates it with
  ``propagate=False``; ``dictConfig`` drops the handlers of every logger it lists.
- ``gunicorn.access`` is silenced and ``accesslog`` is off: its line carries the raw path and query
  string (RN-PLT-06); the access log of the app (``middleware/access_log.py``) replaces it.

``on_starting`` applies the same dict through ``configure_logging`` (as Django does), which also
captures Python warnings and configures structlog in the master.

A worker's ``sys.stderr`` becomes log events too (``post_fork``): after logging a boot failure,
gunicorn prints the exception's message there raw (``print("%s" % e, file=sys.stderr)``), outside
the redaction; so does Python with an uncaught traceback. Each line goes out as a
``process.stderr`` event with the text in ``line``, JSON and redacted.

``LOG_LEVEL`` is read through ``config/settings/env.py``, the only reader of the environment
(AC-PLT-06): a missing or invalid variable stops gunicorn naming it, never showing its value
(AC-PLT-03). Not through ``django.conf.settings``: the master would load the settings module and
every worker forked by ``--reload`` would inherit it, so an edit to the settings would not reload.
"""

# The file name is gunicorn's convention, not an importable module.
# ruff: noqa: N999

from __future__ import annotations

import io
import logging
import sys
from typing import Any

from apps.common.logging.setup import configure_logging, logging_config
from config.settings.env import PlatformEnv, load_env

GUNICORN_LOGGERS: dict[str, dict[str, Any]] = {
    "gunicorn.error": {"handlers": [], "propagate": True},
    "gunicorn.access": {"handlers": ["silenced"], "propagate": False},
}
STDERR_LOGGER = "gunicorn.stderr"
STDERR_EVENT = "process.stderr"
# A line longer than this goes out in pieces instead of growing the buffer without bound; the
# redaction cuts each string at 8192 characters anyway.
STDERR_MAX_LINE = 8192


def gunicorn_logging(level: str) -> dict[str, Any]:
    """``logging_config(level)`` with the gunicorn loggers routed as described above."""
    config = logging_config(level)
    return {**config, "loggers": {**config["loggers"], **GUNICORN_LOGGERS}}


class StderrToLog(io.TextIOBase):
    """A text stream whose lines become ERROR ``process.stderr`` events of ``logger``."""

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__()
        self._logger = logger
        self._pending = ""
        self._emitting = False

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._pending += text
        *lines, self._pending = self._pending.split("\n")
        while len(self._pending) >= STDERR_MAX_LINE:
            lines.append(self._pending[:STDERR_MAX_LINE])
            self._pending = self._pending[STDERR_MAX_LINE:]
        for line in lines:
            self._emit(line)
        return len(text)

    def flush(self) -> None:
        line, self._pending = self._pending, ""
        self._emit(line)

    def _emit(self, line: str) -> None:
        # Re-entry (logging itself writing to stderr) would loop: such a line is dropped.
        if not line.strip() or self._emitting:
            return
        self._emitting = True
        try:
            self._logger.error(STDERR_EVENT, extra={"line": line})
        finally:
            self._emitting = False


_log_level = load_env(PlatformEnv).LOG_LEVEL

bind = "0.0.0.0:8000"  # inside the container; Compose publishes it on 127.0.0.1 only
workers = 2
# No runtime control socket (gunicornc, gunicorn >= 26): nothing uses it, and its default path is
# under $HOME, which the image's user does not have.
control_socket_disable = True
loglevel = _log_level.lower()
accesslog = None
logconfig_dict = gunicorn_logging(_log_level)


def on_starting(server: object) -> None:
    """In the master, before any worker: warnings and structlog as in Django (N-1)."""
    configure_logging(logconfig_dict)


def post_fork(server: object, worker: object) -> None:
    """In each worker, before it loads the app: stderr through the logging (see above)."""
    sys.stderr = StderrToLog(logging.getLogger(STDERR_LOGGER))
