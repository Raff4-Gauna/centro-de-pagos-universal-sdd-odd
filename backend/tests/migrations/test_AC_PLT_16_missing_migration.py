"""AC-PLT-16 (RN-PLT-10, RF-PLT-10): a model change without migration fails the check (T-PLT-22).

Step 8 of CI (job ``migrations``) runs ``makemigrations --check --dry-run``. The synthetic app
``missing_migration`` has a field that ``0001_initial`` lacks: the command must exit non-zero
naming that change, and ``--dry-run`` must write no file. The real apps, under the real test
settings, must pass the same command, so the job is green on ``main``. Subprocesses on the
throwaway ``hub_synthetic`` database (design.md §3.2.7); they need the PostgreSQL of the job.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import RunDjango

CHECK = ("makemigrations", "--check", "--dry-run")
# Django's warning when it cannot check the applied history against the database (it goes on
# without it). A py.warnings JSON log line on stdout, through the platform logging.
HISTORY_SKIPPED = "consistent migration history"
SYNTHETIC_MIGRATIONS = Path(__file__).parent / "synthetic_apps" / "missing_migration" / "migrations"

pytestmark = pytest.mark.integration


def migration_files() -> list[str]:
    return sorted(path.name for path in SYNTHETIC_MIGRATIONS.glob("*.py"))


def test_AC_PLT_16_model_change_without_migration_fails_check(run_manage: RunDjango) -> None:
    before = migration_files()
    assert before == ["0001_initial.py", "__init__.py"]

    result = run_manage(*CHECK, "missing_migration")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Migrations for 'missing_migration':" in result.stdout
    assert "+ Add field code to widget" in result.stdout
    # Failing because of the missing migration, not because the command broke.
    assert "Traceback" not in result.stdout + result.stderr
    # The history check ran against the throwaway database instead of being skipped.
    assert HISTORY_SKIPPED not in result.stdout + result.stderr
    assert migration_files() == before


def test_AC_PLT_16_whole_project_check_catches_synthetic_app(run_manage: RunDjango) -> None:
    """Without an app label (as CI runs it) the same change is found."""
    result = run_manage(*CHECK)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "+ Add field code to widget" in result.stdout


def test_AC_PLT_16_real_apps_have_no_missing_migrations(run_manage: RunDjango) -> None:
    result = run_manage(*CHECK, settings_module="config.settings.test")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No changes detected" in result.stdout
    assert "missing_migration" not in result.stdout
