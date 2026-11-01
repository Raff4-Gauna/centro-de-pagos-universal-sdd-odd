"""AC-PLT-26 (RN-PLT-14, Q-037, D-10): ``audit_deps.py`` blocks high/critical vulnerabilities.

Fakes in ``audit_deps_fakes.py`` (no network, no real tools, fixed clock). The pnpm config guard is
in ``test_AC_PLT_26_pnpm_audit_config.py``; CI job, Dependabot and setup in
``test_RN_PLT_14_dependabot_and_setup.py``.
"""

from __future__ import annotations

import http.client
import io
import json
from pathlib import Path
from typing import Any

import audit_deps
import pytest
from audit_deps_fakes import (
    DRF_HIGH,
    MINIMATCH_MODERATE,
    REPO_ROOT,
    TODAY,
    FakeOsv,
    FakeRunner,
    osv_record,
    pip_audit_report,
    pnpm_report,
    run_audit,
    write_exceptions,
)


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
    # Matched through the alias; still valid on its expiry day; 90 days ahead is the longest.
    valid = write_exceptions(
        tmp_path, ("GHSA-3547-9m27-7rxg", "2026-11-01"), ("GHSA-g3hv-75wg-m249", "2027-01-30")
    )

    code, out, err = run_audit(capsys, tmp_path, runner, osv, valid)

    assert code == 0, err
    assert "excepted until 2026-11-01" in out
    assert "excepted until 2027-01-30" in out
    assert "warning" not in out
    assert osv.asked == []


def test_AC_PLT_26_unused_exception_warns(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    unused = write_exceptions(tmp_path, ("GHSA-aaaa-bbbb-cccc", "2026-12-01"))

    code, out, _ = run_audit(capsys, tmp_path, FakeRunner(), exceptions=unused)

    assert code == 0
    assert "warning: exception GHSA-aaaa-bbbb-cccc matches no finding" in out


def test_AC_PLT_26_exception_beyond_90_days_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    too_long = write_exceptions(tmp_path, ("GHSA-3547-9m27-7rxg", "2027-01-31"))

    code, _, err = run_audit(capsys, tmp_path, FakeRunner(), exceptions=too_long)

    assert code == 2
    assert "GHSA-3547-9m27-7rxg expires on 2027-01-31, more than 90 days ahead" in err


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
    (uv, uv_cwd), (pip_audit, _), (config, _), (pnpm, pnpm_cwd) = runner.calls
    assert uv[:5] == ["uv", "export", "--frozen", "--all-groups", "--no-emit-project"]
    assert uv_cwd == REPO_ROOT / "backend"
    requirements = uv[uv.index("--output-file") + 1]
    assert pip_audit[:3] == ["pip-audit", "-r", requirements]
    assert {"--disable-pip", "--require-hashes", "--format"} <= set(pip_audit)
    # The config guard runs first; --audit-level low beats any auditLevel setting (B-1).
    assert config == ["pnpm", "config", "get", "globalconfig"]
    assert pnpm == ["pnpm", "audit", "--json", "--audit-level", "low"]
    assert pnpm_cwd == REPO_ROOT / "frontend"


@pytest.mark.parametrize(
    "overrides",
    [
        {"uv": (2, "", "error: the lockfile needs to be updated")},
        {"pip-audit": (1, "", "ERROR: invalid requirements input")},
        {"pip-audit": (2, json.dumps(pip_audit_report()), "")},
        {"pnpm-config": (1, "", "ERR_PNPM_CONFIG")},
        {"pnpm": (1, json.dumps({"error": {"code": "ERR_PNPM_AUDIT_BAD_RESPONSE"}}), "")},
        {"pnpm": (1, "not json", "")},
    ],
    ids=[
        "uv-export",
        "pip-audit-no-json",
        "pip-audit-exit-2",
        "pnpm-config",
        "pnpm-error",
        "pnpm-no-json",
    ],
)
def test_AC_PLT_26_tool_error_exits_2(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    overrides: dict[str, tuple[int, str, str]],
) -> None:
    code, _, err = run_audit(capsys, tmp_path, FakeRunner(overrides=overrides))

    assert code == 2
    assert "audit_deps:" in err


def test_AC_PLT_26_pip_audit_skipped_dependency_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    report = pip_audit_report()
    report["dependencies"].append(
        {
            "name": "private-pkg",
            "skip_reason": "Dependency not found on PyPI and could not be audited",
        }
    )

    code, _, err = run_audit(capsys, tmp_path, FakeRunner(pip_report=report))

    assert code == 2
    assert "pip-audit could not audit private-pkg" in err


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
    assert audit_deps.load_exceptions(audit_deps.DEFAULT_EXCEPTIONS, TODAY) == []


def test_AC_PLT_26_fetch_osv_reads_record_and_404_is_unknown(
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

    def not_found(url: str, timeout: float) -> io.BytesIO:
        raise audit_deps.urllib.error.HTTPError(
            url, 404, "Not Found", http.client.HTTPMessage(), None
        )

    monkeypatch.setattr(audit_deps.urllib.request, "urlopen", not_found)
    assert audit_deps.fetch_osv("PYSEC-0000-0") is None


@pytest.mark.parametrize(
    "failure",
    [
        audit_deps.urllib.error.URLError("offline"),
        audit_deps.urllib.error.HTTPError("u", 503, "Unavailable", http.client.HTTPMessage(), None),
        TimeoutError("timed out"),
        ConnectionResetError("reset by peer"),
        http.client.IncompleteRead(b"{"),
        b"not json",
        b"[1, 2]",
    ],
    ids=[
        "url-error",
        "http-503",
        "timeout",
        "os-error",
        "http-exception",
        "not-json",
        "not-object",
    ],
)
def test_AC_PLT_26_osv_failure_exits_2_without_traceback(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException | bytes,
) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        if isinstance(failure, bytes):
            return io.BytesIO(failure)
        raise failure

    monkeypatch.setattr(audit_deps.urllib.request, "urlopen", urlopen)
    runner = FakeRunner(pip_report=pip_audit_report(DRF_HIGH))
    argv = ["--exceptions", str(write_exceptions(tmp_path))]

    code = audit_deps.main(argv, runner=runner, today=TODAY, environ={})

    assert code == 2
    assert "audit_deps: OSV" in capsys.readouterr().err
