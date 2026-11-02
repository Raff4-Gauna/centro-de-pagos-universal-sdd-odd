"""Fixtures for the logging tests (T-PLT-12): what the process writes to stdout, line by line.

The only handler writes each record to the *current* ``sys.stdout`` (``StdoutHandler``), so
``capsys`` sees exactly the lines a container would print. Every test starts and ends with an empty
logging context: a ``request_id`` bound by one test must not show up in the next one.

Celery (T-PLT-17): ``memory_broker`` points the app at kombu's in-memory transport and collects
the headers of what is published; ``redis_worker`` runs a ``start_worker`` thread on the configured
broker (``REDIS_URL``, ``integration`` tests) and yields an event set when a message is done with:
a task finished, or an unknown or rejected message.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
from celery.contrib.testing.worker import start_worker
from celery.signals import after_task_publish, task_postrun, task_rejected, task_unknown

from apps.common.logging import context
from config import celery_app


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


def captured(capfd: pytest.CaptureFixture[str]) -> CapturedLog:
    out, err = capfd.readouterr()
    return CapturedLog(out=out, err=err)


def drop_broker_connections() -> None:
    """Forget the pooled connections, so the next use follows ``broker_url``.

    What Celery's own reset after a fork does: the app's pool and the AMQP helper with its producer
    pool, rebuilt on next use. Not ``app.close()``: it also deregisters the app, and a
    ``shared_task`` imported later in the session would no longer bind to it. Nor closing the pool:
    kombu keeps it in a registry per broker URL and would hand it back closed.
    """
    celery_app.__dict__["_pool"] = None
    celery_app.__dict__.pop("amqp", None)


@pytest.fixture
def memory_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """kombu's in-memory transport; yields the headers of every message published meanwhile."""
    published: list[dict[str, Any]] = []

    def keep(sender: object = None, headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
        published.append(dict(headers or {}))

    monkeypatch.setattr(celery_app.conf, "broker_url", "memory://")
    drop_broker_connections()
    after_task_publish.connect(keep, weak=False)
    try:
        yield published
    finally:
        after_task_publish.disconnect(keep)
        celery_app.control.purge()  # the in-memory queue outlives the connection
        drop_broker_connections()


@pytest.fixture
def redis_worker() -> Iterator[threading.Event]:
    """A worker thread on the configured broker; yields an event set when a message is done."""
    done = threading.Event()

    def finished(**kwargs: Any) -> None:
        done.set()

    signals = (task_postrun, task_unknown, task_rejected)
    celery_app.control.purge()  # a message left by an aborted run would be consumed first
    for signal in signals:
        signal.connect(finished, weak=False)
    try:
        with mock.patch.dict(os.environ), start_worker(celery_app, perform_ping_check=False):
            yield done
    finally:
        for signal in signals:
            signal.disconnect(finished)
