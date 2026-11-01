"""Fail on high/critical vulnerabilities in the locked dependencies (RN-PLT-14, AC-PLT-26, D-10).

Usage (from anywhere; CI job ``deps-audit``):
    python scripts/audit_deps.py [--exceptions PATH] [--backend DIR] [--frontend DIR]

- Backend: ``uv export --frozen --all-groups`` (exactly ``uv.lock``) piped through ``pip-audit``.
  pip-audit gives no severity, so it is looked up in OSV (``api.osv.dev``), GHSA records first.
- Frontend: ``pnpm audit --json`` (exactly ``pnpm-lock.yaml``), which already carries the severity.
- A severity that is missing or not recognised counts as **high** (fail closed).
- ``scripts/audit_exceptions.toml`` lists accepted vulnerabilities, each with a reason and an expiry
  date (valid through that day, UTC). An expired exception fails the run even if the vulnerability
  is gone: the file has to be cleaned up (Q-037).

Exit codes: 0 ok, 1 blocking findings (each one named on stderr), 2 tool/config error. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEPTIONS = REPO_ROOT / "scripts" / "audit_exceptions.toml"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/"
OSV_TIMEOUT_SECONDS = 20
ERROR_DETAIL_CHARS = 300

# GHSA/OSV use LOW/MODERATE/HIGH/CRITICAL; pnpm adds "info". Blocking: high and above.
SEVERITY_RANK = {"info": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}
BLOCKING_RANK = SEVERITY_RANK["high"]
UNKNOWN = "unknown"

Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]
OsvFetcher = Callable[[str], dict[str, Any] | None]


class AuditError(RuntimeError):
    """A tool failed or the exceptions file is invalid: the audit could not run."""


@dataclass(frozen=True)
class Vulnerability:
    package: str
    version: str
    id: str
    aliases: tuple[str, ...]
    # None: ask OSV (pip-audit). pnpm gives it directly.
    severity: str | None
    fix: str

    def ids(self) -> tuple[str, ...]:
        return (self.id, *self.aliases)


@dataclass(frozen=True)
class AuditException:
    id: str
    reason: str
    expires: date


def run_command(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(argv), cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False
        )
    except FileNotFoundError as exc:
        raise AuditError(f"{argv[0]} not found on PATH") from exc


def fetch_osv(vuln_id: str) -> dict[str, Any] | None:
    """The OSV record of ``vuln_id``, or None when it is missing or OSV cannot be reached."""
    url = OSV_VULN_URL + urllib.parse.quote(vuln_id, safe="")
    try:
        with urllib.request.urlopen(url, timeout=OSV_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
            record = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def load_exceptions(path: Path) -> list[AuditException]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AuditError(f"{path.name}: cannot read: {exc}") from exc
    entries = data.get("exception", [])
    if not isinstance(entries, list):
        raise AuditError(f"{path.name}: 'exception' must be an array of tables ([[exception]])")
    exceptions = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise AuditError(f"{path.name}: exception #{index} must be a table ([[exception]])")
        vuln_id, reason, expires = entry.get("id"), entry.get("reason"), entry.get("expires")
        if not isinstance(vuln_id, str) or not vuln_id.strip():
            raise AuditError(f"{path.name}: exception #{index} needs an 'id'")
        if not isinstance(reason, str) or not reason.strip():
            raise AuditError(f"{path.name}: exception {vuln_id} needs a non-empty 'reason'")
        if not isinstance(expires, date) or isinstance(expires, datetime):
            raise AuditError(
                f"{path.name}: exception {vuln_id} needs 'expires' as a TOML date (2026-12-31)"
            )
        exceptions.append(AuditException(vuln_id.strip(), reason.strip(), expires))
    return exceptions


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    text = (completed.stderr or "").strip() or (completed.stdout or "").strip()
    return text[-ERROR_DETAIL_CHARS:] or f"exit code {completed.returncode}"


def _parse_json(completed: subprocess.CompletedProcess[str], tool: str) -> dict[str, Any]:
    try:
        data = json.loads(completed.stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise AuditError(f"{tool} gave no JSON report: {_detail(completed)}")
    return data


def python_vulnerabilities(backend: Path, runner: Runner) -> list[Vulnerability]:
    """pip-audit over ``uv export --frozen --all-groups`` (runtime + every dependency group)."""
    with tempfile.TemporaryDirectory(prefix="audit-deps-") as tmp:
        requirements = str(Path(tmp) / "requirements.txt")
        export = runner(
            [
                "uv",
                "export",
                "--frozen",
                "--all-groups",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                requirements,
            ],
            backend,
        )
        if export.returncode != 0:
            raise AuditError(f"uv export failed: {_detail(export)}")
        # --disable-pip: audit the pins as they are (no resolver, no venv); the export is hashed.
        audit = runner(
            [
                "pip-audit",
                "-r",
                requirements,
                "--disable-pip",
                "--require-hashes",
                "--vulnerability-service",
                "osv",
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ],
            backend,
        )
    # pip-audit exits 1 when it finds vulnerabilities; anything else is a failure to audit.
    if audit.returncode not in (0, 1):
        raise AuditError(f"pip-audit failed: {_detail(audit)}")
    report = _parse_json(audit, "pip-audit")
    found = []
    for dep in report.get("dependencies", []):
        if "skip_reason" in dep:
            print(f"warning: pip-audit skipped {dep.get('name')}: {dep['skip_reason']}")
        for vuln in dep.get("vulns", []):
            fix = ", ".join(vuln.get("fix_versions") or []) or "none"
            aliases = tuple(vuln.get("aliases") or [])
            found.append(Vulnerability(dep["name"], dep["version"], vuln["id"], aliases, None, fix))
    return found


def node_vulnerabilities(frontend: Path, runner: Runner) -> list[Vulnerability]:
    """``pnpm audit --json`` (prod and dev dependencies); exits 1 when it finds anything."""
    completed = runner(["pnpm", "audit", "--json"], frontend)
    report = _parse_json(completed, "pnpm audit")
    advisories = report.get("advisories")
    if not isinstance(advisories, dict):
        raise AuditError(f"pnpm audit failed: {json.dumps(report)[:ERROR_DETAIL_CHARS]}")
    found = []
    for advisory in advisories.values():
        vuln_id = advisory.get("github_advisory_id") or f"npm-{advisory['id']}"
        aliases = tuple(advisory.get("cves") or [])
        versions = sorted({finding["version"] for finding in advisory.get("findings", [])})
        severity = str(advisory.get("severity") or UNKNOWN).lower()
        fix = advisory.get("patched_versions") or "none"
        for version in versions or ["?"]:
            found.append(
                Vulnerability(advisory["module_name"], version, vuln_id, aliases, severity, fix)
            )
    return found


def osv_severity(vuln: Vulnerability, fetch: OsvFetcher) -> str:
    """First recognised ``database_specific.severity`` among the vuln IDs, GHSA first."""
    for vuln_id in sorted(vuln.ids(), key=lambda value: not value.startswith("GHSA-")):
        record = fetch(vuln_id) or {}
        specific = record.get("database_specific")
        level = specific.get("severity") if isinstance(specific, dict) else None
        if isinstance(level, str) and level.lower() in SEVERITY_RANK:
            return level.lower()
    return UNKNOWN


def describe(severity: str) -> str:
    return f"{UNKNOWN} (counts as high)" if severity not in SEVERITY_RANK else severity


def evaluate(
    vulns: Sequence[Vulnerability],
    exceptions: Sequence[AuditException],
    today: date,
    fetch: OsvFetcher,
) -> list[str]:
    """Blocking problems (printed to stderr); informational lines go to stdout."""
    problems = [
        f"exception {item.id} expired on {item.expires.isoformat()} ({item.reason}): "
        "fix the dependency or renew the exception"
        for item in exceptions
        if item.expires < today
    ]
    active = {item.id: item for item in exceptions if item.expires >= today}
    for vuln in vulns:
        label = f"{vuln.package} {vuln.version}: {vuln.id}"
        excepted = next((active[i] for i in vuln.ids() if i in active), None)
        if excepted is not None:
            print(f"{label} excepted until {excepted.expires.isoformat()} ({excepted.reason})")
            continue
        severity = vuln.severity or osv_severity(vuln, fetch)
        line = f"{label} {describe(severity)} (fix: {vuln.fix})"
        if SEVERITY_RANK.get(severity, BLOCKING_RANK) >= BLOCKING_RANK:
            problems.append(line)
        else:
            print(line)
    return problems


def _unique(vulns: Sequence[Vulnerability]) -> list[Vulnerability]:
    seen: dict[tuple[str, str, str], Vulnerability] = {}
    for vuln in vulns:
        seen.setdefault((vuln.package, vuln.version, vuln.id), vuln)
    return list(seen.values())


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = run_command,
    fetch: OsvFetcher = fetch_osv,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--backend", type=Path, default=REPO_ROOT / "backend")
    parser.add_argument("--frontend", type=Path, default=REPO_ROOT / "frontend")
    args = parser.parse_args(argv)
    today = today or datetime.now(UTC).date()
    try:
        exceptions = load_exceptions(args.exceptions)
        vulns = _unique(
            [
                *python_vulnerabilities(args.backend, runner),
                *node_vulnerabilities(args.frontend, runner),
            ]
        )
    except AuditError as exc:
        print(f"audit_deps: {exc}", file=sys.stderr)
        return 2
    problems = evaluate(vulns, exceptions, today, fetch)
    for problem in problems:
        print(f"audit_deps: {problem}", file=sys.stderr)
    if problems:
        print(
            f"audit_deps: {len(problems)} blocking finding(s); add a dated exception to "
            "scripts/audit_exceptions.toml only with a reason (RN-PLT-14)",
            file=sys.stderr,
        )
        return 1
    print(f"audit_deps: ok ({len(vulns)} non-blocking or excepted finding(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
