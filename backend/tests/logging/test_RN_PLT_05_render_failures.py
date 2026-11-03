"""RN-PLT-05 (C-06, C-16): every stdout line is valid JSON, even when an event cannot be rendered.

T-PLT-12 review, taken by T-PLT-14: N-2, a record that fails to render (bad ``%`` args, a broken
formatter) wrote logging's text traceback to stderr, ``record.msg`` and its args included; now
``StdoutHandler.handleError`` writes one fixed JSON line (``log.render_failed``) with neither.
A circular structure in an event is cut by the redaction instead of failing ``json.dumps``. N-4,
``NaN``/``Infinity`` are not JSON: they render as strings, and the renderer rejects them as a
backstop (``allow_nan=False``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from apps.common.domain.redaction import CIRCULAR
from apps.common.logging import context, get_logger
from apps.common.logging.setup import RENDER_FAILED_EVENT, StdoutHandler, json_formatter
from tests.conftest import RunDjango
from tests.logging.conftest import StdoutLog

SENTINEL = "render-sentinel-" + "e2a7"
REQUEST_ID = "3f2b8c1e-9d4a-4b7e-8f21-6c0d5e9a7b13"
FIXED_FIELDS = {
    "timestamp",
    "level",
    "component",
    "message",
    "failed_component",
    "failed_level",
    "error_type",
}


def strict_json(line: str) -> dict[str, Any]:
    """``json.loads`` that fails on ``NaN``/``Infinity`` (Python accepts them by default)."""

    def reject(constant: str) -> None:
        pytest.fail(f"not JSON: {constant}")

    event = json.loads(line, parse_constant=reject)
    assert isinstance(event, dict)
    return event


def handler() -> StdoutHandler:
    stdout = StdoutHandler()
    stdout.setFormatter(json_formatter())
    return stdout


def bad_record() -> logging.LogRecord:
    # "%d" with a str: getMessage() raises TypeError inside the formatter.
    return logging.makeLogRecord(
        {
            "name": "thirdparty.sdk",
            "levelno": logging.WARNING,
            "levelname": "WARNING",
            "msg": "charged %d",
            "args": (SENTINEL,),
        }
    )


def test_RN_PLT_05_render_failure_writes_a_fixed_json_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    context.bind_request(REQUEST_ID)
    handler().handle(bad_record())
    out, err = capsys.readouterr()
    assert err == ""
    (line,) = out.splitlines()
    event = strict_json(line)
    assert event.keys() == FIXED_FIELDS | {"request_id"}
    assert event["message"] == RENDER_FAILED_EVENT
    assert (event["level"], event["component"]) == ("error", "apps.common.logging.setup")
    assert (event["failed_component"], event["failed_level"]) == ("thirdparty.sdk", "warning")
    assert event["error_type"] == "TypeError"
    assert event["request_id"] == REQUEST_ID
    assert event["timestamp"].endswith("Z")
    assert SENTINEL not in out
    assert "charged" not in out  # nor the message template


def test_RN_PLT_05_render_failure_never_shows_the_error_message(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = handler()

    def broken(record: logging.LogRecord) -> str:
        raise RuntimeError(f"cannot render redis://:{SENTINEL}@redis.example")

    monkeypatch.setattr(stdout, "format", broken)
    capsys.readouterr()
    stdout.handle(logging.makeLogRecord({"name": "apps.demo", "msg": "demo"}))
    out, err = capsys.readouterr()
    assert err == ""
    event = strict_json(out)
    assert (event["message"], event["error_type"]) == (RENDER_FAILED_EVENT, "RuntimeError")
    assert "request_id" not in event  # none bound
    assert SENTINEL not in out


def test_RN_PLT_05_circular_dict_in_an_event_still_renders_one_line(stdout_log: StdoutLog) -> None:
    circular: dict[str, Any] = {"name": "loop"}
    circular["self"] = circular
    get_logger("apps.demo").info("demo.circular", data=circular)
    log = stdout_log.read()
    assert log.err == ""
    (line,) = log.lines
    assert strict_json(line)["data"] == {"name": "loop", "self": CIRCULAR}


def test_RN_PLT_05_non_finite_floats_render_as_strict_json(stdout_log: StdoutLog) -> None:
    get_logger("apps.demo").info("demo.ratio", ratio=float("nan"), limits=[float("inf"), 1.5])
    logging.getLogger("thirdparty.lib").info("demo.stdlib", extra={"ratio": float("-inf")})
    lines = stdout_log.read().lines
    structlog_event, stdlib_event = (strict_json(line) for line in lines)
    assert (structlog_event["ratio"], structlog_event["limits"]) == ("NaN", ["Infinity", 1.5])
    assert stdlib_event["ratio"] == "-Infinity"


def test_RN_PLT_05_renderer_rejects_non_finite_floats_as_a_backstop() -> None:
    renderer = json_formatter().processors[-1]
    with pytest.raises(ValueError, match="JSON"):
        renderer(None, "info", {"event": "demo", "ratio": float("nan")})


# pytest's own capture handler re-raises render errors, so the real path (logging's handler
# chain without pytest) runs in a plain interpreter.
RENDER_PROBE = f"""
import logging
import django
django.setup()
logging.getLogger("thirdparty.sdk").warning("charged %d", "{SENTINEL}")
logging.getLogger("thirdparty.sdk").warning("demo.after")
"""


def test_RN_PLT_05_render_failure_outside_pytest_writes_nothing_to_stderr(
    run_django: RunDjango,
) -> None:
    result = run_django(
        "-c",
        RENDER_PROBE,
        settings_module="config.settings.test",
        values={
            "DJANGO_SECRET_KEY": "test-only-not-a-secret",
            "DATABASE_URL": "postgres://db.example/hub",
            "REDIS_URL": "redis://redis.example:6379/0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    failed, after = (strict_json(line) for line in result.stdout.splitlines())
    assert (failed["message"], failed["error_type"]) == (RENDER_FAILED_EVENT, "TypeError")
    assert after["message"] == "demo.after"  # logging goes on
    assert SENTINEL not in result.stdout


# T-PLT-14 review N-1: Python warnings went to stderr as plain text, outside the redaction.
WARNING_PROBE = f"""
import warnings
import django
django.setup()
warnings.warn("deprecated client, password=" + "{SENTINEL}")
"""


def test_AC_PLT_08_python_warnings_are_json_and_redacted(run_django: RunDjango) -> None:
    result = run_django(
        "-c",
        WARNING_PROBE,
        settings_module="config.settings.test",
        values={
            "DJANGO_SECRET_KEY": "test-only-not-a-secret",
            "DATABASE_URL": "postgres://db.example/hub",
            "REDIS_URL": "redis://redis.example:6379/0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert SENTINEL not in result.stdout
    (event,) = (strict_json(line) for line in result.stdout.splitlines())
    assert (event["component"], event["level"]) == ("py.warnings", "warning")
    assert "UserWarning: deprecated client, password=[REDACTED]" in event["message"]
