"""RN-PLT-05 (C-06, C-16, T-PLT-25): gunicorn logs through the platform's logging, never as text.

``config/gunicorn.conf.py`` passes ``logging_config(LOG_LEVEL)`` as ``logconfig_dict`` with
``gunicorn.error`` propagating to the root ``StdoutHandler`` and ``gunicorn.access`` silenced
(T-PLT-14 review: the error log went to stderr as text, outside the redaction), and turns each
worker's stderr into ``process.stderr`` events. The sentinel test starts a real gunicorn whose
worker fails to boot with a secret-shaped message: every stdout line is JSON, the traceback and
the message gunicorn prints raw on stderr are redacted, and stderr stays empty. gunicorn needs
``fcntl`` (POSIX only): on Windows that test is skipped; it runs in CI and in the dev image.
"""

from __future__ import annotations

import json
import logging
import runpy
import secrets
import subprocess
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from apps.common.domain.redaction import REDACTED
from apps.common.logging.setup import configure_logging, logging_config
from tests.conftest import BACKEND_DIR, django_env

CONF = BACKEND_DIR / "config" / "gunicorn.conf.py"
BOOT_FAILURE = "Exception in worker process"


class Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.on_emit: Callable[[], object] = lambda: None

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        self.on_emit()


def env_values(level: str) -> dict[str, str]:
    """Placeholder values the settings validation accepts; nothing connects to them."""
    return {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DATABASE_URL": "postgres://hub@localhost:5432/hub",
        "REDIS_URL": "redis://localhost:6379/0",
        "LOG_LEVEL": level,
    }


def load_conf(monkeypatch: pytest.MonkeyPatch, level: str) -> dict[str, Any]:
    for key, value in env_values(level).items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(CONF))


def test_RN_PLT_05_gunicorn_uses_platform_logconfig(monkeypatch: pytest.MonkeyPatch) -> None:
    conf = load_conf(monkeypatch, "WARNING")
    config = conf["logconfig_dict"]
    expected = logging_config("WARNING")
    # The platform dict untouched, plus the two gunicorn loggers.
    assert {key: value for key, value in config.items() if key != "loggers"} == {
        key: value for key, value in expected.items() if key != "loggers"
    }
    assert config["loggers"] == {
        **expected["loggers"],
        "gunicorn.error": {"handlers": [], "propagate": True},
        "gunicorn.access": {"handlers": ["silenced"], "propagate": False},
    }
    assert conf["loglevel"] == "warning"
    # The access line carries the raw path and query string (RN-PLT-06).
    assert conf["accesslog"] is None
    assert conf["control_socket_disable"] is True


def test_RN_PLT_05_gunicorn_on_starting_captures_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conf = load_conf(monkeypatch, "INFO")
    logging.captureWarnings(False)
    try:
        conf["on_starting"](object())
        # Python warnings become py.warnings events, JSON and redacted (T-PLT-14 review N-1).
        assert warnings.showwarning.__module__ == "logging"
        assert logging.getLogger("gunicorn.error").propagate is True
        assert logging.getLogger("gunicorn.error").handlers == []
        [silenced] = logging.getLogger("gunicorn.access").handlers
        assert isinstance(silenced, logging.NullHandler)
    finally:
        # Back to the logging of the test settings for the tests that follow.
        configure_logging(settings.LOGGING)


@pytest.fixture
def stderr_stream(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Collect]:
    """A ``StderrToLog`` of the conf on a private logger, and what that logger received."""
    conf = load_conf(monkeypatch, "INFO")
    logger = logging.getLogger("tests.gunicorn.stderr")
    collect = Collect()
    monkeypatch.setattr(logger, "handlers", [collect])
    monkeypatch.setattr(logger, "propagate", False)
    return conf["StderrToLog"](logger), collect


def test_RN_PLT_05_worker_stderr_lines_become_events(stderr_stream: tuple[Any, Collect]) -> None:
    stream, collect = stderr_stream
    # print() writes the text and the newline apart; blank lines are dropped.
    assert stream.write("first") == 5
    stream.write("\n\nsecond\nthird")
    assert [record.__dict__["line"] for record in collect.records] == ["first", "second"]
    stream.flush()
    lines = [record.__dict__["line"] for record in collect.records]
    assert lines == ["first", "second", "third"]
    assert {record.getMessage() for record in collect.records} == {"process.stderr"}
    assert {record.levelno for record in collect.records} == {logging.ERROR}
    assert stream.writable() is True


def test_RN_PLT_05_worker_stderr_long_line_is_split(stderr_stream: tuple[Any, Collect]) -> None:
    stream, collect = stderr_stream
    stream.write("x" * 8192 * 2 + "tail")
    assert [len(record.__dict__["line"]) for record in collect.records] == [8192, 8192]
    stream.flush()
    assert collect.records[-1].__dict__["line"] == "tail"


def test_RN_PLT_05_worker_stderr_reentry_is_dropped(stderr_stream: tuple[Any, Collect]) -> None:
    stream, collect = stderr_stream
    # A handler that writes to stderr while the stream is emitting must not loop.
    collect.on_emit = lambda: stream.write("from logging itself\n")
    stream.write("outer\n")
    assert [record.__dict__["line"] for record in collect.records] == ["outer"]


def test_RN_PLT_05_gunicorn_conf_invalid_env_names_variable_only() -> None:
    sentinel = "conf-sentinel-" + secrets.token_hex(8)
    values = {**env_values("INFO"), "LOG_LEVEL": sentinel}
    result = subprocess.run(  # noqa: S603 - fixed interpreter and argv
        [sys.executable, "-c", f"import runpy; runpy.run_path({str(CONF)!r})"],
        cwd=BACKEND_DIR,
        env=django_env("config.settings.test", values),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode != 0
    assert "LOG_LEVEL" in result.stderr
    assert sentinel not in result.stderr + result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="gunicorn needs fcntl (POSIX only)")
def test_RN_PLT_05_gunicorn_worker_boot_failure_is_json_and_redacted(tmp_path: Path) -> None:
    sentinel = "boot-sentinel-" + secrets.token_hex(8)
    (tmp_path / "failing_app.py").write_text(
        f"raise RuntimeError('worker boot failed password={sentinel}')\n", encoding="utf-8"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and argv
        [
            sys.executable,
            "-m",
            "gunicorn",
            "-c",
            "config/gunicorn.conf.py",
            "--bind",
            "127.0.0.1:0",
            "--workers",
            "1",
            "--pythonpath",
            str(tmp_path),
            "failing_app:application",
        ],
        cwd=BACKEND_DIR,
        env=django_env("config.settings.test", env_values("INFO")),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    # gunicorn's "worker failed to boot" exit code.
    assert result.returncode == 3, result.stderr
    # Nothing as text on stderr: gunicorn's handler is gone and its raw print is an event.
    assert result.stderr == ""
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert all(isinstance(event, dict) for event in events)
    gunicorn_events = [event for event in events if event["component"] == "gunicorn.error"]
    assert any(event["message"].startswith("Starting gunicorn") for event in gunicorn_events)
    [failure] = [event for event in gunicorn_events if event["message"] == BOOT_FAILURE]
    assert failure["level"] == "error"
    assert "RuntimeError: worker boot failed password=" + REDACTED in failure["exception"]
    printed = [event for event in events if event["message"] == "process.stderr"]
    assert {"component": "gunicorn.stderr", "level": "error"}.items() <= printed[0].items()
    assert [event["line"] for event in printed] == ["worker boot failed password=" + REDACTED]
    assert sentinel not in result.stdout
