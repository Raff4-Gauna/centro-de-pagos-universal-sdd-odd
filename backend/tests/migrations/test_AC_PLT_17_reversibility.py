"""AC-PLT-17 (RN-PLT-10, RF-PLT-10, C-17): irreversible migrations fail; reversible ones round-trip.

Step 8 of CI (job ``migrations``) runs ``lint_migrations`` (static: ``reversible is False``, nested
in ``SeparateDatabaseAndState`` too) and ``check_migrations_roundtrip`` (apply -> revert to zero ->
reapply on the job's throwaway PostgreSQL). The rules are checked in-process; both commands end to
end in subprocesses with ``settings_synthetic`` on the throwaway ``hub_synthetic``, always with app
labels (``good_reversible``, ``bad_irreversible``) so the other synthetic apps never mix in
(T-PLT-23 review, item 3). Design.md §3.2.7, T-PLT-24.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest
from django.core.management.base import CommandError
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.operations.base import Operation

from apps.common.management.commands import check_migrations_roundtrip as roundtrip_module
from apps.common.migration_lint.rules import (
    IRREVERSIBLE,
    MIXED_RUNPYTHON,
    irreversible_problem,
    migration_problems,
)
from tests.conftest import RunDjango
from tests.migrations.conftest import subprocess_values
from tests.migrations.settings_synthetic import SYNTHETIC_DATABASE


def forwards(apps: object, schema_editor: object) -> None:
    """Placeholder data step: the rules never run the code."""


# Destructive (reverts to zero): every run on hub_synthetic confirms it is throwaway.
ROUNDTRIP = ("check_migrations_roundtrip", "--allow-data-loss")
# The apps under ``apps.*`` with migrations: what a run without labels reverts.
PROJECT_APPS = {"identity", "tenancy"}
RUN_PYTHON_NO_REVERSE = migrations.RunPython(forwards)
RUN_SQL_NO_REVERSE = migrations.RunSQL("UPDATE gizmo SET name = lower(name)")
RUN_PYTHON_ERROR = irreversible_problem(RUN_PYTHON_NO_REVERSE)
RUN_SQL_ERROR = irreversible_problem(RUN_SQL_NO_REVERSE)


class OneWay(Operation):
    """A custom operation declaring itself irreversible."""

    reversible = False

    def state_forwards(self, app_label: str, state: Any) -> None:
        """No state change."""


def problems(operations: Sequence[Operation]) -> list[str]:
    return migration_problems("0002_data", list(operations))


# --- Rules (in-process) -------------------------------------------------------------------------


def test_AC_PLT_17_rule_runpython_without_reverse_is_a_problem() -> None:
    assert problems([RUN_PYTHON_NO_REVERSE]) == [RUN_PYTHON_ERROR]
    assert "irreversible RunPython" in RUN_PYTHON_ERROR
    assert "reverse_code" in RUN_PYTHON_ERROR


def test_AC_PLT_17_rule_runsql_without_reverse_is_a_problem() -> None:
    assert problems([RUN_SQL_NO_REVERSE]) == [RUN_SQL_ERROR]
    assert "irreversible RunSQL" in RUN_SQL_ERROR
    assert "reverse_sql" in RUN_SQL_ERROR


def test_AC_PLT_17_rule_noop_reverses_pass() -> None:
    assert problems([migrations.RunPython(forwards, migrations.RunPython.noop)]) == []
    assert problems([migrations.RunSQL("SELECT 1", migrations.RunSQL.noop)]) == []
    assert problems([migrations.RunSQL("SELECT 1", "SELECT 2")]) == []


def test_AC_PLT_17_rule_schema_operations_pass() -> None:
    add = migrations.AddField("gizmo", "slug", models.SlugField(default=""))
    assert problems([add, migrations.RemoveField("gizmo", "old")]) == []


def test_AC_PLT_17_rule_irreversible_inside_separate_database_and_state_is_a_problem() -> None:
    database = migrations.SeparateDatabaseAndState(database_operations=[RUN_SQL_NO_REVERSE])
    assert problems([database]) == [RUN_SQL_ERROR]
    state = migrations.SeparateDatabaseAndState(state_operations=[OneWay()])
    assert problems([state]) == [IRREVERSIBLE.format(operation="OneWay", reverse="a reverse")]
    deep = migrations.SeparateDatabaseAndState(
        database_operations=[migrations.SeparateDatabaseAndState([RUN_SQL_NO_REVERSE])]
    )
    assert problems([deep]) == [RUN_SQL_ERROR]


def test_AC_PLT_17_rule_reports_each_irreversible_operation_after_other_problems() -> None:
    result = migration_problems(
        "0002_auto_20261105_1200", [RUN_PYTHON_NO_REVERSE, RUN_SQL_NO_REVERSE]
    )
    assert result[1:] == [MIXED_RUNPYTHON, RUN_PYTHON_ERROR, RUN_SQL_ERROR]


# --- Command internals (in-process, no database) ------------------------------------------------


def fake_executor(leaves: list[tuple[str, str]], plan_apps: list[str]) -> Any:
    plan = [(SimpleNamespace(app_label=app), False) for app in plan_apps]
    graph = SimpleNamespace(leaf_nodes=lambda: leaves)
    return SimpleNamespace(loader=SimpleNamespace(graph=graph), migration_plan=lambda *_: plan)


def test_AC_PLT_17_revert_order_is_reverse_dependency_order() -> None:
    # charges depends on accounts; reports (independent) last in the plan: reverted first.
    executor = fake_executor(
        [("accounts", "0002"), ("charges", "0001"), ("reports", "0001")],
        ["accounts", "charges", "accounts", "charges", "reports"],
    )
    assert roundtrip_module.revert_order(executor, ["accounts", "charges", "reports"]) == [
        "reports",
        "charges",
        "accounts",
    ]
    assert roundtrip_module.revert_order(fake_executor([], []), []) == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (IrreversibleError("Operation X in app.0002 is not reversible"), "IrreversibleError"),
        (NotImplementedError("You cannot reverse this operation"), "NotImplementedError"),
        (NotImplementedError(), "operation cannot be reversed"),
    ],
)
def test_AC_PLT_17_revert_failure_becomes_command_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    def failing(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(roundtrip_module, "call_command", failing)
    with pytest.raises(CommandError, match=r"^revert app: ") as raised:
        roundtrip_module.Command().migrate("revert app", ["app", "zero"], 0)
    assert expected in str(raised.value)


def test_AC_PLT_17_roundtrip_without_allow_data_loss_exits_2_before_connecting() -> None:
    """In-process, where pytest-django blocks database access: the refusal opens no connection."""
    with pytest.raises(CommandError) as raised:
        roundtrip_module.Command().handle(app_labels=[], verbosity=1, allow_data_loss=False)
    assert raised.value.returncode == 2
    assert "--allow-data-loss" in str(raised.value)


# --- Commands (subprocess: settings_synthetic on hub_synthetic) -----------------------------------


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def synthetic_url() -> str:
    return urlsplit(os.environ["DATABASE_URL"])._replace(path=f"/{SYNTHETIC_DATABASE}").geturl()


def query(statement: str, *params: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(synthetic_url(), connect_timeout=5) as connection:
        return connection.execute(statement, params).fetchall()


def recorded_migrations() -> list[tuple[Any, ...]] | None:
    """Every row of ``django_migrations`` on ``hub_synthetic`` (None while the table is absent)."""
    if query("SELECT to_regclass('django_migrations')") == [(None,)]:
        return None
    return query("SELECT app, name, applied FROM django_migrations ORDER BY id")


@pytest.mark.integration
@pytest.mark.usefixtures("fresh_synthetic_db")
def test_AC_PLT_17_runpython_without_reverse_fails(run_manage: RunDjango) -> None:
    lint = run_manage("lint_migrations", "bad_irreversible")
    assert lint.returncode == 1, output(lint)
    assert f"bad_irreversible.0004_seed_items: {RUN_PYTHON_ERROR}" in lint.stdout

    roundtrip = run_manage(*ROUNDTRIP, "bad_irreversible")
    assert roundtrip.returncode == 1, output(roundtrip)
    # Django refuses before touching the database: the last migration is a top-level RunPython.
    assert "revert bad_irreversible: IrreversibleError" in roundtrip.stderr
    assert "bad_irreversible.0004_seed_items is not reversible" in roundtrip.stderr
    assert "Round trip passed" not in output(roundtrip)
    assert "Traceback" not in output(roundtrip)


@pytest.mark.integration
def test_AC_PLT_17_runsql_without_reverse_fails(run_manage: RunDjango) -> None:
    result = run_manage("lint_migrations", "bad_irreversible")

    assert result.returncode == 1, output(result)
    assert f"bad_irreversible.0003_lowercase_item_names: {RUN_SQL_ERROR}" in result.stdout
    assert "Checked 4 migration(s): 3 migration problem(s)" in result.stderr
    assert "0001_initial" not in output(result)


@pytest.mark.integration
def test_AC_PLT_17_irreversible_inside_separate_db_and_state_fails(run_manage: RunDjango) -> None:
    result = run_manage("lint_migrations", "bad_irreversible")

    # Top-level SeparateDatabaseAndState is "reversible" for Django: the nested RunSQL is not.
    assert f"bad_irreversible.0002_item_name_index: {RUN_SQL_ERROR}" in result.stdout


@pytest.mark.integration
def test_AC_PLT_17_reversible_migration_passes_lint(run_manage: RunDjango) -> None:
    result = run_manage("lint_migrations", "good_reversible")

    assert result.returncode == 0, output(result)
    assert "Checked 4 migration(s): no problems" in result.stdout


@pytest.mark.integration
@pytest.mark.usefixtures("fresh_synthetic_db")
def test_AC_PLT_17_reversible_migration_roundtrips_on_disposable_db(run_manage: RunDjango) -> None:
    result = run_manage(*ROUNDTRIP, "good_reversible")

    assert result.returncode == 0, output(result)
    assert "Round trip passed for 1 app(s): good_reversible" in result.stdout
    # Applied, reverted down to the first migration (RunPython.noop and the nested RunSQL
    # reverse included) and applied again.
    assert "Unapplying good_reversible.0004_part_code_index" in result.stdout
    assert "Unapplying good_reversible.0003_fill_part_codes" in result.stdout
    assert "Unapplying good_reversible.0001_initial" in result.stdout
    assert result.stdout.index("Unapplying") < result.stdout.rindex(
        "Applying good_reversible.0004_part_code_index"
    )
    # Only the labelled app: the other synthetic apps are neither applied nor reverted.
    for other in ("bad_irreversible", "bad_mixed", "bad_autoname", "missing_migration"):
        assert other not in output(result)
    # The database ends fully migrated, the RunSQL index back in place.
    names = query(
        "SELECT name FROM django_migrations WHERE app = %s ORDER BY name", "good_reversible"
    )
    assert [name for (name,) in names] == [
        "0001_initial",
        "0002_part_code",
        "0003_fill_part_codes",
        "0004_part_code_index",
    ]
    index = query("SELECT 1 FROM pg_indexes WHERE indexname = %s", "good_reversible_part_code_idx")
    assert index == [(1,)]


def reverted_apps(stdout: str) -> set[str]:
    """App labels of the ``Unapplying <app>.<migration>...`` lines."""
    lines = (line.strip() for line in stdout.splitlines())
    return {line.split()[1].split(".")[0] for line in lines if line.startswith("Unapplying ")}


@pytest.mark.integration
@pytest.mark.usefixtures("fresh_synthetic_db")
def test_AC_PLT_17_default_run_reverts_only_apps_modules(run_manage: RunDjango) -> None:
    """Without labels (as CI runs it) the whole project is migrated but only ``apps.*`` reverted."""
    result = run_manage(*ROUNDTRIP)

    assert result.returncode == 0, output(result)
    assert "Round trip passed for 2 app(s): identity, tenancy" in result.stdout
    # Migrated with the rest of the project; the only ones reverted are the apps under ``apps``.
    assert "Applying good_reversible.0004_part_code_index" in result.stdout
    assert "Unapplying identity.0001_users" in result.stdout
    assert reverted_apps(result.stdout) == PROJECT_APPS


@pytest.mark.integration
def test_AC_PLT_17_roundtrip_without_flag_applies_and_reverts_nothing(
    run_manage: RunDjango,
) -> None:
    before = recorded_migrations()
    result = run_manage("check_migrations_roundtrip", "good_reversible")

    assert result.returncode == 2, output(result)
    assert roundtrip_module.ALLOW_DATA_LOSS_REQUIRED in result.stderr
    assert "Applying" not in output(result)
    assert "Unapplying" not in output(result)
    assert "Traceback" not in output(result)
    assert recorded_migrations() == before


@pytest.mark.integration
@pytest.mark.usefixtures("fresh_synthetic_db")
def test_AC_PLT_17_app_with_empty_migrations_package_is_skipped(run_manage: RunDjango) -> None:
    """``startapp`` leaves ``migrations/`` with only ``__init__.py``: nothing to revert there."""
    result = run_manage(*ROUNDTRIP, "good_reversible", "empty_migrations")

    assert result.returncode == 0, output(result)
    assert "Round trip passed for 1 app(s): good_reversible" in result.stdout
    assert "Traceback" not in output(result)


@pytest.mark.integration
def test_AC_PLT_17_explicit_labels_with_nothing_to_check_fail(run_manage: RunDjango) -> None:
    """Asked for by name, zero apps is a mistake and not a pass (without labels it is valid)."""
    result = run_manage(*ROUNDTRIP, "empty_migrations")

    assert result.returncode == 1, output(result)
    assert "No migrations to check in: empty_migrations" in result.stderr
    assert "Round trip passed" not in output(result)
    assert "Traceback" not in output(result)


@pytest.mark.integration
def test_AC_PLT_17_unknown_app_label_fails(run_manage: RunDjango) -> None:
    result = run_manage(*ROUNDTRIP, "no_such_app")

    assert result.returncode == 1, output(result)
    assert "No installed app with label 'no_such_app'" in result.stderr


@pytest.mark.integration
def test_AC_PLT_17_real_apps_roundtrip(run_django: RunDjango, fresh_synthetic_db: str) -> None:
    """The real settings (as CI runs it), pointed at the throwaway database, not at ``hub``."""
    values = {**subprocess_values(), "DATABASE_URL": synthetic_url()}
    result = run_django(
        "manage.py",
        *ROUNDTRIP,
        settings_module="config.settings.test",
        values=values,
    )

    assert result.returncode == 0, output(result)
    assert "Round trip passed for 2 app(s): identity, tenancy" in result.stdout
    assert "Unapplying identity.0001_users" in result.stdout
    assert "Unapplying tenancy.0001_organization" in result.stdout
    assert result.stdout.index("Unapplying") < result.stdout.rindex("Applying identity.0001_users")
    assert reverted_apps(result.stdout) == PROJECT_APPS
