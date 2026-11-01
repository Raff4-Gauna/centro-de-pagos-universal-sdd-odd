"""AC-PLT-13 (RN-PLT-08, C-14): ``check_file_size.py`` fails on code files over 400 lines."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_file_size
import pytest
from conftest import GitRepo, clean_git_env

SCRIPT = Path(check_file_size.__file__).resolve()


def run_check(capsys: pytest.CaptureFixture[str], *paths: str) -> tuple[int, str, str]:
    code = check_file_size.main(list(paths))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    "rel_path",
    [
        "backend/apps/common/big_module.py",
        "frontend/src/lib/big-module.ts",
        "frontend/src/components/BigComponent.tsx",
        "frontend/src/components/Legacy.jsx",
    ],
)
def test_AC_PLT_13_file_with_401_lines_fails_naming_it(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str], rel_path: str
) -> None:
    git_repo.write(rel_path, 401)
    git_repo.write("backend/apps/common/small.py", 10)

    code, _, err = run_check(capsys)

    assert code == 1
    assert f"{rel_path}: 401 lines" in err
    assert "small.py" not in err


def test_AC_PLT_13_every_oversized_file_is_named(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/a.py", 401)
    git_repo.write("frontend/src/b.ts", 900)

    code, _, err = run_check(capsys)

    assert code == 1
    assert "backend/apps/a.py: 401 lines" in err
    assert "frontend/src/b.ts: 900 lines" in err


def test_AC_PLT_13_test_file_with_401_lines_fails(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/tests/logging/test_redaction.py", 401)
    git_repo.write("frontend/src/lib/problem.test.ts", 401)

    code, _, err = run_check(capsys)

    assert code == 1
    assert "backend/tests/logging/test_redaction.py: 401 lines" in err
    assert "frontend/src/lib/problem.test.ts: 401 lines" in err


def test_AC_PLT_13_file_with_400_lines_passes(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/common/exactly_400.py", 400)
    git_repo.write("frontend/src/lib/exactly-400.ts", 400)
    git_repo.write("frontend/src/lib/no-final-newline.tsx", 400, final_newline=False)

    code, out, err = run_check(capsys)

    assert code == 0
    assert err == ""
    assert "3 code file(s) checked" in out


def test_AC_PLT_13_last_line_without_newline_counts(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/common/no_final_newline.py", 401, final_newline=False)

    code, _, err = run_check(capsys)

    assert code == 1
    assert "backend/apps/common/no_final_newline.py: 401 lines" in err


def test_AC_PLT_13_non_code_files_are_ignored(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("specs/00-platform/design.md", 900)
    git_repo.write("frontend/pnpm-lock.yaml", 5000)
    git_repo.write("backend/uv.lock", 5000)

    code, out, err = run_check(capsys)

    assert code == 0
    assert err == ""
    assert "0 code file(s) checked" in out


def test_AC_PLT_13_migration_and_generated_types_are_excluded(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/charges/migrations/0001_initial.py", 900)
    git_repo.write("backend/apps/integrations/providers/mp/fixtures/order.py", 900)
    git_repo.write("frontend/src/types/api.d.ts", 3000)
    git_repo.write("frontend/next-env.d.ts", 401)

    code, _, err = run_check(capsys)

    assert code == 0
    assert err == ""


def test_AC_PLT_13_exclusions_do_not_leak_to_similar_paths(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/common/migrations_helper.py", 401)
    git_repo.write("frontend/src/typesafe/api.ts", 401)

    code, _, err = run_check(capsys)

    assert code == 1
    assert "backend/apps/common/migrations_helper.py: 401 lines" in err
    assert "frontend/src/typesafe/api.ts: 401 lines" in err


def test_AC_PLT_13_legacy_source_is_excluded(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    # Q-055 / D-13: read-only evidence, not Hub code.
    git_repo.write("context/legacy-source/mpqr/qr_client.py", 1054)

    code, _, err = run_check(capsys)

    assert code == 0
    assert err == ""


def test_AC_PLT_13_non_ascii_repo_path(
    non_ascii_git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "ó" in str(non_ascii_git_repo.root)
    non_ascii_git_repo.write("backend/apps/común/módulo.py", 401)
    non_ascii_git_repo.write("backend/apps/común/pequeño.py", 400)

    code, _, err = run_check(capsys)

    assert code == 1
    assert "backend/apps/común/módulo.py: 401 lines" in err
    assert "pequeño.py" not in err


def test_AC_PLT_13_non_ascii_repo_path_as_cli(non_ascii_git_repo: GitRepo) -> None:
    non_ascii_git_repo.write("backend/apps/común/módulo.py", 401)

    completed = subprocess.run(  # noqa: S603 - our own script, fixed argv
        [sys.executable, str(SCRIPT)],
        cwd=non_ascii_git_repo.root,
        capture_output=True,
        env={**clean_git_env(), "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    assert completed.returncode == 1
    assert "backend/apps/común/módulo.py: 401 lines" in completed.stderr.decode("utf-8")


def test_AC_PLT_13_only_tracked_files_are_checked(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/common/untracked.py", 401, track=False)
    git_repo.write("backend/apps/common/tracked.py", 10)

    code, out, err = run_check(capsys)

    assert code == 0
    assert err == ""
    assert "1 code file(s) checked" in out


def test_AC_PLT_13_tracked_file_deleted_from_worktree_is_skipped(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    git_repo.write("backend/apps/common/gone.py", 401).unlink()

    code, _, err = run_check(capsys)

    assert code == 0
    assert err == ""


def test_AC_PLT_13_explicit_paths_limit_the_check(
    git_repo: GitRepo, capsys: pytest.CaptureFixture[str]
) -> None:
    # Pre-commit mode: only the files passed on the command line (and tracked) are checked.
    git_repo.write("backend/apps/common/big.py", 401)
    git_repo.write("backend/apps/common/small.py", 10)
    git_repo.write("backend/apps/common/untracked.py", 401, track=False)

    ok_code, _, ok_err = run_check(
        capsys, "backend/apps/common/small.py", "backend/apps/common/untracked.py"
    )
    bad_code, _, bad_err = run_check(capsys, "backend/apps/common/big.py")

    assert ok_code == 0
    assert ok_err == ""
    assert bad_code == 1
    assert "backend/apps/common/big.py: 401 lines" in bad_err


def test_AC_PLT_13_outside_git_repo_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    code, _, err = run_check(capsys)

    assert code == 2
    assert err.startswith("check_file_size: ")
