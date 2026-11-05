"""AC-PLT-18 (RN-PLT-10, RF-PLT-10): ``auto_`` names and ``RunPython`` mixed with schema (T-PLT-23).

Step 8 of CI (job ``migrations``) runs ``lint_migrations``. A migration named ``NNNN_auto_<date>``
or one where ``RunPython`` sits next to any other operation must make it fail; ``0001_initial`` and
a ``RunPython``-only migration pass. The rules are checked in-process on built ``Migration``
objects, and the command end to end in a subprocess with ``settings_synthetic`` on the synthetic
apps ``bad_autoname`` and ``bad_mixed`` (design.md §3.2.7). The command reads migrations from disk
only (``MigrationLoader`` without a connection): no database is needed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

import pytest
from django.db import migrations, models
from django.db.migrations.operations.base import Operation

from apps.common.migration_lint.rules import (
    AUTO_NAME,
    MIXED_RUNPYTHON,
    is_project_app,
    migration_problems,
)
from tests.conftest import RunDjango
from tests.migrations.conftest import SYNTHETIC_SETTINGS, subprocess_values


def forwards(apps: object, schema_editor: object) -> None:
    """Placeholder data step: the rules never run the code."""


ADD_FIELD = migrations.AddField("gizmo", "slug", models.SlugField(default=""))
RUN_PYTHON = migrations.RunPython(forwards, migrations.RunPython.noop)


def problems(name: str, operations: Sequence[Operation]) -> list[str]:
    return migration_problems(name, list(operations))


# --- Rules (in-process) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["0002_auto_20261105_1200", "0010_auto_20260101_0000", "1234_auto_x"]
)
def test_AC_PLT_18_rule_auto_name_is_a_problem(name: str) -> None:
    assert problems(name, [ADD_FIELD]) == [AUTO_NAME]


@pytest.mark.parametrize(
    "name",
    [
        "0001_initial",
        "0002_gizmo_slug",
        "0003_add_branch_timezone",
        "0004_autonomous_mode",
        "0005_backfill_auto_codes",
    ],
)
def test_AC_PLT_18_rule_descriptive_names_pass(name: str) -> None:
    assert problems(name, [ADD_FIELD]) == []


def test_AC_PLT_18_rule_runpython_with_schema_operation_is_a_problem() -> None:
    assert problems("0002_add_slug", [ADD_FIELD, RUN_PYTHON]) == [MIXED_RUNPYTHON]
    assert problems("0002_add_slug", [RUN_PYTHON, ADD_FIELD]) == [MIXED_RUNPYTHON]


def test_AC_PLT_18_rule_runpython_with_runsql_is_a_problem() -> None:
    run_sql = migrations.RunSQL("SELECT 1", migrations.RunSQL.noop)
    assert problems("0002_data", [RUN_PYTHON, run_sql]) == [MIXED_RUNPYTHON]


def test_AC_PLT_18_rule_runpython_alone_or_repeated_passes() -> None:
    other = migrations.RunPython(forwards, migrations.RunPython.noop)
    assert problems("0003_backfill", [RUN_PYTHON]) == []
    assert problems("0003_backfill", [RUN_PYTHON, other]) == []


def test_AC_PLT_18_rule_schema_only_passes() -> None:
    remove = migrations.RemoveField("gizmo", "old")
    assert problems("0002_slug", [ADD_FIELD, remove]) == []
    assert problems("0002_empty", []) == []


def test_AC_PLT_18_rule_mixing_inside_separate_database_and_state_is_a_problem() -> None:
    nested_database = migrations.SeparateDatabaseAndState(database_operations=[RUN_PYTHON])
    assert problems("0002_x", [ADD_FIELD, nested_database]) == [MIXED_RUNPYTHON]
    nested_state = migrations.SeparateDatabaseAndState(state_operations=[ADD_FIELD])
    assert problems("0002_x", [RUN_PYTHON, nested_state]) == [MIXED_RUNPYTHON]
    both_nested = migrations.SeparateDatabaseAndState(
        database_operations=[migrations.SeparateDatabaseAndState([RUN_PYTHON]), ADD_FIELD]
    )
    assert problems("0002_x", [both_nested]) == [MIXED_RUNPYTHON]
    only_python = migrations.SeparateDatabaseAndState(database_operations=[RUN_PYTHON])
    assert problems("0002_x", [only_python]) == []


def test_AC_PLT_18_rule_reports_both_problems() -> None:
    assert problems("0002_auto_20261105_1200", [ADD_FIELD, RUN_PYTHON]) == [
        AUTO_NAME,
        MIXED_RUNPYTHON,
    ]


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("apps", True),
        ("apps.charges", True),
        ("apps.integrations.providers.mercadopago", True),
        ("appsx", False),
        ("django.contrib.auth", False),
        ("tests.migrations.synthetic_apps.bad_mixed", False),
        ("rest_framework", False),
    ],
)
def test_AC_PLT_18_only_apps_modules_are_linted_by_default(module: str, expected: bool) -> None:
    assert is_project_app(module) is expected


# --- Command (subprocess, synthetic apps) -------------------------------------------------------


@pytest.fixture
def lint(run_django: RunDjango) -> RunDjango:
    """``manage.py lint_migrations <labels>`` under ``settings_synthetic`` (no database needed)."""

    def run(*labels: str) -> subprocess.CompletedProcess[str]:
        return run_django(
            "manage.py",
            "lint_migrations",
            *labels,
            settings_module=SYNTHETIC_SETTINGS,
            values=subprocess_values(),
        )

    return run


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


@pytest.mark.integration
def test_AC_PLT_18_auto_named_migration_fails(lint: RunDjango) -> None:
    result = lint("bad_autoname")

    assert result.returncode == 1, output(result)
    assert f"bad_autoname.0002_auto_20261105_1200: {AUTO_NAME}" in result.stdout
    assert "1 migration problem(s)" in result.stderr
    assert "Traceback" not in output(result)


@pytest.mark.integration
def test_AC_PLT_18_0001_initial_is_accepted(lint: RunDjango) -> None:
    result = lint("bad_autoname")

    assert "0001_initial" not in output(result)
    # Both migrations of the app were read: the clean one is counted, not skipped.
    assert "Checked 2 migration(s)" in output(result)


@pytest.mark.integration
def test_AC_PLT_18_runpython_mixed_with_schema_ops_fails(lint: RunDjango) -> None:
    result = lint("bad_mixed")

    assert result.returncode == 1, output(result)
    assert f"bad_mixed.0002_add_slug_and_backfill: {MIXED_RUNPYTHON}" in result.stdout
    assert "Traceback" not in output(result)


@pytest.mark.integration
def test_AC_PLT_18_runpython_alone_passes(lint: RunDjango) -> None:
    result = lint("bad_mixed")

    # 0003 is RunPython only (with its reverse): read and not reported.
    assert "Checked 3 migration(s)" in output(result)
    assert "0003_backfill_slugs" not in output(result)
    assert "1 migration problem(s)" in result.stderr


@pytest.mark.integration
def test_AC_PLT_18_several_apps_report_every_problem(lint: RunDjango) -> None:
    result = lint("bad_autoname", "bad_mixed", "missing_migration")

    assert result.returncode == 1, output(result)
    assert "bad_autoname.0002_auto_20261105_1200" in result.stdout
    assert "bad_mixed.0002_add_slug_and_backfill" in result.stdout
    assert "2 migration problem(s)" in result.stderr


@pytest.mark.integration
def test_AC_PLT_18_clean_synthetic_app_passes(lint: RunDjango) -> None:
    result = lint("missing_migration")

    assert result.returncode == 0, output(result)
    assert "Checked 1 migration(s): no problems" in result.stdout


@pytest.mark.integration
def test_AC_PLT_18_unknown_app_label_fails(lint: RunDjango) -> None:
    result = lint("no_such_app")

    assert result.returncode == 1, output(result)
    assert "No installed app with label 'no_such_app'" in result.stderr


@pytest.mark.integration
def test_AC_PLT_18_default_run_skips_non_apps_modules(lint: RunDjango) -> None:
    """Without labels (as CI runs it) only ``apps.*`` is linted: the synthetic apps are not."""
    result = lint()

    assert result.returncode == 0, output(result)
    assert "bad_autoname" not in output(result)
    assert "bad_mixed" not in output(result)


@pytest.mark.integration
def test_AC_PLT_18_real_apps_pass(run_django: RunDjango) -> None:
    result = run_django(
        "manage.py",
        "lint_migrations",
        settings_module="config.settings.test",
        values=subprocess_values(),
    )

    assert result.returncode == 0, output(result)
    assert "no problems" in result.stdout
