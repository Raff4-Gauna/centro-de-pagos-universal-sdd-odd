"""AC-PLT-19 (RN-PLT-13, C-06): shape of the gitleaks config, ``secrets`` job and hook (T-PLT-04).

No Docker. ``.gitleaks.toml`` keeps the default rules plus one own rule (Mercado Pago access
tokens, which the defaults miss) and one allowlist, the ``<ver .env: NAME>`` placeholder matched
against the captured *secret*. The ``secrets`` job pins the image by digest, fetches the whole
history and scans the commits of the event; its ``range`` step is executed with bash in a
throwaway repo: ``base..head`` on a PR, ``before..after`` on a push, the whole history of
``after`` on the first push of a ref (``before`` = 40 zeros). The gitleaks runs are in
``test_AC_PLT_19_gitleaks*.py``.

Today no default rule fires on the placeholder (it has spaces and ``<``), so the allowlist is
defensive: this test pins it to exactly that pattern.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import gitleaks_support as gl
import pytest
import yaml
from conftest import GitRepo

PLACEHOLDER_REGEX = r"<ver \.env: [A-Z][A-Z0-9_]*>"
PINNED_IMAGE = re.compile(r"^zricethezav/gitleaks:v8\.30\.1@sha256:[0-9a-f]{64}$")
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


def test_RN_PLT_13_gitleaks_config_is_defaults_plus_mp_rule_and_placeholder_allowlist() -> None:
    config = tomllib.loads(gl.GITLEAKS_CONFIG.read_text(encoding="utf-8"))

    assert config["extend"] == {"useDefault": True}
    assert config["rules"] == [MP_RULE]  # exact: no rule-level allowlist, path or entropy
    for prefix in ("APP_USR", "TEST"):
        assert re.fullmatch(MP_RULE_REGEX, gl.fake_mp_token(prefix))
    assert not re.search(MP_RULE_REGEX, f"MP_ACCESS_TOKEN={gl.PLACEHOLDER}")
    assert not re.search(MP_RULE_REGEX, "APP_USR-1234")  # a bare prefix in docs is no token
    assert "allowlist" not in config  # the deprecated single table would add a second allowlist
    [allowlist] = config["allowlists"]
    assert set(allowlist) <= {"description", "regexTarget", "regexes"}  # no paths/commits/stopwords
    assert allowlist["regexTarget"] == "secret"
    assert allowlist["regexes"] == [PLACEHOLDER_REGEX]
    assert re.search(PLACEHOLDER_REGEX, gl.PLACEHOLDER)
    assert not re.search(PLACEHOLDER_REGEX, "<ver .env: lower>")


def test_AC_PLT_19_secrets_job_scans_event_commits_with_pinned_image() -> None:
    job = gl.secrets_job()

    assert job["needs"] == "file-size"
    assert "permissions" not in job  # inherits the read-only token of the workflow
    assert "secrets." not in yaml.safe_dump(job)
    assert PINNED_IMAGE.match(job["env"]["GITLEAKS_IMAGE"])
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    range_env = gl.step(job, "range")["env"]
    assert range_env["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert range_env["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert range_env["BEFORE_SHA"] == "${{ github.event.before }}"
    assert range_env["AFTER_SHA"] == "${{ github.event.after }}"
    scan = gl.step(job, "scan")
    assert scan["env"] == {"LOG_OPTS": "${{ steps.range.outputs.log-opts }}"}
    assert '"$GITLEAKS_IMAGE" git /repo' in scan["run"]
    assert "--redact" in scan["run"]
    runs = [s.get("run", "") for s in job["steps"]]
    assert "pytest -c scripts/pytest.ini scripts/tests -m gitleaks" in runs


def test_AC_PLT_19_precommit_gitleaks_scans_staged_redacted_everywhere() -> None:
    config = yaml.safe_load(gl.PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
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
    code, log_opts = gl.run_range_step(
        repo, tmp_path, EVENT_NAME="pull_request", BASE_SHA=base, HEAD_SHA=head
    )
    assert (code, log_opts) == (0, f"{base}..{head}")


def test_AC_PLT_19_push_range_is_before_to_after(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path
) -> None:
    repo, base, head = two_commits
    code, log_opts = gl.run_range_step(
        repo, tmp_path, EVENT_NAME="push", BEFORE_SHA=base, AFTER_SHA=head
    )
    assert (code, log_opts) == (0, f"{base}..{head}")


@pytest.mark.parametrize(
    "before",
    [gl.ZERO_SHA, "1234567890abcdef1234567890abcdef12345678"],
    ids=["first-push-of-ref", "before-not-in-clone"],
)
def test_AC_PLT_19_push_without_usable_before_scans_whole_history(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, before: str
) -> None:
    repo, _, head = two_commits
    code, log_opts = gl.run_range_step(
        repo, tmp_path, EVENT_NAME="push", BEFORE_SHA=before, AFTER_SHA=head
    )
    assert (code, log_opts) == (0, head)


@pytest.mark.parametrize(
    "event",
    [
        {"EVENT_NAME": "pull_request", "BASE_SHA": "main", "HEAD_SHA": "HEAD"},
        {"EVENT_NAME": "push", "BEFORE_SHA": gl.ZERO_SHA, "AFTER_SHA": "HEAD --all"},
        {"EVENT_NAME": "workflow_dispatch"},
    ],
    ids=["ref-names", "injected-option", "unknown-event"],
)
def test_AC_PLT_19_range_rejects_anything_but_commit_shas(
    two_commits: tuple[GitRepo, str, str], tmp_path: Path, event: dict[str, str]
) -> None:
    repo, _, _ = two_commits
    code, log_opts = gl.run_range_step(repo, tmp_path, **event)
    assert code != 0
    assert log_opts == ""
