"""RN-PLT-14 / AC-PLT-26: the ``deps-audit`` CI job, ``.github/dependabot.yml`` and the pnpm
checks of ``.github/actions/setup`` (T-PLT-27 review follow-ups, resolved in T-PLT-28). Static YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_yaml(*parts: str) -> dict[Any, Any]:
    return yaml.safe_load(REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def setup_steps() -> dict[str, dict[str, Any]]:
    steps = load_yaml(".github", "actions", "setup", "action.yml")["runs"]["steps"]
    return {step["name"]: step for step in steps}


def test_AC_PLT_26_deps_audit_job_runs_audit_deps() -> None:
    job = load_yaml(".github", "workflows", "ci.yml")["jobs"]["deps-audit"]
    assert job["needs"] == "file-size"
    setup = next(step for step in job["steps"] if step.get("uses") == "./.github/actions/setup")
    # B-2: pnpm only; no setup-node, no `pnpm install`: no code of the PR runs before the gate.
    assert setup["with"] == {"python": "true", "node": "true", "frontend-deps": "false"}
    assert not [step for step in job["steps"] if "pnpm install" in step.get("run", "")]
    assert any("python scripts/audit_deps.py" in step.get("run", "") for step in job["steps"])


def test_AC_PLT_26_frontend_deps_input_gates_only_node_and_install() -> None:
    inputs = load_yaml(".github", "actions", "setup", "action.yml")["inputs"]
    assert inputs["frontend-deps"]["default"] == "true"
    steps = setup_steps()
    gated = "inputs.node == 'true' && inputs.frontend-deps == 'true'"
    assert steps["Set up Node"]["if"] == gated
    assert steps["Install the frontend deps from the lockfile"]["if"] == gated
    # pnpm itself and its version check still run with frontend-deps "false".
    assert steps["Set up pnpm"]["if"] == "inputs.node == 'true'"
    assert steps["Check pnpm matches packageManager"]["if"] == "inputs.node == 'true'"


def test_AC_PLT_26_shared_install_runs_no_scripts_nor_pnpmfile() -> None:
    install = setup_steps()["Install the frontend deps from the lockfile"]
    assert install["run"] == "pnpm install --frozen-lockfile --ignore-scripts --ignore-pnpmfile"


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
