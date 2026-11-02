"""Fail when measured coverage is below the thresholds of step 7 (RNF-PLT-08, Q-032, AC-PLT-22).

Usage (from the repo root, CI job ``coverage``):
    python scripts/check_coverage.py [--config scripts/coverage_thresholds.toml] [--root .]

Each ``[[gate]]`` of the thresholds file names a report (relative to ``--root``), its format
(``coverage.py``: ``coverage json``; ``istanbul``: vitest ``json-summary``), the files it gates
(``include``/``exclude`` globs, see ``glob_paths``) and a minimum percentage of ``lines`` and/or
``branches``. The percentage is computed over the matched files only and compared exactly
(``covered * 100 >= threshold * total``). Report paths are normalized to ``/`` and absolute ones
lose their root (``/``, ``C:``), so ``**/src/lib/**`` matches istanbul's absolute keys.

Exit codes: 0 every gate passes; 1 a gate is below its threshold, or a declared report is missing,
unreadable, gates no file or lacks the branch data a threshold needs; 2 invalid or missing
thresholds file. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from glob_paths import compile_glob, match_any

DEFAULT_CONFIG = Path(__file__).resolve().parent / "coverage_thresholds.toml"
FORMATS = frozenset({"coverage.py", "istanbul"})
METRICS = ("lines", "branches")
GATE_KEYS = frozenset({"name", "report", "format", "include", "exclude", *METRICS})
# How many of the least covered files a failure lists.
WEAKEST_SHOWN = 5


class ConfigError(ValueError):
    """The thresholds file is missing or invalid (exit 2)."""


class ReportError(ValueError):
    """A declared report cannot be used to evaluate its gate (exit 1)."""


@dataclass(frozen=True)
class Gate:
    name: str
    report: str
    format: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    lines: Fraction | None
    branches: Fraction | None


# Per file: metric -> (covered, total); a metric is absent when the report did not measure it.
FileCounts = dict[str, tuple[int, int]]


def _globs(raw: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: {key} must be a list of globs")
    for pattern in value:
        try:
            compile_glob(pattern)
        except ValueError as exc:
            raise ConfigError(f"{where}: {exc}") from exc
    return tuple(value)


def _threshold(raw: dict[str, Any], key: str, where: str) -> Fraction | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{where}: {key} must be a number")
    threshold = Fraction(str(value))
    if not 0 < threshold <= 100:
        raise ConfigError(f"{where}: {key} must be in (0, 100]")
    return threshold


def load_gates(config_path: Path) -> list[Gate]:
    try:
        with config_path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{config_path}: {exc}") from exc
    raw_gates = document.get("gate")
    if not isinstance(raw_gates, list) or not raw_gates:
        raise ConfigError(f"{config_path}: no [[gate]] declared")
    gates = []
    for index, raw in enumerate(raw_gates):
        where = f"gate #{index + 1}"
        unknown = set(raw) - GATE_KEYS
        if unknown:
            raise ConfigError(f"{where}: unknown keys {sorted(unknown)}")
        name, report = raw.get("name"), raw.get("report")
        if not isinstance(name, str) or not name or not isinstance(report, str) or not report:
            raise ConfigError(f"{where}: name and report are required strings")
        if raw.get("format") not in FORMATS:
            raise ConfigError(f"{where}: format must be one of {sorted(FORMATS)}")
        gate = Gate(
            name=name,
            report=report,
            format=raw["format"],
            include=_globs(raw, "include", where),
            exclude=_globs(raw, "exclude", where),
            lines=_threshold(raw, "lines", where),
            branches=_threshold(raw, "branches", where),
        )
        if not gate.include or (gate.lines is None and gate.branches is None):
            raise ConfigError(f"{where}: needs include and a lines or branches threshold")
        gates.append(gate)
    return gates


def normalize(path: str) -> str:
    """POSIX separators; drop a drive (``C:``) and leading ``/`` so ``**/`` globs can match."""
    posix = re.sub(r"^[A-Za-z]:", "", path.replace("\\", "/"))
    return posix.lstrip("/")


def _pair(covered: Any, total: Any) -> tuple[int, int]:
    if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
        raise ReportError(f"bad counts {covered!r}/{total!r}")
    return covered, total


def _coverage_py(data: Any) -> dict[str, FileCounts]:
    has_branches = bool(data["meta"]["branch_coverage"])
    files = {}
    for name, entry in data["files"].items():
        summary = entry["summary"]
        counts = {"lines": _pair(summary["covered_lines"], summary["num_statements"])}
        if has_branches:
            counts["branches"] = _pair(summary["covered_branches"], summary["num_branches"])
        files[normalize(name)] = counts
    return files


def _istanbul(data: Any) -> dict[str, FileCounts]:
    return {
        normalize(name): {
            metric: _pair(entry[metric]["covered"], entry[metric]["total"]) for metric in METRICS
        }
        for name, entry in data.items()
        if name != "total"
    }


def parse_report(data: Any, report_format: str) -> dict[str, FileCounts]:
    """Map normalized file path -> counts. Raises ReportError on an unexpected structure."""
    parser = _coverage_py if report_format == "coverage.py" else _istanbul
    try:
        return parser(data)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ReportError(f"unexpected structure ({exc!r})") from exc


def _percent(covered: int, total: int) -> str:
    """Truncated to two decimals: a failing value never prints as the threshold."""
    hundredths = math.floor(Fraction(covered * 10_000, total))
    return f"{hundredths // 100}.{hundredths % 100:02d}%"


def _show(threshold: Fraction) -> str:
    return f"{threshold.numerator}%" if threshold.denominator == 1 else f"{float(threshold)}%"


def evaluate(gate: Gate, root: Path) -> tuple[list[str], list[str]]:
    """Return (ok lines for stdout, failures for stderr) of one gate."""
    path = root / gate.report
    if not path.is_file():
        return [], [f"{gate.name}: report {gate.report} not found (declared in the thresholds)"]
    try:
        files = parse_report(json.loads(path.read_text(encoding="utf-8")), gate.format)
    except (OSError, ValueError) as exc:
        return [], [f"{gate.name}: cannot read report {gate.report}: {exc}"]

    gated = {
        name: counts
        for name, counts in files.items()
        if match_any(name, gate.include) and not match_any(name, gate.exclude)
    }
    if sum(counts["lines"][1] for counts in gated.values()) == 0:
        return [], [f"{gate.name}: no measured lines match {list(gate.include)} in {gate.report}"]

    ok: list[str] = []
    failures: list[str] = []
    for metric in METRICS:
        threshold = getattr(gate, metric)
        if threshold is None:
            continue
        if any(metric not in counts for counts in gated.values()):
            failures.append(f"{gate.name}: report {gate.report} has no {metric} data")
            continue
        covered = sum(counts[metric][0] for counts in gated.values())
        total = sum(counts[metric][1] for counts in gated.values())
        if total == 0:
            ok.append(f"{gate.name} {metric}: nothing to cover")
            continue
        result = f"{gate.name} {metric} {_percent(covered, total)} ({covered}/{total})"
        if covered * 100 >= threshold * total:
            ok.append(f"{result} >= {_show(threshold)}")
            continue
        failures.append(f"{result} below {_show(threshold)}")
        weakest = sorted(
            (name for name in gated if gated[name][metric][1]),
            key=lambda name: Fraction(*gated[name][metric]),
        )
        for name in weakest[:WEAKEST_SHOWN]:
            failures.append(f"  {name}: {_percent(*gated[name][metric])}")
    return ok, failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coverage gate of CI step 7 (AC-PLT-22).")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="thresholds TOML")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="base of report paths")
    args = parser.parse_args(argv)
    try:
        gates = load_gates(args.config)
    except ConfigError as exc:
        print(f"check_coverage: invalid thresholds: {exc}", file=sys.stderr)
        return 2

    failed = False
    for gate in gates:
        ok, failures = evaluate(gate, args.root)
        for line in ok:
            print(line)
        for line in failures:
            print(line, file=sys.stderr)
        failed = failed or bool(failures)
    if failed:
        print("check_coverage: coverage gate failed (RNF-PLT-08).", file=sys.stderr)
        return 1
    print(f"check_coverage: {len(gates)} gate(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
