"""Fixtures of the cross-tenant suite: the two organizations and a client that never re-raises."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog
from django.test import Client

from tests.cross_tenant.harness import World, build_world
from tests.cross_tenant.registry import load


@pytest.fixture(autouse=True)
def no_cached_loggers() -> Iterator[None]:
    """The suite runs before ``tests/logging`` and ``tests/tenancy``: it must not cache loggers.

    With ``cache_logger_on_first_use`` a logger keeps the processor list of its first call. The
    logging tests then configure a new list, and a logger cached here (``tenancy.access_denied``)
    would never reach a later ``capture_logs``.
    """
    previous = structlog.get_config()["cache_logger_on_first_use"]
    structlog.configure(cache_logger_on_first_use=False)
    yield
    structlog.configure(cache_logger_on_first_use=previous)


@pytest.fixture
def world(db: None) -> World:
    return build_world(load().seeds)


@pytest.fixture
def xt_client() -> Client:
    """A view that skips the guard may raise: the suite reads the ``500``, not the traceback."""
    return Client(raise_request_exception=False)
