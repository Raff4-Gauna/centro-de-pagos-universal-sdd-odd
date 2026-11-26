"""Fixtures shared by the identity suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog


@pytest.fixture(autouse=True)
def no_cached_loggers() -> Iterator[None]:
    """The suite runs before ``tests/logging`` and ``tests/tenancy``: it must not cache loggers.

    With ``cache_logger_on_first_use`` a logger keeps the processor list of its first call. The
    logging tests then configure a new list, and a logger of ``apps.common`` cached here (the
    refused operator of ``platform_operators``, Q-242) would never reach a later ``capture_logs``
    of ``tests/tenancy``. Same fixture as ``tests/cross_tenant/conftest.py``.
    """
    previous = structlog.get_config()["cache_logger_on_first_use"]
    structlog.configure(cache_logger_on_first_use=False)
    yield
    structlog.configure(cache_logger_on_first_use=previous)
