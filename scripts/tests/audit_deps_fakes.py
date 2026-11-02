"""Fakes and payloads shared by the ``audit_deps.py`` tests (AC-PLT-26). Not a test module.

No network and no real tools: ``uv``/``pip-audit``/``pnpm`` are replaced by a fake runner, OSV by a
dict, the clock by a fixed date and the environment by a dict. The pnpm payload is a trimmed,
sanitized copy of the real ``pnpm audit --json`` output of 2026-11-01 (1 moderate, ``minimatch``).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import audit_deps
import pytest

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


@dataclass
class PnpmRun:
    """What ``pnpm audit`` saw: its cwd (deleted afterwards) with the files in it, and its env."""

    cwd: Path
    files: dict[str, bytes]
    env: dict[str, str]


class FakeRunner:
    """Answers ``uv export``, ``pip-audit`` (``python -I -m pip_audit``), ``pnpm --version`` and
    ``pnpm audit`` like the tools.

    ``overrides`` replace an answer by tool name (``uv``, ``pip-audit``, ``pnpm`` = audit,
    ``pnpm-version``). ``pnpm_runs`` holds what each ``pnpm audit`` saw; ``version_envs`` the env
    of each ``pnpm --version``.
    """

    def __init__(
        self,
        pip_report: dict[str, Any] | None = None,
        pnpm: dict[str, Any] | None = None,
        overrides: dict[str, tuple[int, str, str]] | None = None,
        pnpm_version: str = "12.16.1",
    ) -> None:
        self.pip_report = pip_report or pip_audit_report()
        self.pnpm = pnpm or pnpm_report()
        self.overrides = overrides or {}
        self.pnpm_version = pnpm_version
        self.calls: list[tuple[list[str], Path]] = []
        self.pnpm_runs: list[PnpmRun] = []
        self.version_envs: list[dict[str, str]] = []

    def __call__(
        self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append((argv, cwd))
        tool = "pnpm-version" if argv == ["pnpm", "--version"] else argv[0]
        if argv[: len(audit_deps.PIP_AUDIT)] == list(audit_deps.PIP_AUDIT):
            tool = "pip-audit"
        if tool == "pnpm":
            files = {p.name: p.read_bytes() if p.is_file() else b"<dir>" for p in cwd.iterdir()}
            self.pnpm_runs.append(PnpmRun(cwd, files, dict(env or {})))
        elif tool == "pnpm-version":
            self.version_envs.append(dict(env or {}))
        if tool in self.overrides:
            code, out, err = self.overrides[tool]
        elif tool == "uv":
            code, out, err = 0, "", ""
        elif tool == "pip-audit":
            has_vulns = any(dep.get("vulns") for dep in self.pip_report["dependencies"])
            code, out, err = int(has_vulns), json.dumps(self.pip_report), ""
        elif tool == "pnpm-version":
            code, out, err = 0, self.pnpm_version + "\n", ""
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
    *,
    frontend: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    """``audit_deps.main`` with fakes; an empty environment unless one is given."""
    argv = ["--exceptions", str(exceptions or write_exceptions(tmp_path))]
    if frontend is not None:
        argv += ["--frontend", str(frontend)]
    code = audit_deps.main(
        argv, runner=runner, fetch=osv or FakeOsv({}), today=TODAY, environ=environ or {}
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err
