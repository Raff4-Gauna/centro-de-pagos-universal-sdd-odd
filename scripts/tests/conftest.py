"""Shared fixtures for the ``scripts/`` tests: throwaway git repositories (T-PLT-01).

Each repository lives under pytest's ``tmp_path``; nothing touches the real repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def clean_git_env() -> dict[str, str]:
    """Environment without ``GIT_*`` variables, so a parent git process (hooks) cannot leak in."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argv, test-only
        ["git", *args],  # noqa: S607 - git is resolved from PATH on purpose
        cwd=repo,
        check=True,
        capture_output=True,
        env=clean_git_env(),
    )


class GitRepo:
    """A temporary git repository with helpers to create (and optionally track) files."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(
        self, rel_path: str, lines: int, *, track: bool = True, final_newline: bool = True
    ) -> Path:
        """Create ``rel_path`` with exactly ``lines`` physical lines; ``git add`` it if asked."""
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "x = 1\n" * lines
        if not final_newline and content:
            content = content[:-1]
        path.write_text(content, encoding="utf-8", newline="\n")
        if track:
            run_git(self.root, "add", "--", rel_path)
        return path


def init_repo(root: Path) -> GitRepo:
    root.mkdir(parents=True, exist_ok=True)
    run_git(root, "init", "--quiet")
    run_git(root, "config", "core.autocrlf", "false")
    return GitRepo(root)


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitRepo:
    """Empty git repo; the test's working directory is its root."""
    repo = init_repo(tmp_path / "repo")
    monkeypatch.chdir(repo.root)
    for key in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(key)
    return repo


@pytest.fixture
def non_ascii_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GitRepo:
    """Empty git repo under a non-ASCII path, like the real ``Programación-2026`` checkout."""
    repo = init_repo(tmp_path / "Programación-2026" / "repo")
    monkeypatch.chdir(repo.root)
    for key in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(key)
    return repo
