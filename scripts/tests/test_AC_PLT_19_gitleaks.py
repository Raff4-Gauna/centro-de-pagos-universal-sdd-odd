"""AC-PLT-19 (RN-PLT-13, C-06): gitleaks blocks a token-shaped secret, not a placeholder (T-PLT-04).

``.gitleaks.toml`` keeps the default rules with one allowlist, the ``<ver .env: NAME>`` placeholder
matched against the captured *secret*; the ``secrets`` job pins the image by digest, fetches the
whole history and scans the commits of the event. Its range step is executed with bash in a
throwaway repo: ``base..head`` on a PR, ``before..after`` on a push, the whole history of ``after``
on the first push of a ref (``before`` = 40 zeros). The gitleaks runs themselves (Docker, fake token
generated at runtime) join this module with the ``gitleaks`` marker.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import GitRepo

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

PLACEHOLDER_REGEX = r"<ver \.env: [A-Z][A-Z0-9_]*>"
PLACEHOLDER = "<ver .env: MP_ACCESS_TOKEN>"
PINNED_IMAGE = re.compile(r"^zricethezav/gitleaks:v8\.30\.1@sha256:[0-9a-f]{64}$")
ZERO_SHA = "0" * 40


def secrets_job() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["secrets"]


def step(job: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in job["steps"] if s.get("id") == step_id)


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


def commit(repo: GitRepo, message: str) -> str:
    repo.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)
    return git_out(repo, "rev-parse", "HEAD")


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
        pytest.fail("bash not found: the range step of the secrets job cannot be checked")
    return found


def run_range_step(repo: GitRepo, tmp_path: Path, **event: str) -> tuple[int, str]:
    """Run the ``range`` step of the ``secrets`` job like the runner (bash -eo pipefail)."""
    script = tmp_path / "range.sh"
    script.write_text(step(secrets_job(), "range")["run"], encoding="utf-8", newline="\n")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    names = ("EVENT_NAME", "BASE_SHA", "HEAD_SHA", "BEFORE_SHA", "AFTER_SHA")
    env = {**repo.env, **{name: event.get(name, "") for name in names}}
    env["GITHUB_OUTPUT"] = output.as_posix()
    completed = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [find_bash(), "--noprofile", "--norc", "-eo", "pipefail", script.as_posix()],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    values = dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if line
    )
    return completed.returncode, values.get("log-opts", "")


@pytest.fixture
def two_commits(git_repo: GitRepo) -> tuple[GitRepo, str, str]:
    git_repo.write_bytes("README.md", b"base\n")
    base = commit(git_repo, "base")
    git_repo.write_bytes("notes.txt", b"change\n")
    head = commit(git_repo, "change")
    return git_repo, base, head


def test_RN_PLT_13_gitleaks_config_is_defaults_plus_placeholder_allowlist() -> None:
    config = tomllib.loads(GITLEAKS_CONFIG.read_text(encoding="utf-8"))

    assert config["extend"] == {"useDefault": True}
    assert "allowlist" not in config  # the deprecated single table would add a second allowlist
    [allowlist] = config["allowlists"]
    assert set(allowlist) <= {"description", "regexTarget", "regexes"}  # no paths/commits/stopwords
    assert allowlist["regexTarget"] == "secret"
    assert allowlist["regexes"] == [PLACEHOLDER_REGEX]
    assert re.search(PLACEHOLDER_REGEX, PLACEHOLDER)
    assert not re.search(PLACEHOLDER_REGEX, "<ver .env: lower>")


def test_AC_PLT_19_secrets_job_scans_event_commits_with_pinned_image() -> None:
    job = secrets_job()

    assert job["needs"] == "file-size"
    assert "permissions" not in job  # inherits the read-only token of the workflow
    assert "secrets." not in yaml.safe_dump(job)
    assert PINNED_IMAGE.match(job["env"]["GITLEAKS_IMAGE"])
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    range_env = step(job, "range")["env"]
    assert range_env["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert range_env["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert range_env["BEFORE_SHA"] == "${{ github.event.before }}"
    assert range_env["AFTER_SHA"] == "${{ github.event.after }}"
    runs = [s.get("run", "") for s in job["steps"]]
    scan = next(run for run in runs if "docker run" in run)
    assert '"$GITLEAKS_IMAGE" git /repo' in scan
    assert "--redact" in scan
    assert '--log-opts="$LOG_OPTS"' in scan


def test_AC_PLT_19_precommit_gitleaks_scans_staged_redacted_everywhere() -> None:
    config = yaml.safe_load(PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    [repo] = [r for r in config["repos"] if r["repo"] == "https://github.com/gitleaks/gitleaks"]
    [hook] = repo["hooks"]

    assert repo["rev"] == "83d9cd684c87d95d656c1458ef04895a7f1cbd8e"  # tag v8.30.1
    assert hook["id"] == "gitleaks"
    for flag in ("git", "--pre-commit", "--staged", "--redact", "--config .gitleaks.toml"):
        assert flag in hook["entry"]
    # Q-055: gitleaks also scans context/legacy-source/; no hook-level or global filter.
    assert not {"exclude", "files", "types", "types_or"} & set(hook)
    assert not {"exclude", "files"} & set(config)


def test_AC_PLT_19_pull_request_range_is_base_to_head(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> None:
    repo, base, head = two_commits
    code, log_opts = run_range_step(
        repo, tmp_path, EVENT_NAME="pull_request", BASE_SHA=base, HEAD_SHA=head
    )
    assert (code, log_opts) == (0, f"{base}..{head}")


def test_AC_PLT_19_push_range_is_before_to_after(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> None:
    repo, base, head = two_commits
    code, log_opts = run_range_step(
        repo, tmp_path, EVENT_NAME="push", BEFORE_SHA=base, AFTER_SHA=head
    )
    assert (code, log_opts) == (0, f"{base}..{head}")


@pytest.mark.parametrize(
    "before",
    [ZERO_SHA, "1234567890abcdef1234567890abcdef12345678"],
    ids=["first-push-of-ref", "before-not-in-clone"],
)
def test_AC_PLT_19_push_without_usable_before_scans_whole_history(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, before: str
) -> None:
    repo, _, head = two_commits
    code, log_opts = run_range_step(
        repo, tmp_path, EVENT_NAME="push", BEFORE_SHA=before, AFTER_SHA=head
    )
    assert (code, log_opts) == (0, head)


@pytest.mark.parametrize(
    "event",
    [
        {"EVENT_NAME": "pull_request", "BASE_SHA": "main", "HEAD_SHA": "HEAD"},
        {"EVENT_NAME": "push", "BEFORE_SHA": ZERO_SHA, "AFTER_SHA": "HEAD --all"},
        {"EVENT_NAME": "workflow_dispatch"},
    ],
    ids=["ref-names", "injected-option", "unknown-event"],
)
def test_AC_PLT_19_range_rejects_anything_but_commit_shas(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, event: dict[str, str]
) -> None:
    repo, _, _ = two_commits
    code, log_opts = run_range_step(repo, tmp_path, **event)
    assert code != 0
    assert log_opts == ""
