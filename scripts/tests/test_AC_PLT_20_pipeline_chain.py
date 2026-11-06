"""AC-PLT-20 (RN-PLT-11): the CI jobs form the fail-fast chain of design.md §3.5 (T-PLT-03).

The pipeline grows one task at a time, so ``ci.yml`` holds only the jobs that already have something
to run. Whatever is present must be a subsequence of the canonical chain, each job must ``needs:``
exactly the previous *present* stage, and no required job may carry a job-level ``if:`` (GitHub
counts a skipped required check as passed). With that shape a lint error stops everything after it,
the build (step 9) included. The checks are run on the real ``ci.yml`` and on synthetic broken
workflows, so a check that silently passes on anything would fail here.

Also covered: AC-PLT-13 in CI (``file-size`` runs ``check_file_size.py``), AC-PLT-16 in CI
(``migrations`` runs ``makemigrations --check`` on its own PostgreSQL), AC-PLT-18 in CI (the same
job runs ``lint_migrations``), AC-PLT-17 in CI (and then ``check_migrations_roundtrip``) and the
RN-PLT-18 basics of ``ci.yml`` (read-only token, no ``pull_request_target``/``workflow_run``,
actions pinned by SHA). T-PLT-40 adds the other half of AC-PLT-20: the ruleset requires every job
of the chain plus ``zona-roja``, so a job skipped through ``needs:`` (GitHub reports it as passed)
never hides a failure: the job that failed is required too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import check_workflows
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ZONA_ROJA_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "zona-roja.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
SETUP_ACTION = REPO_ROOT / ".github" / "actions" / "setup" / "action.yml"
RULESET = REPO_ROOT / ".github" / "rulesets" / "main.json"
# `app.id` of the check runs of real runs (GET /repos/{o}/{r}/commits/{sha}/check-runs, PR #54).
GITHUB_ACTIONS_APP_ID = 15368

# design.md §3.5, steps 1-9. Jobs in the same stage run in parallel (step 3).
CANONICAL_STAGES: tuple[tuple[str, ...], ...] = (
    ("lint",),
    ("file-size",),
    ("secrets", "deps-audit"),
    ("typecheck",),
    ("architecture",),
    ("tests",),
    ("coverage",),
    ("migrations",),
    ("build",),
)
CANONICAL_ORDER = [job for stage in CANONICAL_STAGES for job in stage]
PINNED_USES = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def load_yaml(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    """The ``on:`` block. YAML 1.1 (PyYAML) parses the bare key ``on`` as the boolean ``True``."""
    return workflow.get("on", workflow.get(True)) or {}


def needs_of(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs", [])
    return {needs} if isinstance(needs, str) else set(needs)


def order_errors(jobs: dict[str, Any]) -> list[str]:
    unknown = [name for name in jobs if name not in CANONICAL_ORDER]
    if unknown:
        return [f"jobs outside the canonical chain: {unknown}"]
    ranks = [CANONICAL_ORDER.index(name) for name in jobs]
    return [] if ranks == sorted(ranks) else [f"jobs out of canonical order: {list(jobs)}"]


def needs_errors(jobs: dict[str, Any]) -> list[str]:
    present = [[job for job in stage if job in jobs] for stage in CANONICAL_STAGES]
    present = [stage for stage in present if stage]
    errors = []
    for previous, stage in zip([[], *present], present, strict=False):
        for name in stage:
            if needs_of(jobs[name]) != set(previous):
                errors.append(f"{name} needs {sorted(needs_of(jobs[name]))}, expected {previous}")
    return errors


def job_level_if_errors(jobs: dict[str, Any]) -> list[str]:
    return [f"{name} has a job-level if:" for name, job in jobs.items() if "if" in job]


def ci_jobs() -> dict[str, Any]:
    return load_yaml(CI_WORKFLOW)["jobs"]


def check_names(jobs: dict[str, Any]) -> list[str]:
    """The name each job reports as a check: its `name:`, or its id without one."""
    return [job.get("name", job_id) for job_id, job in jobs.items()]


def ruleset_checks() -> list[dict[str, Any]]:
    rules = json.loads(RULESET.read_text(encoding="utf-8"))["rules"]
    rule = next(rule for rule in rules if rule["type"] == "required_status_checks")
    return rule["parameters"]["required_status_checks"]


def repeated_check_names(workflows: dict[str, dict[str, Any]], required: set[str]) -> list[str]:
    """Required names defined more than once: any of those jobs reports the same check."""
    names = [name for jobs in workflows.values() for name in check_names(jobs)]
    return sorted({name for name in names if name in required and names.count(name) > 1})


def all_uses(jobs: dict[str, Any]) -> list[str]:
    return [step["uses"] for job in jobs.values() for step in job["steps"] if "uses" in step]


def test_AC_PLT_20_jobs_follow_canonical_order() -> None:
    assert order_errors(ci_jobs()) == []
    assert order_errors({"lint": {}, "tests": {}, "file-size": {}}) != []
    assert order_errors({"lint": {}, "made-up": {}}) != []


def test_AC_PLT_20_each_job_needs_previous_present_job() -> None:
    assert needs_errors(ci_jobs()) == []
    # A job that skips back over the previous present stage breaks fail-fast.
    assert needs_errors({"lint": {}, "file-size": {"needs": "lint"}, "tests": {"needs": "lint"}})
    # Step 4 needs both step-3 jobs when both exist.
    synthetic = {
        "lint": {},
        "file-size": {"needs": "lint"},
        "secrets": {"needs": "file-size"},
        "deps-audit": {"needs": "file-size"},
        "typecheck": {"needs": ["secrets"]},
    }
    assert needs_errors(synthetic) == [
        "typecheck needs ['secrets'], expected ['secrets', 'deps-audit']"
    ]


def test_AC_PLT_20_lint_is_first_without_needs() -> None:
    jobs = ci_jobs()
    assert next(iter(jobs)) == "lint"
    assert "needs" not in jobs["lint"]
    assert needs_errors({"lint": {"needs": "tests"}, "tests": {"needs": "lint"}})
    runs = " ".join(step.get("run", "") for step in jobs["lint"]["steps"])
    assert "ruff check" in runs
    assert "ruff format --check" in runs


def test_AC_PLT_20_no_job_level_if_on_required_jobs() -> None:
    assert job_level_if_errors(ci_jobs()) == []
    assert job_level_if_errors({"lint": {"if": "github.event_name == 'push'"}}) != []


def test_AC_PLT_20_build_is_last_and_needs_migrations() -> None:
    jobs = ci_jobs()
    # The whole chain of design.md §3.5 is there now, with build at the end (T-PLT-37).
    assert list(jobs) == CANONICAL_ORDER
    assert list(jobs)[-1] == "build"
    assert needs_of(jobs["build"]) == {"migrations"}
    assert "if" not in jobs["build"]
    # A failed build fails the required check, step by step too.
    assert "continue-on-error" not in jobs["build"]
    assert all("continue-on-error" not in step for step in jobs["build"]["steps"])


def test_AC_PLT_20_ruleset_checks_equal_pipeline_jobs_plus_zona_roja() -> None:
    jobs = ci_jobs()
    # A matrix job reports `name (value)`: the context of the ruleset would never appear.
    assert [name for name, job in jobs.items() if "matrix" in job.get("strategy", {})] == []
    pipeline = check_names(jobs)
    assert pipeline == CANONICAL_ORDER
    zona_roja = check_names(load_yaml(ZONA_ROJA_WORKFLOW)["jobs"])
    assert zona_roja == ["zona-roja"]

    contexts = [check["context"] for check in ruleset_checks()]
    assert sorted(contexts) == sorted([*pipeline, *zona_roja])
    assert len(contexts) == len(set(contexts)) == 11
    # Each one tied to GitHub Actions: a commit status or another app cannot satisfy it.
    assert {check.get("integration_id") for check in ruleset_checks()} == {GITHUB_ACTIONS_APP_ID}


def test_AC_PLT_20_check_workflows_guards_the_same_checks_as_the_ruleset() -> None:
    assert {check["context"] for check in ruleset_checks()} == check_workflows.REQUIRED_CHECKS


def test_AC_PLT_20_required_check_names_are_unique_across_workflows() -> None:
    # `integration_id` tells GitHub Actions from others, not one workflow from another (Q-063).
    paths = sorted(WORKFLOWS_DIR.iterdir())
    assert CI_WORKFLOW in paths
    workflows = {path.name: load_yaml(path)["jobs"] for path in paths}
    required = {check["context"] for check in ruleset_checks()}
    assert repeated_check_names(workflows, required) == []
    # By id and by `name:`, and only for required names.
    copy_by_id: dict[str, Any] = {"zona-roja": {}}
    copy_by_name = {"other": {"name": "zona-roja"}}
    assert repeated_check_names({"a": copy_by_id, "b": copy_by_name}, required) == ["zona-roja"]
    assert repeated_check_names({"a": {"x": {}}, "b": {"x": {}}}, required) == []


def test_AC_PLT_13_file_size_job_runs_check_file_size() -> None:
    runs = [step.get("run", "") for step in ci_jobs()["file-size"]["steps"]]
    assert any("scripts/check_file_size.py" in run for run in runs)


def test_AC_PLT_20_tests_job_runs_scripts_tests() -> None:
    runs = [step.get("run", "") for step in ci_jobs()["tests"]["steps"]]
    assert any("pytest -c scripts/pytest.ini scripts/tests" in run for run in runs)


def test_AC_PLT_23_typecheck_job_checks_contract_then_frontend_types() -> None:
    steps = ci_jobs()["typecheck"]["steps"]
    runs = [step.get("run", "") for step in steps]

    def index_of(fragment: str) -> int:
        return next(i for i, run in enumerate(runs) if fragment in run)

    contract = index_of("python manage.py export_openapi --check")
    types = index_of("pnpm openapi:types")
    tsc = index_of("pnpm typecheck")
    # Contract first, then the types generated from it, then tsc against those types.
    assert contract < types < tsc
    assert steps[types]["working-directory"] == "frontend"
    # New untracked files count as a difference too, and the step fails printing the diff.
    assert "git status --porcelain --untracked-files=all -- src/types" in runs[types]
    assert "git --no-pager diff -- src/types" in runs[types]
    assert "exit 1" in runs[types]


def test_AC_PLT_16_migrations_job_runs_makemigrations_check_on_postgres() -> None:
    jobs = ci_jobs()
    job = jobs["migrations"]
    runs = " ".join(step.get("run", "") for step in job["steps"])
    assert "python -W error::RuntimeWarning manage.py makemigrations --check --dry-run" in runs
    # Django only warns when it cannot reach the database: the step turns that into a failure,
    # by the warning filter and by the text in the output.
    assert 'grep -q "consistent migration history"' in runs
    # Its own throwaway PostgreSQL, the same pinned image and credentials as the `tests` job.
    assert job["services"]["postgres"] == jobs["tests"]["services"]["postgres"]


def test_AC_PLT_18_migrations_job_runs_lint_migrations() -> None:
    steps = ci_jobs()["migrations"]["steps"]
    lint = [step for step in steps if step.get("name") == "lint_migrations"]
    assert len(lint) == 1
    # Without app labels: every app under apps.* (the synthetic ones run in the `tests` job).
    assert lint[0]["run"].strip() == "python manage.py lint_migrations"
    assert lint[0]["working-directory"] == "backend"
    assert "continue-on-error" not in lint[0]
    # After the missing-migration check, in the same job.
    names = [step.get("name") for step in steps]
    assert names.index("makemigrations --check --dry-run") < names.index("lint_migrations")


def test_AC_PLT_17_migrations_job_runs_roundtrip_last() -> None:
    steps = ci_jobs()["migrations"]["steps"]
    roundtrip = [step for step in steps if step.get("name") == "check_migrations_roundtrip"]
    assert len(roundtrip) == 1
    # Without app labels: every app under apps.*, on the job's own throwaway PostgreSQL, which is
    # what --allow-data-loss confirms (reverting drops the tables).
    assert (
        roundtrip[0]["run"].strip()
        == "python manage.py check_migrations_roundtrip --allow-data-loss"
    )
    assert roundtrip[0]["working-directory"] == "backend"
    assert "continue-on-error" not in roundtrip[0]
    # After the static checks: an irreversible migration is reported before touching the DB.
    names = [step.get("name") for step in steps]
    assert names[-1] == "check_migrations_roundtrip"
    assert names.index("lint_migrations") < names.index("check_migrations_roundtrip")


def test_RN_PLT_18_ci_triggers_and_read_only_token() -> None:
    workflow = load_yaml(CI_WORKFLOW)
    on = triggers(workflow)
    # Exactly these two: never pull_request_target nor workflow_run (RN-PLT-18).
    assert set(on) == {"pull_request", "push"}
    assert on["pull_request"]["branches"] == ["main"]
    assert on["push"] == {"branches": ["main"], "tags": ["v*"]}
    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in workflow["jobs"].values())
    assert (
        workflow["concurrency"]["cancel-in-progress"]
        == "${{ github.event_name == 'pull_request' }}"
    )


@pytest.mark.parametrize("path", [CI_WORKFLOW, SETUP_ACTION], ids=["ci.yml", "setup/action.yml"])
def test_RN_PLT_18_remote_actions_are_pinned_by_full_sha(path: Path) -> None:
    document = load_yaml(path)
    steps_owner = document["jobs"] if "jobs" in document else {"composite": document["runs"]}
    uses = all_uses(steps_owner)
    remote = [ref for ref in uses if not ref.startswith("./")]
    assert remote, f"{path.name} uses no remote action: the check would pass on nothing"
    unpinned = [ref for ref in remote if not PINNED_USES.match(ref)]
    assert unpinned == []
