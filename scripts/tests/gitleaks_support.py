"""Helpers for the AC-PLT-19 tests: the ``secrets`` job, its bash steps, gitleaks runs (T-PLT-04).

The tests run the **real** commands: the ``run`` of a ``secrets`` step from ``ci.yml`` (with bash,
as the runner does) and the ``entry`` of the pre-commit hook, both against a throwaway repo. So a
flag added to or dropped from ``ci.yml`` or ``.pre-commit-config.yaml`` changes what the tests see;
there is no copy of the gitleaks options here. Fake secrets are generated at runtime, never stored.
"""

from __future__ import annotations

import base64
import os
import re
import secrets
import shlex
import shutil
import string
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

if TYPE_CHECKING:  # conftest imports this module for its fixtures
    from conftest import GitRepo

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
PLACEHOLDER = "<ver .env: MP_ACCESS_TOKEN>"
ZERO_SHA = "0" * 40
DOCKER_TIMEOUT = 300


# One example file per directory/path entry of the default `[allowlist] paths` of gitleaks v8.30.1
# (Q-062). Each must match its entry, so gitleaks never scans it, and must fail the guard step
# `no-allowlisted-paths`. A new entry in a newer gitleaks needs a new example here.
ALLOWLISTED_PATH_EXAMPLES = {
    r"gitleaks\.toml": "a/gitleaks.toml/b.py",
    r"go\.(?:mod|sum|work(?:\.sum)?)$": "tools/go.sum",
    r"(?:^|/)vendor/modules\.txt$": "x/vendor/modules.txt",
    r"(?:^|/)vendor/(?:github\.com|golang\.org/x|google\.golang\.org|gopkg\.in|istio\.io|k8s\.io"
    r"|sigs\.k8s\.io)(?:/.*)?$": "vendor/github.com/acme/lib/k.go",
    r"(?:^|/)gradlew(?:\.bat)?$": "android/gradlew.bat",
    r"(?:^|/)gradle\.lockfile$": "android/gradle.lockfile",
    r"(?:^|/)mvnw(?:\.cmd)?$": "java/mvnw",
    r"(?:^|/)\.mvn/wrapper/MavenWrapperDownloader\.java$": (
        ".mvn/wrapper/MavenWrapperDownloader.java"
    ),
    r"(?:^|/)node_modules(?:/.*)?$": "x/node_modules/c.py",
    r"(?:^|/)(?:deno\.lock|npm-shrinkwrap\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$": (
        "web/package-lock.json"
    ),
    r"(?:^|/)bower_components(?:/.*)?$": "web/bower_components/e.py",
    r"(?:^|/)(?:angular|bootstrap|jquery(?:-?ui)?|plotly|swagger-?ui)[a-zA-Z0-9.-]*(?:\.min)?\.js"
    r"(?:\.map)?$": "static/jquery-3.7.1.min.js",
    r"(?:^|/)javascript\.json$": "conf/javascript.json",
    r"(?:^|/)(?:Pipfile|poetry)\.lock$": "py/poetry.lock",
    r"(?i)(?:^|/)(?:v?env|virtualenv)/lib(?:64)?(?:/.*)?$": "virtualenv/lib64/a.py",
    r"(?i)(?:^|/)(?:lib(?:64)?/python[23](?:\.\d{1,2})+|python/[23](?:\.\d{1,2})+/lib(?:64)?)"
    r"(?:/.*)?$": "lib/python3.12/d.py",
    r"(?i)(?:^|/)[a-z0-9_.]+-[0-9.]+\.dist-info(?:/.+)?$": "pkg-1.0.dist-info/e.py",
    r"(?:^|/)vendor/(?:bundle|ruby)(?:/.*?)?$": "vendor/bundle/f.rb",
    r"verification-metadata\.xml": "gradle/verification-metadata.xml",
    r"Database.refactorlog": "db/Database.refactorlog",
    # git ignores a `.git` path component ("Ignoring path"), so this one can never reach the guard.
    r"(?:^|/)\.git$": "sub/.git",
}
UNTRACKABLE_EXAMPLES = {"sub/.git"}


def secrets_job() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["secrets"]


def step(job: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in job["steps"] if s.get("id") == step_id)


def gitleaks_image() -> str:
    return secrets_job()["env"]["GITLEAKS_IMAGE"]


def guard_entries() -> list[str]:
    """The regexes of the `skipped=( ... )` array of the guard step, in order."""
    run = step(secrets_job(), "no-allowlisted-paths")["run"]
    block = run[run.index("skipped=(") : run.index("\n)", run.index("skipped=("))]
    return re.findall(r"^\s+'(.+)'$", block, re.MULTILINE)


def is_extension_entry(entry: str) -> bool:
    """A file-extension entry (images, fonts, binaries): `\\.` first and no directory part."""
    return bool(re.match(r"^(\(\?i\))?\\\.", entry)) and "/" not in entry


def gitleaks_hook() -> dict[str, Any]:
    config = yaml.safe_load(PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    return next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "gitleaks")


def git_out(repo: GitRepo, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv, test-only
        ["git", *args],  # noqa: S607 - git is resolved from PATH on purpose
        cwd=repo.root,
        check=True,
        capture_output=True,
        text=True,
        env=repo.env,
    )
    return completed.stdout.strip()


def commit(repo: GitRepo, message: str, *args: str) -> str:
    """Commit what is staged (``args`` go to ``git commit``); return the new HEAD."""
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    repo.git(*identity, "commit", "-q", "-m", message, *args)
    return git_out(repo, "rev-parse", "HEAD")


def fake_github_token() -> str:
    """A GitHub PAT shape (rule ``github-pat``), random per run; never a literal in the repo."""
    alphabet = string.ascii_letters + string.digits
    return "ghp" + "_" + "".join(secrets.choice(alphabet) for _ in range(36))


def fake_mp_token(prefix: str) -> str:
    """A Mercado Pago access token shape with random parts, built at runtime."""

    def digits(count: int) -> str:
        return "".join(secrets.choice(string.digits) for _ in range(count))

    hex32 = "".join(secrets.choice("0123456789abcdef") for _ in range(32))
    month, day, hour = secrets.randbelow(12) + 1, secrets.randbelow(28) + 1, secrets.randbelow(24)
    stamp = f"{month:02d}{day:02d}{hour:02d}"
    return f"{prefix}-{digits(16)}-{stamp}-{hex32}-{digits(10)}"


def fake_rsa_private_key(*inner_lines: str) -> str:
    """PEM framing of an RSA private key with a random body (rule ``private-key``).

    The header is split so neither gitleaks nor ``detect-private-key`` flags this source file.
    ``inner_lines`` are inserted in the middle of the body, as an attacker would hide a placeholder.
    """
    body = base64.b64encode(secrets.token_bytes(1190)).decode("ascii")
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    half = len(lines) // 2
    lines[half:half] = list(inner_lines)
    kind = "RSA " + "PRIVATE KEY"
    return "\n".join([f"-----BEGIN {kind}-----", *lines, f"-----END {kind}-----"]) + "\n"


def find_bash() -> str:
    """bash as the runner has it; on Windows Git for Windows' one, never the WSL launcher."""
    if os.name == "nt":
        exec_path = subprocess.run(
            ["git", "--exec-path"],  # noqa: S607 - git is resolved from PATH on purpose
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        git_home = Path(exec_path).parents[2]
        candidates = [git_home / "bin" / "bash.exe", git_home / "usr" / "bin" / "bash.exe"]
        found = next((str(path) for path in candidates if path.is_file()), None)
    else:
        found = shutil.which("bash")
    if found is None:
        pytest.fail("bash not found: the steps of the secrets job cannot be checked")
    return found


def run_step(
    repo: GitRepo, tmp_path: Path, step_id: str, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Run a ``secrets`` step like the runner (bash -eo pipefail); return it and its outputs."""
    script = tmp_path / f"{step_id}.sh"
    script.write_text(step(secrets_job(), step_id)["run"], encoding="utf-8", newline="\n")
    output = tmp_path / f"{step_id}.github_output"
    output.write_text("", encoding="utf-8")
    full_env = {**repo.env, **env, "GITHUB_OUTPUT": output.as_posix()}
    # Git Bash would rewrite "/repo" and "C:/x:/repo:ro" in the docker arguments.
    full_env["MSYS_NO_PATHCONV"] = "1"
    completed = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [find_bash(), "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()],
        cwd=repo.root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=full_env,
        check=False,
        timeout=DOCKER_TIMEOUT,
    )
    lines = output.read_text(encoding="utf-8").splitlines()
    return completed, dict(line.split("=", 1) for line in lines if line)


def run_range_step(repo: GitRepo, tmp_path: Path, **event: str) -> tuple[int, str]:
    names = ("EVENT_NAME", "BASE_SHA", "HEAD_SHA", "BEFORE_SHA", "AFTER_SHA")
    completed, outputs = run_step(
        repo, tmp_path, "range", {name: event.get(name, "") for name in names}
    )
    return completed.returncode, outputs.get("log-opts", "")


def install_config(repo: GitRepo) -> None:
    """The repo's ``.gitleaks.toml`` at the root of the throwaway repo, untracked."""
    shutil.copyfile(GITLEAKS_CONFIG, repo.root / ".gitleaks.toml")


def ci_scan(
    repo: GitRepo, tmp_path: Path, base: str, head: str
) -> subprocess.CompletedProcess[str]:
    """The ``range`` and ``scan`` steps of ``secrets`` for a PR from ``base`` to ``head``."""
    code, log_opts = run_range_step(
        repo, tmp_path, EVENT_NAME="pull_request", BASE_SHA=base, HEAD_SHA=head
    )
    assert code == 0
    install_config(repo)
    env = {
        "GITHUB_WORKSPACE": repo.root.as_posix(),
        "GITLEAKS_IMAGE": gitleaks_image(),
        "LOG_OPTS": log_opts,
    }
    return run_step(repo, tmp_path, "scan", env)[0]


def hook_scan(repo: GitRepo) -> subprocess.CompletedProcess[str]:
    """The pre-commit hook's ``entry`` (staged diff) run in the pinned image, from the repo root."""
    install_config(repo)
    program, *args = shlex.split(gitleaks_hook()["entry"])
    assert program == "gitleaks"
    docker = ["docker", "run", "--rm", "-v", f"{repo.root}:/repo", "-w", "/repo", gitleaks_image()]
    return subprocess.run(  # noqa: S603 - fixed argv, test-only; docker from PATH
        [*docker, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=DOCKER_TIMEOUT,
    )
