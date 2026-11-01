"""AC-PLT-12 (RN-PLT-05): ``print`` in ``backend/apps/`` fails lint via ruff ``T20`` (T-PLT-02).

The tests lint source from stdin against the real ``ruff.toml`` at the repo root, so they exercise
the same configuration that CI and pre-commit use. ruff runs from the current interpreter's env.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRINT_SOURCE = 'print("hello")\n'


def ruff_check_stdin(
    stdin_filename: str, source: str, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    """``ruff check`` of ``source`` as if it lived at ``stdin_filename`` (repo-relative)."""
    return subprocess.run(  # noqa: S603 - fixed argv, test-only
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "concise",
            *extra_args,
            "--stdin-filename",
            stdin_filename,
            "-",
        ],
        cwd=REPO_ROOT,
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_AC_PLT_12_print_in_backend_apps_fails_lint() -> None:
    result = ruff_check_stdin("backend/apps/demo/x.py", PRINT_SOURCE)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "T201" in result.stdout


def test_AC_PLT_12_print_in_backend_subdir_named_frontend_fails_lint() -> None:
    # Regression (T-PLT-02 review, B-1): only the root frontend/ is excluded, not every `frontend`.
    result = ruff_check_stdin("backend/apps/frontend/x.py", PRINT_SOURCE)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "T201" in result.stdout


def test_AC_PLT_12_root_frontend_is_excluded() -> None:
    result = ruff_check_stdin("frontend/x.py", PRINT_SOURCE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "T201" not in result.stdout


def test_AC_PLT_12_print_in_backend_tests_still_fails_lint() -> None:
    # Tests only relax S101/N802; T20 stays active there.
    result = ruff_check_stdin("backend/apps/demo/tests/test_x.py", PRINT_SOURCE)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "T201" in result.stdout


def test_AC_PLT_12_print_in_scripts_is_allowed() -> None:
    result = ruff_check_stdin("scripts/x.py", PRINT_SOURCE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "T201" not in result.stdout


def test_AC_PLT_12_legacy_source_is_force_excluded() -> None:
    # Q-055: context/legacy-source/ is read-only evidence; ruff skips it even when a file is passed
    # explicitly (force-exclude), as pre-commit does.
    result = ruff_check_stdin("context/legacy-source/x.py", PRINT_SOURCE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "T201" not in result.stdout


def test_AC_PLT_12_legacy_source_is_linted_only_without_force_exclude() -> None:
    # Control for the test above: the exclusion (not a missing rule) is what lets the print through.
    result = ruff_check_stdin("context/legacy-source/x.py", PRINT_SOURCE, "--no-force-exclude")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "T201" in result.stdout
