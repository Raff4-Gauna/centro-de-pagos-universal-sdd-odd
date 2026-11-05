"""Fixtures of the migration checks (design.md §3.2.7, RN-PLT-10).

The checks run as ``manage.py`` subprocesses (``run_django``) with ``settings_synthetic``, on the
throwaway database ``hub_synthetic``: ``synthetic_db`` creates it on the server of ``DATABASE_URL``
(the CI ``tests`` job service) and drops it at the end. With the database there, ``makemigrations``
also checks the applied history against it instead of skipping that check with a warning.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from tests.conftest import RunDjango
from tests.migrations.settings_synthetic import SYNTHETIC_DATABASE

SYNTHETIC_SETTINGS = "tests.migrations.settings_synthetic"
# What config.settings.test requires, passed through to every subprocess (non-secret test values).
PASSED_VARS = ("DJANGO_SECRET_KEY", "DATABASE_URL", "REDIS_URL")


def subprocess_values() -> dict[str, str]:
    return {name: os.environ[name] for name in PASSED_VARS}


def _drop_synthetic(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    # FORCE: a subprocess that died mid-command must not leave the database undroppable.
    statement = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
    connection.execute(statement.format(sql.Identifier(SYNTHETIC_DATABASE)))


@pytest.fixture(scope="session")
def synthetic_db() -> Iterator[str]:
    """A fresh, empty ``hub_synthetic`` for the session; a leftover from a previous run is dropped.

    Created through the database of ``DATABASE_URL`` itself, from the environment and not from
    ``settings.DATABASES`` (pytest-django renames that one to its ``test_`` database).
    """
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as connection:
        _drop_synthetic(connection)
        statement = sql.SQL("CREATE DATABASE {}")
        connection.execute(statement.format(sql.Identifier(SYNTHETIC_DATABASE)))
    try:
        yield SYNTHETIC_DATABASE
    finally:
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as connection:
            _drop_synthetic(connection)


@pytest.fixture
def run_manage(run_django: RunDjango, synthetic_db: str) -> RunDjango:
    """``manage.py <args>`` in a subprocess; ``settings_module`` defaults to the synthetic one."""

    def run(
        *args: str, settings_module: str = SYNTHETIC_SETTINGS
    ) -> subprocess.CompletedProcess[str]:
        return run_django(
            "manage.py", *args, settings_module=settings_module, values=subprocess_values()
        )

    return run
