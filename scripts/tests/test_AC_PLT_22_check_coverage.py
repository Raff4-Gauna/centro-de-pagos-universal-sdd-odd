"""AC-PLT-22 (RNF-PLT-08, Q-032): the coverage gate of step 7 (T-PLT-21).

Every case builds its own thresholds file and reports under ``tmp_path`` (coverage.py JSON for
backend/``scripts/``, istanbul ``json-summary`` for the frontend, as vitest writes it) and calls
``check_coverage.main`` in-process: no network, no real test run. The last tests pin the real
``coverage_thresholds.toml`` and the ``tests`` -> ``coverage`` wiring of ``ci.yml``.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import check_coverage
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

BACKEND_GATE = """
[[gate]]
name = "backend"
report = "backend/coverage/backend.json"
format = "coverage.py"
include = ["apps/**", "config/**"]
lines = 85
branches = 85
"""
SCRIPTS_GATE = """
[[gate]]
name = "scripts"
report = "coverage/scripts.json"
format = "coverage.py"
include = ["scripts/**"]
exclude = ["scripts/tests/**"]
lines = 85
branches = 85
"""
FRONTEND_GATE = """
[[gate]]
name = "frontend"
report = "frontend/coverage/coverage-summary.json"
format = "istanbul"
include = ["**/src/lib/**", "**/src/hooks/**", "**/src/modules/**"]
lines = 70
"""


def coverage_py_file(lines: tuple[int, int], branches: tuple[int, int] | None) -> dict[str, Any]:
    """One ``files`` entry of a coverage.py JSON report: (covered, total) lines and branches."""
    summary: dict[str, Any] = {"covered_lines": lines[0], "num_statements": lines[1]}
    if branches is not None:
        summary |= {"covered_branches": branches[0], "num_branches": branches[1]}
    return {"summary": summary}


def write_coverage_py(path: Path, files: dict[str, dict[str, Any]], *, branch: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"meta": {"format": 3, "branch_coverage": branch}, "files": files, "totals": {}}
    path.write_text(json.dumps(report), encoding="utf-8")


def istanbul_entry(covered: int, total: int) -> dict[str, Any]:
    pct = 100 * covered / total if total else 100
    counts = {"total": total, "covered": covered, "skipped": 0, "pct": pct}
    return dict.fromkeys(("lines", "statements", "functions", "branches"), counts)


def write_istanbul(path: Path, files: dict[str, tuple[int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"total": istanbul_entry(1, 1)} | {
        name: istanbul_entry(*counts) for name, counts in files.items()
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def run_gate(tmp_path: Path, config: str) -> int:
    config_path = tmp_path / "thresholds.toml"
    config_path.write_text(config, encoding="utf-8")
    return check_coverage.main(["--config", str(config_path), "--root", str(tmp_path)])


def write_backend(tmp_path: Path, lines: tuple[int, int], branches: tuple[int, int]) -> None:
    write_coverage_py(
        tmp_path / "backend/coverage/backend.json",
        {
            "apps/common/x.py": coverage_py_file(lines, branches),
            "config/settings/base.py": coverage_py_file((10, 10), (2, 2)),
        },
    )


def test_AC_PLT_22_backend_lines_below_85_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 93 of 110 lines = 84.545...%: shown truncated, so a failure never prints as "85.00%".
    write_backend(tmp_path, lines=(83, 100), branches=(20, 20))
    assert run_gate(tmp_path, BACKEND_GATE) == 1
    err = capsys.readouterr().err
    assert "backend lines 84.54% (93/110) below 85%" in err
    # The weakest files are named so the fix is obvious.
    assert "apps/common/x.py" in err


def test_AC_PLT_22_backend_branches_below_85_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_backend(tmp_path, lines=(100, 100), branches=(14, 20))
    assert run_gate(tmp_path, BACKEND_GATE) == 1
    assert "backend branches 72.72% (16/22) below 85%" in capsys.readouterr().err


def test_AC_PLT_22_backend_files_outside_apps_and_config_are_not_gated(tmp_path: Path) -> None:
    write_coverage_py(
        tmp_path / "backend/coverage/backend.json",
        {
            "apps/common/x.py": coverage_py_file((9, 10), (9, 10)),
            "tests/test_x.py": coverage_py_file((0, 500), (0, 50)),
            "manage.py": coverage_py_file((0, 10), (0, 2)),
        },
    )
    assert run_gate(tmp_path, BACKEND_GATE) == 0


def test_AC_PLT_22_report_without_branch_data_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A report measured without `branch = true` cannot satisfy a branch threshold.
    write_coverage_py(
        tmp_path / "backend/coverage/backend.json",
        {"apps/x.py": coverage_py_file((10, 10), None)},
        branch=False,
    )
    assert run_gate(tmp_path, BACKEND_GATE) == 1
    assert "has no branches data" in capsys.readouterr().err


def test_AC_PLT_22_scripts_below_85_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_coverage_py(
        tmp_path / "coverage/scripts.json",
        {
            # Windows reports use backslashes: normalized before matching.
            "scripts\\check_x.py": coverage_py_file((80, 100), (20, 20)),
            # The tests themselves are excluded: 100 % here must not lift the result.
            "scripts\\tests\\test_x.py": coverage_py_file((900, 900), (10, 10)),
        },
    )
    assert run_gate(tmp_path, SCRIPTS_GATE) == 1
    assert "scripts lines 80.00% (80/100) below 85%" in capsys.readouterr().err


def test_AC_PLT_22_frontend_below_70_in_lib_hooks_modules_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # istanbul keys are absolute paths of the machine that ran vitest.
    write_istanbul(
        tmp_path / "frontend/coverage/coverage-summary.json",
        {
            "/home/runner/work/hub/hub/frontend/src/lib/api-client.ts": (60, 100),
            "/home/runner/work/hub/hub/frontend/src/hooks/use-x.ts": (5, 10),
            "C:\\dev\\hub\\frontend\\src\\modules\\settings\\x.tsx": (10, 10),
        },
    )
    assert run_gate(tmp_path, FRONTEND_GATE) == 1
    assert "frontend lines 62.50% (75/120) below 70%" in capsys.readouterr().err


def test_AC_PLT_22_frontend_app_dir_is_not_gated(tmp_path: Path) -> None:
    write_istanbul(
        tmp_path / "frontend/coverage/coverage-summary.json",
        {
            "/w/frontend/src/lib/theme.ts": (70, 100),
            "/w/frontend/src/app/(dashboard)/inicio/page.tsx": (0, 400),
            "/w/frontend/src/types/api.d.ts": (0, 50),
        },
    )
    assert run_gate(tmp_path, FRONTEND_GATE) == 0


def test_AC_PLT_22_declared_report_missing_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_backend(tmp_path, lines=(100, 100), branches=(20, 20))
    assert run_gate(tmp_path, BACKEND_GATE + SCRIPTS_GATE) == 1
    err = capsys.readouterr().err
    assert "scripts: report coverage/scripts.json not found" in err


BAD_COUNTS = json.dumps(
    {
        "meta": {"branch_coverage": False},
        "files": {"apps/a.py": {"summary": {"covered_lines": 5, "num_statements": 3}}},
    }
)


@pytest.mark.parametrize(
    "content",
    ["{not json", "[]", '{"files": {"a.py": {}}}', BAD_COUNTS],
    ids=["not-json", "not-object", "no-summary", "covered-over-total"],
)
def test_AC_PLT_22_unreadable_report_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    report = tmp_path / "backend/coverage/backend.json"
    report.parent.mkdir(parents=True)
    report.write_text(content, encoding="utf-8")
    assert run_gate(tmp_path, BACKEND_GATE) == 1
    assert "backend: cannot read report" in capsys.readouterr().err


def test_AC_PLT_22_include_matching_no_file_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A gate over nothing would pass forever (e.g. a wrong `source`): it fails instead.
    write_coverage_py(
        tmp_path / "backend/coverage/backend.json",
        {"tests/test_x.py": coverage_py_file((10, 10), (2, 2))},
    )
    assert run_gate(tmp_path, BACKEND_GATE) == 1
    assert "backend: no measured lines match" in capsys.readouterr().err


def test_AC_PLT_22_exactly_at_threshold_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 75 + 10 of 90 + 10 = 85 % exactly, lines and branches (exact arithmetic, no float rounding).
    write_backend(tmp_path, lines=(75, 90), branches=(15, 18))
    write_istanbul(
        tmp_path / "frontend/coverage/coverage-summary.json", {"/w/frontend/src/lib/a.ts": (7, 10)}
    )
    assert run_gate(tmp_path, BACKEND_GATE + FRONTEND_GATE) == 0
    out = capsys.readouterr().out
    assert "backend lines 85.00% (85/100) >= 85%" in out
    assert "backend branches 85.00% (17/20) >= 85%" in out
    assert "frontend lines 70.00% (7/10) >= 70%" in out


def test_AC_PLT_22_no_branches_to_cover_passes(tmp_path: Path) -> None:
    write_coverage_py(
        tmp_path / "backend/coverage/backend.json", {"apps/x.py": coverage_py_file((9, 10), (0, 0))}
    )
    assert run_gate(tmp_path, BACKEND_GATE) == 0


@pytest.mark.parametrize(
    "config",
    [
        "",  # no gate at all
        BACKEND_GATE.replace("lines = 85\nbranches = 85\n", ""),  # no threshold
        BACKEND_GATE.replace("lines = 85", "lines = 101"),
        BACKEND_GATE.replace("lines = 85", 'lines = "85"'),
        BACKEND_GATE.replace('"coverage.py"', '"lcov"'),
        BACKEND_GATE.replace('include = ["apps/**", "config/**"]', 'include = "apps/**"'),
        BACKEND_GATE.replace('include = ["apps/**", "config/**"]', 'include = ["/apps/**"]'),
        BACKEND_GATE + "typo = 1\n",
        BACKEND_GATE.replace('name = "backend"', ""),
        "[[gate]\n",  # not TOML
    ],
    ids=[
        "empty",
        "no-threshold",
        "over-100",
        "string-threshold",
        "unknown-format",
        "include-not-list",
        "absolute-glob",
        "unknown-key",
        "no-name",
        "invalid-toml",
    ],
)
def test_AC_PLT_22_invalid_thresholds_file_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], config: str
) -> None:
    assert run_gate(tmp_path, config) == 2
    assert "check_coverage: invalid thresholds" in capsys.readouterr().err


def test_AC_PLT_22_missing_thresholds_file_is_a_usage_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"
    assert check_coverage.main(["--config", str(missing), "--root", str(tmp_path)]) == 2


def test_AC_PLT_22_real_thresholds_match_rnf_plt_08() -> None:
    # Lowering a threshold needs a row in the spec's change history (RNF-PLT-08): pin the values.
    gates = {gate.name: gate for gate in check_coverage.load_gates(check_coverage.DEFAULT_CONFIG)}
    assert set(gates) == {"backend", "scripts"}  # the frontend entry arrives with T-PLT-30
    backend, scripts = gates["backend"], gates["scripts"]
    assert backend.include == ("apps/**", "config/**")
    assert (backend.lines, backend.branches) == (85, 85)
    assert (scripts.lines, scripts.branches) == (85, 85)
    assert scripts.exclude == ("scripts/tests/**",)
    with check_coverage.DEFAULT_CONFIG.open("rb") as handle:
        assert tomllib.load(handle)  # parses as plain TOML too


def ci_jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_AC_PLT_22_tests_job_uploads_the_declared_reports() -> None:
    steps = ci_jobs()["tests"]["steps"]
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-"))
    uploaded = set(upload["with"]["path"].split())
    declared = {gate.report for gate in check_coverage.load_gates(check_coverage.DEFAULT_CONFIG)}
    assert uploaded == declared
    assert upload["with"]["retention-days"] == 7
    assert upload["with"]["if-no-files-found"] == "error"
    runs = " ".join(step.get("run", "") for step in steps)
    assert "--cov-report=json:coverage/backend.json" in runs
    assert "--cov-branch --cov-report=json:coverage/scripts.json" in runs


def test_AC_PLT_22_coverage_job_downloads_and_runs_check() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["coverage"]
    assert job["needs"] == "tests"
    # Read-only token, inherited from the workflow (job-level blocks are banned, RN-PLT-18).
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in job
    uses = [step.get("uses", "") for step in job["steps"]]
    assert any(ref.startswith("actions/download-artifact@") for ref in uses)
    runs = [step.get("run", "") for step in job["steps"]]
    assert "python scripts/check_coverage.py" in runs
