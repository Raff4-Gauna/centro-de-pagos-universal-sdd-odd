"""AC-PLT-19 (RN-PLT-13, C-06): gitleaks blocks a token-shaped secret, not a placeholder (T-PLT-04).

Two groups of tests:

* Shape and range (always run): ``.gitleaks.toml`` keeps the default rules plus one own rule
  (Mercado Pago access tokens, which the defaults miss) and one allowlist, the ``<ver .env: NAME>``
  placeholder matched against the captured *secret*; the ``secrets`` job pins
  the image by digest, fetches the whole history and scans the commits of the event. Its range step
  is executed with bash in a throwaway repo: ``base..head`` on a PR, ``before..after`` on a push,
  the whole history of ``after`` on the first push of a ref (``before`` = 40 zeros).
* ``gitleaks`` marker (Docker, the image of ``ci.yml``): deselected by default in
  ``scripts/pytest.ini``; the ``secrets`` job runs them with ``-m gitleaks``. The fake token is
  generated at runtime, so the repo never holds one (gitleaks would flag its own tests). One of
  them scans the whole history (``git log -p --all``) to show the config has no false positives.

Today no default rule fires on the placeholder (it has spaces and ``<``), so the allowlist is
defensive: the shape test pins it to exactly that pattern, and the same-line test proves it does not
hide a real token next to a placeholder (it would with ``regexTarget = "line"``).
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import string
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import GitRepo, clean_git_env

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

PLACEHOLDER_REGEX = r"<ver \.env: [A-Z][A-Z0-9_]*>"
PLACEHOLDER = "<ver .env: MP_ACCESS_TOKEN>"
# PREFIX-<app id>-<MMDDHH>-<32 hex>-<user id>; the repo only documents the prefixes (context/03,
# context/09).
MP_RULE_REGEX = r"\b((?:APP_USR|TEST)-\d{12,20}-\d{6}-[0-9a-fA-F]{32}-\d{6,12})\b"
MP_RULE: dict[str, object] = {
    "id": "mercadopago-access-token",
    "description": "Mercado Pago access token (APP_USR- or TEST- credentials)",
    "regex": MP_RULE_REGEX,
    "secretGroup": 1,
    "keywords": ["app_usr-", "test-"],
}
MP_PREFIXES = ("APP_USR", "TEST")
PINNED_IMAGE = re.compile(r"^zricethezav/gitleaks:v8\.30\.1@sha256:[0-9a-f]{64}$")
ZERO_SHA = "0" * 40


def secrets_job() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["secrets"]


def step(job: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in job["steps"] if s.get("id") == step_id)


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


def test_RN_PLT_13_gitleaks_config_is_defaults_plus_mp_rule_and_placeholder_allowlist() -> None:
    config = tomllib.loads(GITLEAKS_CONFIG.read_text(encoding="utf-8"))

    assert config["extend"] == {"useDefault": True}
    assert config["rules"] == [MP_RULE]  # exact: no rule-level allowlist, path or entropy
    for prefix in MP_PREFIXES:
        assert re.fullmatch(MP_RULE_REGEX, fake_mp_token(prefix))
    assert not re.search(MP_RULE_REGEX, f"MP_ACCESS_TOKEN={PLACEHOLDER}")
    assert not re.search(MP_RULE_REGEX, "APP_USR-1234")  # a bare prefix in docs is no token
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
    assert any("-m gitleaks" in run and "test_AC_PLT_19_gitleaks.py" in run for run in runs)


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


# --- gitleaks in Docker (marker `gitleaks`) ------------------------------------------------------

Scan = Callable[[str], subprocess.CompletedProcess[str]]


@pytest.fixture(params=["pre-commit-staged", "ci-pull-request"])
def scan(
    request: pytest.FixtureRequest, two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> Scan:
    """Stage (pre-commit) or commit on top of ``head`` and scan it the way that path does."""
    repo, _, head = two_commits
    config_dir = tmp_path / "gitleaks-config"
    config_dir.mkdir()
    shutil.copyfile(GITLEAKS_CONFIG, config_dir / ".gitleaks.toml")

    def run(content: str) -> subprocess.CompletedProcess[str]:
        repo.write_bytes("config.txt", content.encode("utf-8"))
        if request.param == "pre-commit-staged":
            mode = ["--pre-commit", "--staged"]
        else:
            code, log_opts = run_range_step(
                repo, tmp_path, EVENT_NAME="pull_request", BASE_SHA=head, HEAD_SHA=commit(repo, "x")
            )
            assert code == 0
            mode = [f"--log-opts={log_opts}"]
        mounts = ["-v", f"{repo.root}:/repo", "-v", f"{config_dir}:/cfg:ro"]
        docker = ["docker", "run", "--rm", *mounts]
        image = secrets_job()["env"]["GITLEAKS_IMAGE"]
        options = ["--config", "/cfg/.gitleaks.toml", "--redact", "--no-banner", "--verbose"]
        return subprocess.run(  # noqa: S603 - fixed argv, test-only; docker from PATH
            [*docker, image, "git", "/repo", *options, *mode],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )

    return run


@pytest.mark.gitleaks
def test_AC_PLT_19_token_shaped_secret_is_detected(scan: Scan) -> None:
    token = fake_github_token()
    result = scan(f"GITHUB_TOKEN={token}\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "github-pat" in output
    assert token not in output  # --redact


@pytest.mark.gitleaks
def test_AC_PLT_19_env_placeholder_is_not_flagged(scan: Scan) -> None:
    result = scan(
        f"MP_ACCESS_TOKEN={PLACEHOLDER}\n| Access Token (prueba) | `{PLACEHOLDER}` |\n"
        f'access_token = "{PLACEHOLDER}"\n'
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.gitleaks
def test_AC_PLT_19_placeholder_and_real_token_on_same_line_still_fails(scan: Scan) -> None:
    token = fake_github_token()
    result = scan(f"MP_ACCESS_TOKEN={PLACEHOLDER} GITHUB_TOKEN={token}\n")

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert token not in output


@pytest.mark.gitleaks
@pytest.mark.parametrize("prefix", MP_PREFIXES)
def test_AC_PLT_19_mercadopago_token_is_detected_in_every_form(scan: Scan, prefix: str) -> None:
    token = fake_mp_token(prefix)
    forms = [
        f"MP_ACCESS_TOKEN={token}",
        f'curl -H "Authorization: Bearer {token}"',
        f'{{"access_token": "{token}"}}',
        f"https://api.mercadopago.com/pos?access_token={token}",
    ]
    result = scan("".join(f"{form}\n" for form in forms))

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert len(re.findall(r"RuleID:\s+mercadopago-access-token", output)) == len(forms), output
    assert token not in output


@pytest.mark.gitleaks
def test_AC_PLT_19_repo_history_has_no_findings(tmp_path: Path, empty_git_config: Path) -> None:
    # Every commit of every ref (with fetch-depth 0 in CI): the own rule and the allowlist give no
    # false positives on the real content, placeholders included.
    history = subprocess.run(
        ["git", "log", "-p", "--all", "--no-color", "--no-ext-diff"],  # noqa: S607 - git from PATH
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        env=clean_git_env(empty_git_config),
    ).stdout
    assert history
    config_dir = tmp_path / "gitleaks-config"
    config_dir.mkdir()
    shutil.copyfile(GITLEAKS_CONFIG, config_dir / ".gitleaks.toml")
    image = secrets_job()["env"]["GITLEAKS_IMAGE"]
    docker = ["docker", "run", "--rm", "-i", "-v", f"{config_dir}:/cfg:ro"]
    options = ["--config", "/cfg/.gitleaks.toml", "--redact", "--no-banner", "--verbose"]
    result = subprocess.run(  # noqa: S603 - fixed argv, test-only; docker from PATH
        [*docker, image, "stdin", *options],
        input=history,
        capture_output=True,
        check=False,
        timeout=300,
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert result.returncode == 0, output
