"""AC-PLT-26 (RN-PLT-14, Q-037, D-10): ``audit_deps.py`` blocks high/critical vulnerabilities.

No network and no real tools: ``uv``/``pip-audit``/``pnpm`` are replaced by a fake runner, OSV by a
dict and the clock by a fixed date. The pnpm payload is a trimmed, sanitized copy of the real
``pnpm audit --json`` output of 2026-11-01 (1 moderate, ``minimatch``, dev only).
Also covered: the ``deps-audit`` CI job, ``.github/dependabot.yml`` (RN-PLT-14) and the pnpm checks
of ``.github/actions/setup`` (T-PLT-27 review follow-ups).
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import audit_deps
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 1)

DRF_HIGH = {
    "id": "CVE-2026-114136",
    "fix_versions": ["3.18.2"],
    "aliases": ["GHSA-3547-9m27-7rxg"],
    "description": "JSONParser applies an attacker-named codec to the request stream",
}
MINIMATCH_MODERATE = {
    "findings": [{"version": "3.1.5", "paths": [".>eslint>minimatch"], "dev": True}],
    "id": 1244012,
    "title": "minimatch has potential denial of service via globparts amplification",
    "module_name": "minimatch",
    "vulnerable_versions": "<11.0.1",
    "patched_versions": ">=11.0.1",
    "severity": "moderate",
    "cwe": "CWE-405",
    "github_advisory_id": "GHSA-g3hv-75wg-m249",
    "url": "https://github.com/advisories/GHSA-g3hv-75wg-m249",
}


def pip_audit_report(*vulns: dict[str, Any]) -> dict[str, Any]:
    deps = [{"name": "django", "version": "5.2.18", "vulns": []}]
    deps.append({"name": "djangorestframework", "version": "3.16.1", "vulns": list(vulns)})
    return {"dependencies": deps, "fixes": []}


def pnpm_report(*advisories: dict[str, Any]) -> dict[str, Any]:
    return {"advisories": {str(item["id"]): item for item in advisories}, "metadata": {}}


def osv_record(severity: str | None) -> dict[str, Any]:
    return {"database_specific": {"severity": severity}} if severity else {"id": "x"}


class FakeRunner:
    """Answers ``uv export``, ``pip-audit`` and ``pnpm audit`` like the real tools would."""

    def __init__(
        self,
        pip_report: dict[str, Any] | None = None,
        pnpm: dict[str, Any] | None = None,
        overrides: dict[str, tuple[int, str, str]] | None = None,
    ) -> None:
        self.pip_report = pip_report or pip_audit_report()
        self.pnpm = pnpm or pnpm_report()
        self.overrides = overrides or {}
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append((argv, cwd))
        tool = argv[0]
        if tool in self.overrides:
            code, out, err = self.overrides[tool]
        elif tool == "uv":
            code, out, err = 0, "", ""
        elif tool == "pip-audit":
            has_vulns = any(dep["vulns"] for dep in self.pip_report["dependencies"])
            code, out, err = int(has_vulns), json.dumps(self.pip_report), ""
        else:
            code, out, err = int(bool(self.pnpm.get("advisories"))), json.dumps(self.pnpm), ""
        return subprocess.CompletedProcess(argv, code, out, err)


class FakeOsv:
    """OSV by ID from a dict; records which IDs were asked, in order."""

    def __init__(self, records: dict[str, dict[str, Any] | None]) -> None:
        self.records = records
        self.asked: list[str] = []

    def __call__(self, vuln_id: str) -> dict[str, Any] | None:
        self.asked.append(vuln_id)
        return self.records.get(vuln_id)


def write_exceptions(tmp_path: Path, *entries: tuple[str, str]) -> Path:
    path = tmp_path / "audit_exceptions.toml"
    blocks = [
        f'[[exception]]\nid = "{vuln_id}"\nreason = "fix not released yet"\nexpires = {expires}\n'
        for vuln_id, expires in entries
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def run_audit(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    runner: FakeRunner,
    osv: FakeOsv | None = None,
    exceptions: Path | None = None,
) -> tuple[int, str, str]:
    exceptions = exceptions or write_exceptions(tmp_path)
    code = audit_deps.main(
        ["--exceptions", str(exceptions)], runner=runner, fetch=osv or FakeOsv({}), today=TODAY
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_AC_PLT_26_high_vuln_without_exception_fails(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # pip-audit can list the same vuln twice (seen in the real report): reported once.
    runner = FakeRunner(pip_report=pip_audit_report(DRF_HIGH, DRF_HIGH))
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_record("HIGH")})

    code, _, err = run_audit(capsys, tmp_path, runner, osv)

    assert code == 1
    assert "djangorestframework 3.16.1" in err
    assert err.count("CVE-2026-114136") == 1
    assert "high" in err
    # GHSA records carry the severity, so they are asked first.
    assert osv.asked[0] == "GHSA-3547-9m27-7rxg"


@pytest.mark.parametrize("source", ["python", "node"])
def test_AC_PLT_26_critical_vuln_fails(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, source: str
) -> None:
    runner = (
        FakeRunner(pip_report=pip_audit_report(DRF_HIGH))
        if source == "python"
        else FakeRunner(pnpm=pnpm_report({**MINIMATCH_MODERATE, "severity": "critical"}))
    )
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_record("CRITICAL")})

    code, _, err = run_audit(capsys, tmp_path, runner, osv)

    assert code == 1
    assert "critical" in err


def test_AC_PLT_26_expired_exception_fails(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = FakeRunner(pip_report=pip_audit_report(DRF_HIGH))
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_record("HIGH")})
    expired = write_exceptions(tmp_path, ("GHSA-3547-9m27-7rxg", "2026-10-31"))

    code, _, err = run_audit(capsys, tmp_path, runner, osv, expired)

    assert code == 1
    assert "GHSA-3547-9m27-7rxg expired on 2026-10-31" in err
    assert "djangorestframework 3.16.1" in err

    # A stale expired exception (its vuln is gone) also fails: the file must be cleaned up.
    stale = write_exceptions(tmp_path, ("GHSA-aaaa-bbbb-cccc", "2026-10-31"))
    code, _, err = run_audit(capsys, tmp_path, FakeRunner(), exceptions=stale)
    assert code == 1
    assert "GHSA-aaaa-bbbb-cccc expired on 2026-10-31" in err


def test_AC_PLT_26_valid_exception_passes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = FakeRunner(
        pip_report=pip_audit_report(DRF_HIGH),
        pnpm=pnpm_report({**MINIMATCH_MODERATE, "severity": "high"}),
    )
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_record("HIGH")})
    # Matched through the alias; still valid on its expiry day.
    valid = write_exceptions(
        tmp_path, ("GHSA-3547-9m27-7rxg", "2026-11-01"), ("GHSA-g3hv-75wg-m249", "2027-01-31")
    )

    code, out, err = run_audit(capsys, tmp_path, runner, osv, valid)

    assert code == 0, err
    assert "excepted until 2026-11-01" in out
    assert "excepted until 2027-01-31" in out
    assert osv.asked == []


@pytest.mark.parametrize("osv_answer", [None, osv_record(None), osv_record("SEVERE")])
def test_AC_PLT_26_unknown_severity_counts_as_high(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, osv_answer: dict[str, Any] | None
) -> None:
    runner = FakeRunner(pip_report=pip_audit_report(DRF_HIGH))
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_answer, "CVE-2026-114136": osv_answer})

    code, _, err = run_audit(capsys, tmp_path, runner, osv)

    assert code == 1
    assert "unknown (counts as high)" in err
    assert sorted(osv.asked) == ["CVE-2026-114136", "GHSA-3547-9m27-7rxg"]

    # pnpm without a severity: same rule.
    runner = FakeRunner(pnpm=pnpm_report({**MINIMATCH_MODERATE, "severity": None}))
    code, _, err = run_audit(capsys, tmp_path, runner)
    assert code == 1
    assert "unknown (counts as high)" in err


def test_AC_PLT_26_pnpm_high_vuln_fails(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    runner = FakeRunner(pnpm=pnpm_report({**MINIMATCH_MODERATE, "severity": "high"}))

    code, _, err = run_audit(capsys, tmp_path, runner)

    assert code == 1
    assert "minimatch 3.1.5" in err
    assert "GHSA-g3hv-75wg-m249" in err


def test_AC_PLT_26_moderate_and_low_do_not_fail(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Today's real state: 1 moderate (minimatch, dev) must not block; only high/critical do."""
    runner = FakeRunner(pip_report=pip_audit_report(DRF_HIGH), pnpm=pnpm_report(MINIMATCH_MODERATE))
    osv = FakeOsv({"GHSA-3547-9m27-7rxg": osv_record("LOW")})

    code, out, err = run_audit(capsys, tmp_path, runner, osv)

    assert code == 0, err
    assert "minimatch 3.1.5: GHSA-g3hv-75wg-m249 moderate" in out
    assert "low" in out


def test_AC_PLT_26_audits_frozen_lockfiles_of_both_ecosystems(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = FakeRunner()

    code, _, _ = run_audit(capsys, tmp_path, runner)

    assert code == 0
    (uv, uv_cwd), (pip_audit, _), (pnpm, pnpm_cwd) = runner.calls
    assert uv[:5] == ["uv", "export", "--frozen", "--all-groups", "--no-emit-project"]
    assert uv_cwd == REPO_ROOT / "backend"
    requirements = uv[uv.index("--output-file") + 1]
    assert pip_audit[:3] == ["pip-audit", "-r", requirements]
    assert {"--disable-pip", "--require-hashes", "--format"} <= set(pip_audit)
    assert pnpm == ["pnpm", "audit", "--json"]
    assert pnpm_cwd == REPO_ROOT / "frontend"


@pytest.mark.parametrize(
    "overrides",
    [
        {"uv": (2, "", "error: the lockfile needs to be updated")},
        {"pip-audit": (1, "", "ERROR: invalid requirements input")},
        {"pip-audit": (2, json.dumps(pip_audit_report()), "")},
        {"pnpm": (1, json.dumps({"error": {"code": "ERR_PNPM_AUDIT_BAD_RESPONSE"}}), "")},
        {"pnpm": (1, "not json", "")},
    ],
    ids=["uv-export", "pip-audit-no-json", "pip-audit-exit-2", "pnpm-error", "pnpm-no-json"],
)
def test_AC_PLT_26_tool_error_exits_2(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    overrides: dict[str, tuple[int, str, str]],
) -> None:
    code, _, err = run_audit(capsys, tmp_path, FakeRunner(overrides=overrides))

    assert code == 2
    assert "audit_deps:" in err


def test_AC_PLT_26_missing_tool_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(audit_deps.subprocess, "run", missing)
    exceptions = write_exceptions(tmp_path)

    code = audit_deps.main(["--exceptions", str(exceptions)], fetch=FakeOsv({}), today=TODAY)

    assert code == 2
    assert "uv not found on PATH" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    [
        '[[exception]]\nid = "GHSA-x"\nreason = "r"\n',
        '[[exception]]\nid = "GHSA-x"\nreason = "r"\nexpires = "2026-12-31"\n',
        '[[exception]]\nid = "GHSA-x"\nreason = ""\nexpires = 2026-12-31\n',
        '[[exception]]\nreason = "r"\nexpires = 2026-12-31\n',
        "exception = [",
    ],
    ids=["no-expires", "expires-string", "empty-reason", "no-id", "bad-toml"],
)
def test_AC_PLT_26_invalid_exception_file_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, content: str
) -> None:
    path = tmp_path / "audit_exceptions.toml"
    path.write_text(content, encoding="utf-8")

    code, _, err = run_audit(capsys, tmp_path, FakeRunner(), exceptions=path)

    assert code == 2
    assert "audit_exceptions.toml" in err


def test_AC_PLT_26_repo_exceptions_file_is_valid_and_empty() -> None:
    assert audit_deps.load_exceptions(audit_deps.DEFAULT_EXCEPTIONS) == []


def test_AC_PLT_26_fetch_osv_reads_record_and_swallows_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> io.BytesIO:
        opened.append(url)
        return io.BytesIO(b'{"database_specific": {"severity": "HIGH"}}')

    monkeypatch.setattr(audit_deps.urllib.request, "urlopen", fake_urlopen)
    assert audit_deps.fetch_osv("GHSA-3547-9m27-7rxg") == {
        "database_specific": {"severity": "HIGH"}
    }
    assert opened == ["https://api.osv.dev/v1/vulns/GHSA-3547-9m27-7rxg"]

    def offline(url: str, timeout: float) -> io.BytesIO:
        raise audit_deps.urllib.error.URLError("offline")

    monkeypatch.setattr(audit_deps.urllib.request, "urlopen", offline)
    assert audit_deps.fetch_osv("GHSA-3547-9m27-7rxg") is None


def load_yaml(*parts: str) -> dict[Any, Any]:
    return yaml.safe_load(REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def test_AC_PLT_26_deps_audit_job_runs_audit_deps() -> None:
    job = load_yaml(".github", "workflows", "ci.yml")["jobs"]["deps-audit"]
    assert job["needs"] == "file-size"
    setup = next(step for step in job["steps"] if step.get("uses") == "./.github/actions/setup")
    assert setup["with"] == {"python": "true", "node": "true"}
    assert any("python scripts/audit_deps.py" in step.get("run", "") for step in job["steps"])


def test_RN_PLT_14_dependabot_weekly_for_all_ecosystems() -> None:
    config = load_yaml(".github", "dependabot.yml")
    assert config["version"] == 2
    updates = {entry["package-ecosystem"]: entry for entry in config["updates"]}
    assert set(updates) == {"uv", "npm", "docker", "github-actions"}

    def directories(entry: dict[str, Any]) -> list[str]:
        return entry.get("directories", [entry.get("directory")])

    assert directories(updates["uv"]) == ["/backend"]
    assert directories(updates["npm"]) == ["/frontend"]
    assert set(directories(updates["docker"])) == {"/backend", "/frontend"}
    assert "/" in directories(updates["github-actions"])
    for name, entry in updates.items():
        assert entry["schedule"]["interval"] == "weekly", name
        # Patches grouped in one PR; majors (and minors) stay separate.
        groups = list(entry["groups"].values())
        assert [group["update-types"] for group in groups] == [["patch"]], name
    eslint = [rule for rule in updates["npm"]["ignore"] if rule["dependency-name"] == "eslint"]
    assert eslint == [
        {"dependency-name": "eslint", "update-types": ["version-update:semver-major"]}
    ]


def test_RN_PLT_14_setup_checks_pnpm_version_and_skips_cache_on_tags() -> None:
    steps = load_yaml(".github", "actions", "setup", "action.yml")["runs"]["steps"]
    names = [step.get("name") for step in steps]
    check = steps[names.index("Check pnpm matches packageManager")]
    assert names.index("Set up pnpm") < names.index("Check pnpm matches packageManager")
    assert "pnpm --version" in check["run"]
    assert "packageManager" in check["run"]
    node = steps[names.index("Set up Node")]["with"]
    # `cond && '' || 'pnpm'` would always yield 'pnpm' ('' is falsy): the empty value goes last.
    assert node["cache"] == "${{ !startsWith(github.ref, 'refs/tags/') && 'pnpm' || '' }}"
