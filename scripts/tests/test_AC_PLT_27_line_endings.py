"""AC-PLT-27 (RNF-PLT-05): CRLF never reaches a ``.sh``/``Dockerfile``; and the pre-commit config.

``.gitattributes`` stores them LF (checked with ``git check-attr`` on the real file and by adding a
CRLF file to a throwaway repo); pre-commit's ``mixed-line-ending --fix=lf`` rewrites the working
copy. The rest of this module pins the shape of ``.pre-commit-config.yaml`` (RF-PLT-12, design.md
sec. 3.6): fast hooks only (RNF-PLT-04), ``check_file_size.py`` on code files (AC-PLT-13), remote
repos pinned by commit SHA, and context/legacy-source/ skipped by every hook except gitleaks
(Q-055; gitleaks itself is checked in test_AC_PLT_19_gitleaks.py). T-PLT-04.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from conftest import GitRepo, clean_git_env

REPO_ROOT = Path(__file__).resolve().parents[2]
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

LF_PATHS = ("run.sh", "infra/scripts/run.sh", "Dockerfile", "backend/Dockerfile")
LEGACY_FILE = "context/legacy-source/mpqr/config.py"
# Hooks that must never run in pre-commit: test suites, type-check, migrations (CI only).
SLOW_TOOLS = re.compile(r"pytest|vitest|jest|mypy|tsc|manage\.py|makemigrations|migrate")
SHA = re.compile(r"^[0-9a-f]{40}$")


def load_config() -> dict[str, Any]:
    return yaml.safe_load(PRECOMMIT_CONFIG.read_text(encoding="utf-8"))


def hooks(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


def slow_hook_errors(config: dict[str, Any]) -> list[str]:
    errors = []
    for hook_id, hook in hooks(config).items():
        text = " ".join([hook_id, str(hook.get("entry", "")), *map(str, hook.get("args", []))])
        if SLOW_TOOLS.search(text):
            errors.append(f"{hook_id} runs a slow tool: {text}")
    return errors


def skips(hook: dict[str, Any], path: str) -> bool:
    """pre-commit semantics: ``exclude`` is a Python regex searched in the repo-relative path."""
    return bool(re.search(hook.get("exclude", "^$"), path))


def test_AC_PLT_27_gitattributes_forces_lf_for_sh_and_dockerfile(empty_git_config: Path) -> None:
    completed = subprocess.run(  # noqa: S603 - fixed argv, test-only
        ["git", "check-attr", "text", "eol", "--", *LF_PATHS],  # noqa: S607 - git from PATH
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=clean_git_env(empty_git_config),
    )
    attributes = set(completed.stdout.splitlines())
    for path in LF_PATHS:
        assert f"{path}: text: auto" in attributes
        assert f"{path}: eol: lf" in attributes


def test_AC_PLT_27_crlf_shell_script_and_dockerfile_are_stored_lf(git_repo: GitRepo) -> None:
    shutil.copyfile(GITATTRIBUTES, git_repo.root / ".gitattributes")
    git_repo.write_bytes("run.sh", b"#!/bin/sh\r\necho ok\r\n")
    git_repo.write_bytes("Dockerfile", b"FROM scratch\r\nCOPY run.sh /\r\n")

    completed = subprocess.run(
        ["git", "ls-files", "--eol", "--", "run.sh", "Dockerfile"],  # noqa: S607 - git from PATH
        cwd=git_repo.root,
        capture_output=True,
        text=True,
        check=True,
        env=git_repo.env,
    )
    index_eol = [line.split()[0] for line in completed.stdout.splitlines()]
    assert index_eol == ["i/lf", "i/lf"]


def test_AC_PLT_27_precommit_has_mixed_line_ending_fix_lf() -> None:
    config = load_config()
    url = "https://github.com/pre-commit/pre-commit-hooks"
    [repo] = [r for r in config["repos"] if r["repo"] == url]
    hook = next(h for h in repo["hooks"] if h["id"] == "mixed-line-ending")

    assert hook["args"] == ["--fix=lf"]
    assert not {"files", "types", "types_or"} & set(hook)
    assert not any(skips(hook, path) for path in LF_PATHS)


def test_RNF_PLT_04_precommit_has_no_tests_nor_migrations() -> None:
    assert slow_hook_errors(load_config()) == []
    # Control: the check flags each kind of slow hook.
    synthetic = {
        "repos": [
            {
                "repo": "local",
                "hooks": [
                    {"id": "tests", "entry": "pytest -q"},
                    {"id": "types", "entry": "mypy ."},
                    {"id": "db", "entry": "python manage.py makemigrations --check"},
                ],
            }
        ]
    }
    assert len(slow_hook_errors(synthetic)) == 3


def test_RF_PLT_12_precommit_runs_lf_ruff_file_size_and_gitleaks() -> None:
    present = set(hooks(load_config()))
    required = {"mixed-line-ending", "ruff-check", "ruff-format", "check-file-size", "gitleaks"}
    assert required <= present
    assert {"no-commit-to-branch", "detect-private-key", "check-added-large-files"} <= present


def test_AC_PLT_13_precommit_runs_check_file_size_on_code_files() -> None:
    hook = hooks(load_config())["check-file-size"]

    assert hook["entry"] == "python scripts/check_file_size.py"
    assert hook["language"] == "python"
    assert hook["types_or"] == ["python", "ts", "tsx", "jsx"]
    assert "additional_dependencies" not in hook  # stdlib only


def test_RF_PLT_12_remote_hook_repos_are_pinned_by_commit_sha() -> None:
    remote = [repo for repo in load_config()["repos"] if repo["repo"] != "local"]
    assert remote, "no remote hook repo: the check would pass on nothing"
    assert [repo["repo"] for repo in remote if not SHA.match(str(repo["rev"]))] == []


def test_RF_PLT_12_trailing_whitespace_skips_markdown() -> None:
    hook = hooks(load_config())["trailing-whitespace"]
    assert skips(hook, "specs/00-platform/design.md")
    assert not skips(hook, "scripts/check_file_size.py")


def test_RF_PLT_12_every_file_hook_but_gitleaks_skips_legacy_source() -> None:
    # Q-055: legacy evidence is never rewritten nor linted; gitleaks still scans it.
    not_file_hooks = {"gitleaks", "no-commit-to-branch"}
    file_hooks = {k: v for k, v in hooks(load_config()).items() if k not in not_file_hooks}
    assert [hook_id for hook_id, hook in file_hooks.items() if not skips(hook, LEGACY_FILE)] == []
    assert [hook_id for hook_id, hook in file_hooks.items() if skips(hook, "scripts/x.py")] == []
