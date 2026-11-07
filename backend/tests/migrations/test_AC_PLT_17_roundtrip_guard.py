"""AC-PLT-17 (C-17): the round trip refuses a database that is not throwaway, T-IDA-00.

``--allow-data-loss`` says nothing about where it points, and CI and development share the name
``hub``. So the command looks at the content: a table with rows exits with 2 before ``migrate``.
Subprocesses with ``settings_synthetic`` on a freshly created ``hub_synthetic``.
"""

from __future__ import annotations

import itertools
import os
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest

from tests.conftest import RunDjango
from tests.migrations.conftest import SYNTHETIC_SETTINGS, subprocess_values
from tests.migrations.settings_synthetic import SYNTHETIC_DATABASE

Roundtrip = Callable[..., subprocess.CompletedProcess[str]]

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("fresh_synthetic_db")]

ROUNDTRIP = ("check_migrations_roundtrip", "--allow-data-loss")
ROW_VALUE = "value-that-must-never-be-printed"
RUN_NUMBERS = itertools.count()


@pytest.fixture
def roundtrip(run_django: RunDjango) -> Roundtrip:
    """``run_django`` caches by arguments and values; here the result depends on the database."""

    def run(*labels: str) -> subprocess.CompletedProcess[str]:
        values = {**subprocess_values(), "ROUNDTRIP_GUARD_RUN": str(next(RUN_NUMBERS))}
        return run_django(
            "manage.py", *ROUNDTRIP, *labels, settings_module=SYNTHETIC_SETTINGS, values=values
        )

    return run


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def execute(statement: str, *params: str) -> list[tuple[Any, ...]]:
    url = urlsplit(os.environ["DATABASE_URL"])._replace(path=f"/{SYNTHETIC_DATABASE}").geturl()
    with psycopg.connect(url, connect_timeout=5) as connection:
        cursor = connection.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


def create_leftover(*rows: str) -> None:
    execute("CREATE TABLE leftover (note text)")
    for row in rows:
        execute("INSERT INTO leftover (note) VALUES (%s)", row)


def test_AC_PLT_17_refuses_database_with_rows(roundtrip: Roundtrip) -> None:
    create_leftover(ROW_VALUE)

    result = roundtrip()

    assert result.returncode == 2, output(result)
    assert SYNTHETIC_DATABASE in result.stderr
    assert "leftover" in result.stderr
    assert "Applying" not in output(result)
    assert "Traceback" not in output(result)
    assert execute("SELECT note FROM leftover") == [(ROW_VALUE,)]
    assert execute("SELECT to_regclass('django_migrations')") == [(None,)]


def test_AC_PLT_17_labels_still_check_dependent_tables(roundtrip: Roundtrip) -> None:
    """``migrate <app> zero`` also reverts its dependents: labels do not narrow the guard."""
    create_leftover(ROW_VALUE)

    result = roundtrip("good_reversible")

    assert result.returncode == 2, output(result)
    assert "leftover" in result.stderr
    assert "Applying" not in output(result)


def test_AC_PLT_17_empty_tables_pass(roundtrip: Roundtrip) -> None:
    create_leftover()

    result = roundtrip("good_reversible")

    assert result.returncode == 0, output(result)
    assert "Round trip passed for 1 app(s): good_reversible" in result.stdout


def test_AC_PLT_17_recorded_migrations_do_not_count(roundtrip: Roundtrip) -> None:
    """A second run finds ``django_migrations`` full: that table alone is no reason to refuse."""
    first = roundtrip("good_reversible")
    assert first.returncode == 0, output(first)

    second = roundtrip("good_reversible")

    assert second.returncode == 0, output(second)


def test_AC_PLT_17_refusal_shows_no_values(roundtrip: Roundtrip) -> None:
    create_leftover(ROW_VALUE)

    result = roundtrip()

    assert result.returncode == 2, output(result)
    assert ROW_VALUE not in output(result)


def test_AC_PLT_17_prints_target_without_the_url(roundtrip: Roundtrip) -> None:
    result = roundtrip("good_reversible")

    password = urlsplit(os.environ["DATABASE_URL"]).password
    assert password is not None
    assert result.returncode == 0, output(result)
    assert f"Database: {SYNTHETIC_DATABASE} on " in result.stdout
    assert f":{password}@" not in output(result)
