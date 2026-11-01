"""Fixtures for the logging tests (T-PLT-12): what the process writes to stdout, line by line.

The only handler writes each record to the *current* ``sys.stdout`` (``StdoutHandler``), so
``capsys`` sees exactly the lines a container would print. Every test starts and ends with an empty
logging context: a ``request_id`` bound by one test must not show up in the next one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from apps.common.logging import context


@dataclass(frozen=True)
class CapturedLog:
    out: str
    err: str

    @property
    def lines(self) -> list[str]:
        return self.out.splitlines()

    @property
    def events(self) -> list[dict[str, Any]]:
        """Every stdout line parsed as JSON (fails on the first line that is not one object)."""
        events = []
        for line in self.lines:
            event = json.loads(line)
            assert isinstance(event, dict), line
            events.append(event)
        return events

    def find(self, message: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("message") == message]


@dataclass(frozen=True)
class StdoutLog:
    capsys: pytest.CaptureFixture[str]

    def read(self) -> CapturedLog:
        out, err = self.capsys.readouterr()
        return CapturedLog(out=out, err=err)


@pytest.fixture
def stdout_log(capsys: pytest.CaptureFixture[str]) -> StdoutLog:
    capsys.readouterr()  # drop anything written before the test body
    return StdoutLog(capsys)


@pytest.fixture(autouse=True)
def _empty_log_context() -> Iterator[None]:
    context.clear()
    yield
    context.clear()
