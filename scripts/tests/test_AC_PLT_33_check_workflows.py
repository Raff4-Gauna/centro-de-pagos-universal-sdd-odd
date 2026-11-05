"""AC-PLT-33 (RN-PLT-18, RF-PLT-11): ``check_workflows.py`` fails naming file and rule (T-PLT-05).

Every rule of design.md §3.5 has a synthetic workflow (inline YAML) that breaks only that rule, so a
rule that silently passes on anything fails here; the real ``ci.yml`` and the composite action pass.
"""

from __future__ import annotations

from pathlib import Path

import check_workflows as cw
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DIGEST = "c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"

# A workflow that breaks no rule. Each test changes one thing of it.
GOOD = f"""\
name: good
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@{SHA} # v7.0.1
      - uses: ./.github/actions/setup
      - name: token for the API
        if: github.event_name == 'pull_request'
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
        run: echo "${{{{ needs.secrets.result }}}} no secrets here"
"""


SETUP_ACTION = "name: setup\nruns:\n  using: composite\n  steps: []\n"


def write(root: Path, text: str, name: str = "x.yml", folder: str = ".github/workflows") -> Path:
    """Write a file; the first call also writes the local action ``GOOD`` uses (uses-local)."""
    setup = root / ".github/actions/setup/action.yml"
    if not setup.exists():
        setup.parent.mkdir(parents=True, exist_ok=True)
        setup.write_text(SETUP_ACTION, encoding="utf-8")
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def rules_of(root: Path) -> set[str]:
    return {violation.rule for violation in cw.check_repo(root)}


def fails_naming(
    root: Path, capsys: pytest.CaptureFixture[str], rule: str, name: str = "x.yml"
) -> str:
    """Run the CLI: exit 1 and a stderr line naming the file and the rule."""
    assert cw.main(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if f"[{rule}]" in line]
    assert lines, err
    assert all(name in line for line in lines)
    return err


def test_AC_PLT_33_good_synthetic_workflow_passes(tmp_path: Path) -> None:
    write(tmp_path, GOOD)
    assert cw.check_repo(tmp_path) == []


def test_AC_PLT_33_pull_request_target_fails_naming_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, GOOD.replace("  pull_request:\n", "  pull_request_target:\n"), "evil.yml")
    fails_naming(tmp_path, capsys, "forbidden-trigger", "evil.yml")


def test_AC_PLT_33_workflow_run_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, GOOD.replace("  pull_request:\n", "  workflow_run:\n"))
    fails_naming(tmp_path, capsys, "forbidden-trigger")


@pytest.mark.parametrize(
    "on",
    ["on: pull_request_target", "on: [push, workflow_run]", '"on":\n  pull_request_target: {}'],
    ids=["string", "list", "quoted-key"],
)
def test_AC_PLT_33_forbidden_trigger_in_any_form_fails(tmp_path: Path, on: str) -> None:
    write(tmp_path, GOOD.replace("on:\n  pull_request:\n    branches: [main]", on))
    assert "forbidden-trigger" in rules_of(tmp_path)


def test_AC_PLT_33_missing_top_level_permissions_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, GOOD.replace("permissions:\n  contents: read\n", ""))
    fails_naming(tmp_path, capsys, "permissions-missing")


@pytest.mark.parametrize(
    "permissions",
    ["permissions: write-all", "permissions:\n  contents: write", "permissions:\n  issues: admin"],
    ids=["write-all", "scope-write", "invalid-level"],
)
def test_AC_PLT_33_write_token_by_default_fails_naming_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], permissions: str
) -> None:
    write(tmp_path, GOOD.replace("permissions:\n  contents: read", permissions), "writer.yml")
    fails_naming(tmp_path, capsys, "permissions-top-level", "writer.yml")


@pytest.mark.parametrize(
    "permissions", ["permissions: read-all", "permissions: {}", "permissions:\n  issues: none"]
)
def test_AC_PLT_33_read_or_none_top_level_permissions_pass(
    tmp_path: Path, permissions: str
) -> None:
    write(tmp_path, GOOD.replace("permissions:\n  contents: read", permissions))
    assert cw.check_repo(tmp_path) == []


@pytest.mark.parametrize(
    "job_permissions",
    ["    permissions: write-all\n", "    permissions:\n      pull-requests: write\n"],
    ids=["write-all", "scope-write"],
)
def test_AC_PLT_33_job_write_permission_outside_allowlist_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], job_permissions: str
) -> None:
    assert frozenset() == cw.JOB_PERMISSION_ALLOWLIST  # empty in 00 (design.md §3.5)
    write(tmp_path, GOOD.replace("    runs-on:", job_permissions + "    runs-on:", 1))
    err = fails_naming(tmp_path, capsys, "permissions-job")
    assert "job 'lint'" in err


def test_AC_PLT_33_job_read_permission_passes(tmp_path: Path) -> None:
    write(
        tmp_path, GOOD.replace("    runs-on:", "    permissions:\n      issues: read\n    runs-on:")
    )
    assert cw.check_repo(tmp_path) == []


def test_AC_PLT_33_allowlisted_job_write_permission_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = (".github/workflows/x.yml", "lint", "pull-requests")
    monkeypatch.setattr(cw, "JOB_PERMISSION_ALLOWLIST", frozenset({entry}))
    write(
        tmp_path,
        GOOD.replace("    runs-on:", "    permissions:\n      pull-requests: write\n    runs-on:"),
    )
    assert cw.check_repo(tmp_path) == []


@pytest.mark.parametrize(
    "expression",
    [
        "${{ secrets.MP_ACCESS_TOKEN }}",
        "${{ Secrets . deploy_key }}",
        "${{ secrets['NPM_TOKEN'] }}",
        "${{ toJSON(secrets) }}",
        "prefix-${{ secrets.GITHUB_TOKEN }}-${{ secrets.OTHER }}",
    ],
    ids=["dot", "case-and-spaces", "bracket", "whole-context", "second-of-two"],
)
def test_AC_PLT_33_non_github_token_secret_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], expression: str
) -> None:
    write(tmp_path, GOOD.replace("${{ secrets.GITHUB_TOKEN }}", expression))
    fails_naming(tmp_path, capsys, "secrets")


def test_AC_PLT_33_secret_in_a_bare_if_expression_fails(tmp_path: Path) -> None:
    write(tmp_path, GOOD.replace("github.event_name == 'pull_request'", "secrets.DEPLOY != ''"))
    assert "secrets" in rules_of(tmp_path)


def test_AC_PLT_33_secrets_inherit_fails(tmp_path: Path) -> None:
    reusable = (
        f"  call:\n    uses: org/repo/.github/workflows/r.yml@{SHA} # v1\n    secrets: inherit\n"
    )
    write(tmp_path, GOOD + reusable)
    assert rules_of(tmp_path) == {"secrets"}


@pytest.mark.parametrize(
    "ref",
    [
        "actions/checkout@v7",
        "actions/checkout@3d3c42e",
        "actions/checkout",
        f"actions/checkout@{SHA.upper()}",
    ],
    ids=["tag", "short-sha", "no-ref", "uppercase"],
)
def test_AC_PLT_33_unpinned_action_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ref: str
) -> None:
    write(tmp_path, GOOD.replace(f"actions/checkout@{SHA}", ref))
    fails_naming(tmp_path, capsys, "uses-pin")


def test_AC_PLT_33_unpinned_reusable_workflow_fails(tmp_path: Path) -> None:
    write(tmp_path, GOOD + "  call:\n    uses: org/repo/.github/workflows/r.yml@main\n")
    assert rules_of(tmp_path) == {"uses-pin"}


@pytest.mark.parametrize(
    ("ref", "ok"),
    [
        (f"docker://zricethezav/gitleaks:v8.30.1@sha256:{DIGEST}", True),
        (f"docker://alpine@sha256:{DIGEST}", True),
        ("docker://alpine:3.22", False),
        (f"docker://alpine@sha256:{DIGEST[:-1]}", False),
    ],
    ids=["tag-and-digest", "digest", "tag-only", "short-digest"],
)
def test_AC_PLT_33_docker_uses_needs_a_digest(tmp_path: Path, ref: str, ok: bool) -> None:
    write(tmp_path, GOOD.replace(f"actions/checkout@{SHA} # v7.0.1", ref))
    assert (rules_of(tmp_path) == set()) is ok


def test_AC_PLT_33_pinned_action_without_tag_comment_fails(tmp_path: Path) -> None:
    write(tmp_path, GOOD.replace(f"actions/checkout@{SHA} # v7.0.1", f"actions/checkout@{SHA}"))
    assert rules_of(tmp_path) == {"uses-tag-comment"}


def test_AC_PLT_33_composite_action_unpinned_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, GOOD)
    action = "name: a\nruns:\n  using: composite\n  steps:\n    - uses: astral-sh/setup-uv@v7\n"
    write(tmp_path, action, "action.yml", ".github/actions/setup")
    fails_naming(tmp_path, capsys, "uses-pin", ".github/actions/setup/action.yml")


def test_AC_PLT_33_job_level_if_on_required_job_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path,
        GOOD.replace("    runs-on:", "    if: github.event_name == 'push'\n    runs-on:", 1),
    )
    err = fails_naming(tmp_path, capsys, "job-if")
    assert "job 'lint'" in err


def test_AC_PLT_33_job_level_if_by_check_name_fails_and_other_jobs_pass(tmp_path: Path) -> None:
    renamed = GOOD.replace("  lint:\n", "  first:\n    name: lint\n    if: always()\n")
    write(tmp_path, renamed)
    assert rules_of(tmp_path) == {"job-if"}
    write(tmp_path, GOOD.replace("  lint:\n", "  helper:\n    if: always()\n"))
    assert cw.check_repo(tmp_path) == []


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (GOOD + "permissions: write-all\n", "invalid-yaml"),
        ("jobs: [\n", "invalid-yaml"),
        ("- just a list\n", "invalid-workflow"),
        (GOOD.replace("on:\n  pull_request:\n    branches: [main]\n", ""), "invalid-workflow"),
        (GOOD.replace("on:", '"on": push\non:', 1), "invalid-workflow"),
        (GOOD.replace("jobs:", "jobs: []\nunused:", 1), "invalid-workflow"),
    ],
    ids=["duplicate-key", "syntax", "not-a-mapping", "no-on", "on-twice", "jobs-not-a-mapping"],
)
def test_AC_PLT_33_unreadable_workflow_fails_closed(tmp_path: Path, text: str, rule: str) -> None:
    write(tmp_path, text)
    assert rule in rules_of(tmp_path)


def test_AC_PLT_33_no_workflow_found_fails(tmp_path: Path) -> None:
    assert rules_of(tmp_path) == {"no-workflows"}


def test_AC_PLT_33_repo_workflows_pass(capsys: pytest.CaptureFixture[str]) -> None:
    files = cw.find_files(REPO_ROOT)
    names = {path.relative_to(REPO_ROOT).as_posix() for path in files}
    assert {".github/workflows/ci.yml", ".github/actions/setup/action.yml"} <= names
    assert cw.main(["--root", str(REPO_ROOT)]) == 0
    assert capsys.readouterr().err == ""


def test_AC_PLT_33_lint_job_runs_check_workflows() -> None:
    ci = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    runs = [step.get("run", "") for step in ci["jobs"]["lint"]["steps"]]
    assert "python scripts/check_workflows.py" in runs
