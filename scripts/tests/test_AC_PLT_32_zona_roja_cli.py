"""``check_zona_roja.main()`` and ``zona-roja.yml``: end to end, without network (T-PLT-07).

AC-PLT-32 (RN-PLT-12): the PR data (files with old and new names, labels, comments, each author's
permission) comes from the GitHub API through an injected fake transport; any API error fails the
check as "not verified". The workflow runs the script and the list of the base branch (D-09).
Also the T-PLT-06 backlog: ``updated_at`` compared in UTC, verdict lines inside code ignored.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from check_zona_roja import (
    EXIT_FAILED,
    EXIT_NOT_VERIFIED,
    EXIT_PASSED,
    LABEL,
    Comment,
    evaluate,
    main,
    parse_timestamp,
    parse_verdict,
)
from github_api import Response

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "zona-roja.yml"
API = "https://api.github.test"
BASE = f"{API}/repos/acme/hub"
HEAD = "c" * 40
OLD = "d" * 40
RED = "backend/apps/charges/services/create.py"


def verdict(status: str = "APROBADO", sha: str = HEAD) -> str:
    return f"Revisión.\n<!-- reviewer-verdict -->\nVeredicto del reviewer: {status}\nSHA: {sha}\n"


def ok(payload: Any) -> Response:
    return Response(200, {}, json.dumps(payload).encode())


class FakeGitHub:
    """A fake transport for one PR (#7 of acme/hub); ``fail`` maps a URL to an error answer."""

    def __init__(
        self,
        *,
        files: list[dict[str, Any]],
        labels: tuple[str, ...] = (),
        comments: tuple[dict[str, Any], ...] = (),
        permissions: Mapping[str, str] | None = None,
        head: str = HEAD,
        fail: Mapping[str, Response] | None = None,
    ) -> None:
        pr = {
            "head": {"sha": head},
            "labels": [{"name": name} for name in labels],
            "changed_files": len(files),
        }
        self.answers: dict[str, Response] = {
            f"{BASE}/pulls/7": ok(pr),
            f"{BASE}/pulls/7/files?per_page=100": ok(files),
            f"{BASE}/issues/7/comments?per_page=100": ok(list(comments)),
        }
        for user, permission in (permissions or {}).items():
            url = f"{BASE}/collaborators/{user}/permission"
            self.answers[url] = ok({"permission": permission})
        self.answers.update(fail or {})
        self.urls: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.urls.append(url)
        return self.answers.get(url, Response(404, {}, b"{}"))


def comment(author: str, body: str, updated_at: str = "2026-11-05T12:00:00Z") -> dict[str, Any]:
    return {"user": {"login": author}, "body": body, "updated_at": updated_at}


def run(tmp_path: Path, fake: FakeGitHub, **env: str) -> tuple[int, str]:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": HEAD}}}))
    summary = tmp_path / "summary.md"
    environ = {
        "GITHUB_REPOSITORY": "acme/hub",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_TOKEN": "fake-token-for-tests",
        "GITHUB_API_URL": API,
        "GITHUB_STEP_SUMMARY": str(summary),
        **env,
    }
    code = main([], environ=environ, transport=fake)
    return code, summary.read_text(encoding="utf-8") if summary.exists() else ""


# --- CLI (AC-PLT-32) ---


def test_AC_PLT_32_cli_reads_pr_data_and_writes_summary(tmp_path: Path) -> None:
    fake = FakeGitHub(
        files=[
            {"filename": "docs/new.md", "previous_filename": RED, "status": "renamed"},
            {"filename": "docs/notes.md", "status": "modified"},
        ],
        labels=(LABEL,),
        comments=(
            comment("outsider", verdict(), "2026-11-05T13:00:00Z"),
            comment("noise", "LGTM"),
            comment("owner", verdict()),
        ),
        permissions={"owner": "admin", "outsider": "read"},
    )
    code, summary = run(tmp_path, fake)
    assert code == EXIT_PASSED
    assert "PASSED" in summary
    assert f"`{RED}`" in summary  # the old name of the rename counts
    assert "owner" in summary
    # Only verdict comments that cite the head SHA cost a permission lookup.
    assert f"{BASE}/collaborators/noise/permission" not in fake.urls
    assert f"{BASE}/collaborators/outsider/permission" in fake.urls


def test_AC_PLT_32_cli_red_path_without_label_fails(tmp_path: Path) -> None:
    fake = FakeGitHub(files=[{"filename": RED, "status": "modified"}])
    code, summary = run(tmp_path, fake)
    assert code == EXIT_FAILED
    assert "FAILED" in summary
    assert not any("/comments" in url for url in fake.urls)  # no label: comments not needed


def test_AC_PLT_32_cli_verdict_on_previous_sha_fails(tmp_path: Path) -> None:
    fake = FakeGitHub(
        files=[{"filename": RED, "status": "modified"}],
        labels=(LABEL,),
        comments=(comment("owner", verdict(sha=OLD)),),
        permissions={"owner": "admin"},
    )
    assert run(tmp_path, fake)[0] == EXIT_FAILED


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/pulls/7",
        f"{BASE}/pulls/7/files?per_page=100",
        f"{BASE}/issues/7/comments?per_page=100",
        f"{BASE}/collaborators/owner/permission",
    ],
)
def test_AC_PLT_32_api_error_fails_as_not_verified(tmp_path: Path, url: str) -> None:
    fake = FakeGitHub(
        files=[{"filename": RED, "status": "modified"}],
        labels=(LABEL,),
        comments=(comment("owner", verdict()),),
        permissions={"owner": "admin"},
        fail={url: Response(502, {}, b"")},
    )
    code, summary = run(tmp_path, fake)
    assert code == EXIT_NOT_VERIFIED
    assert "NOT VERIFIED" in summary
    assert "fake-token-for-tests" not in summary


@pytest.mark.parametrize(
    ("answers", "env"),
    [
        ({f"{BASE}/pulls/7": ok({"head": {"sha": OLD}, "labels": [], "changed_files": 1})}, {}),
        ({f"{BASE}/pulls/7": ok({"head": {"sha": HEAD}, "labels": [], "changed_files": 9})}, {}),
        ({f"{BASE}/pulls/7": ok({"head": {}, "labels": [], "changed_files": 0})}, {}),
        ({f"{BASE}/pulls/7/files?per_page=100": ok([{"status": "added"}])}, {}),
        ({}, {"GITHUB_TOKEN": ""}),
        ({}, {"GITHUB_REPOSITORY": "not a repo"}),
        ({}, {"GITHUB_EVENT_PATH": "missing.json"}),
    ],
    ids=[
        "head-moved",
        "files-truncated",
        "no-head-sha",
        "file-no-name",
        "no-token",
        "bad-repo",
        "no-event",
    ],
)
def test_AC_PLT_32_unexpected_data_fails_as_not_verified(
    tmp_path: Path, answers: Mapping[str, Response], env: Mapping[str, str]
) -> None:
    fake = FakeGitHub(files=[{"filename": "docs/a.md", "status": "added"}], fail=answers)
    environ = dict(env)
    if environ.get("GITHUB_EVENT_PATH") == "missing.json":
        environ["GITHUB_EVENT_PATH"] = str(tmp_path / "missing.json")
    assert run(tmp_path, fake, **environ)[0] == EXIT_NOT_VERIFIED


def test_AC_PLT_32_cli_quotes_the_login_in_the_permission_url(tmp_path: Path) -> None:
    fake = FakeGitHub(
        files=[{"filename": RED, "status": "modified"}],
        labels=(LABEL,),
        comments=(comment("reviewer[bot]", verdict()),),
    )
    url = f"{BASE}/collaborators/reviewer%5Bbot%5D/permission"
    fake.answers[url] = ok({"permission": "write"})
    assert run(tmp_path, fake)[0] == EXIT_PASSED


# --- Workflow (D-09) ---


def test_AC_PLT_32_workflow_checks_out_base_sha_without_paths() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = workflow[True]  # PyYAML reads the bare `on` key as True
    assert set(on) == {"pull_request"}
    trigger = on["pull_request"]
    assert set(trigger) == {
        "types"
    }  # no paths:/branches: filters (a filtered required check hangs)
    assert set(trigger["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "labeled",
        "unlabeled",
        "ready_for_review",
        "edited",  # retargeting a PR to another base fires nothing else
    }
    assert workflow["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
        "issues": "read",
    }
    job = workflow["jobs"]["zona-roja"]
    assert "if" not in job
    assert "permissions" not in job
    checkout, *rest = job["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    run_step = rest[-1]
    assert "scripts/check_zona_roja.py" in run_step["run"]
    assert run_step["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}


# --- T-PLT-06 backlog: updated_at in UTC, verdicts inside code ---


def test_AC_PLT_32_updated_at_is_compared_in_utc() -> None:
    """12:30-03:00 is 15:30Z: later than 14:00Z, though its wall clock is earlier."""
    minus_three = timezone(timedelta(hours=-3))
    approved = Comment("owner", "admin", verdict(), datetime(2026, 11, 5, 14, 0, tzinfo=UTC))
    rejected = Comment(
        "owner", "admin", verdict("RECHAZADO"), datetime(2026, 11, 5, 12, 30, tzinfo=minus_three)
    )
    # A naive datetime is read as UTC (and never raises against an aware one).
    naive = Comment("owner", "admin", verdict(), datetime(2026, 11, 5, 15, 0))  # noqa: DTZ001
    result = evaluate([RED], [LABEL], [approved, rejected, naive], HEAD, rules=None)
    assert result.verdict is not None
    assert result.verdict.status == "RECHAZADO"
    assert result.verdict.updated_at == datetime(2026, 11, 5, 15, 30, tzinfo=UTC)
    assert result.verdict.updated_at.tzinfo is UTC


def test_AC_PLT_32_api_timestamps_parse_as_utc() -> None:
    assert parse_timestamp("2026-11-05T12:00:00Z") == datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert parse_timestamp("2026-11-05T09:00:00-03:00") == datetime(2026, 11, 5, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="timestamp"):
        parse_timestamp("yesterday")


@pytest.mark.parametrize(
    "body",
    [
        "<!-- reviewer-verdict -->\n```\nVeredicto del reviewer: APROBADO\nSHA: " + HEAD + "\n```",
        "```md\n" + verdict() + "```\n",
        "~~~~\n" + verdict() + "~~~~\n",
        "<!-- reviewer-verdict -->\nSHA: " + HEAD + "\n```\nVeredicto del reviewer: APROBADO\n",
        "<!-- reviewer-verdict -->\n\n    Veredicto del reviewer: APROBADO\n    SHA: " + HEAD,
        "<!-- reviewer-verdict -->\n\tVeredicto del reviewer: APROBADO\n\tSHA: " + HEAD,
    ],
    ids=["backticks", "info-string", "tildes", "unclosed-fence", "indented-code", "tab-indent"],
)
def test_AC_PLT_32_verdict_lines_inside_code_are_ignored(body: str) -> None:
    assert parse_verdict(body) is None


def test_AC_PLT_32_verdict_after_a_closed_code_block_counts() -> None:
    body = "Ejemplo:\n````\n```\nVeredicto del reviewer: RECHAZADO\n```\n````\n" + verdict()
    parsed = parse_verdict(body)
    assert parsed is not None
    assert parsed.status == "APROBADO"


def test_AC_PLT_32_reviewer_docs_use_the_parsed_format() -> None:
    """Agent, skill and AGENTS.md ask for exactly what the check parses (§3.7.3)."""
    for doc in (
        "AGENTS.md",
        ".claude/agents/reviewer.md",
        ".claude/skills/reviewer-verdict/SKILL.md",
    ):
        text = (REPO_ROOT / doc).read_text(encoding="utf-8")
        assert "<!-- reviewer-verdict -->" in text, doc
        assert "Veredicto del reviewer: APROBADO" in text, doc
        assert "SHA: <" in text, doc
        assert "VEREDICTO: aprobado | cambios requeridos" not in text, doc
