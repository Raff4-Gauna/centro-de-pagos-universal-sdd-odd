"""Shared fixtures for the ``scripts/`` tests: throwaway git repositories (T-PLT-01).

Each repository lives under pytest's ``tmp_path``; nothing touches the real repo. git runs isolated
from the host: no inherited ``GIT_*`` variables (hooks), no system config, an empty global config.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def clean_git_env(empty_config: Path) -> dict[str, str]:
    """Environment without inherited ``GIT_*`` variables, system config off, empty global config."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = str(empty_config)
    return env


def isolate_git_env(monkeypatch: pytest.MonkeyPatch, empty_config: Path) -> None:
    """Apply ``clean_git_env`` to this process, for in-process calls to the scripts."""
    for key in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))


class GitRepo:
    """A temporary git repository with helpers to create (and optionally track) files."""

    def __init__(self, root: Path, env: dict[str, str]) -> None:
        self.root = root
        self.env = env

    def git(self, *args: str) -> None:
        subprocess.run(  # noqa: S603 - fixed argv, test-only
            ["git", *args],  # noqa: S607 - git is resolved from PATH on purpose
            cwd=self.root,
            check=True,
            capture_output=True,
            env=self.env,
        )

    def write_bytes(self, rel_path: str, data: bytes, *, track: bool = True) -> Path:
        """Create ``rel_path`` with exactly ``data``; ``git add`` it if asked."""
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if track:
            self.git("add", "--", rel_path)
        return path

    def write(
        self, rel_path: str, lines: int, *, track: bool = True, final_newline: bool = True
    ) -> Path:
        """Create ``rel_path`` with exactly ``lines`` physical LF lines; ``git add`` it if asked."""
        content = b"x = 1\n" * lines
        if not final_newline and content:
            content = content[:-1]
        return self.write_bytes(rel_path, content, track=track)


def init_repo(root: Path, empty_config: Path) -> GitRepo:
    root.mkdir(parents=True, exist_ok=True)
    repo = GitRepo(root, clean_git_env(empty_config))
    repo.git("init", "--quiet")
    # Byte-exact files: no CRLF/LF conversion on `git add`.
    repo.git("config", "core.autocrlf", "false")
    return repo


@pytest.fixture(scope="session")
def empty_git_config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("gitconfig") / "empty.gitconfig"
    path.write_bytes(b"")
    return path


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty_git_config: Path) -> GitRepo:
    """Empty git repo; the test's working directory is its root."""
    isolate_git_env(monkeypatch, empty_git_config)
    repo = init_repo(tmp_path / "repo", empty_git_config)
    monkeypatch.chdir(repo.root)
    return repo


@pytest.fixture
def non_ascii_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty_git_config: Path
) -> GitRepo:
    """Empty git repo under a non-ASCII path, like the real ``Programación-2026`` checkout."""
    isolate_git_env(monkeypatch, empty_git_config)
    repo = init_repo(tmp_path / "Programación-2026" / "repo", empty_git_config)
    monkeypatch.chdir(repo.root)
    return repo
