"""RN-PLT-14 / AC-PLT-26: the ``deps-audit`` CI job and its pinned tools, ``.github/dependabot.yml``
and the checks/inputs of ``.github/actions/setup`` that keep PR code out of the gate (T-PLT-27
review follow-ups and T-PLT-28 review, B-2/B-3). Static YAML and text.
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


TOOLS_PYTHON = '"$RUNNER_TEMP/audit-tools/bin/python"'


def join_continuations(text: str) -> str:
    """Shell/requirements line continuations (backslash + newline) joined into one line."""
    return text.replace("\\\n", " ")


def deps_audit_steps() -> dict[str, dict[str, Any]]:
    job = load_yaml(".github", "workflows", "ci.yml")["jobs"]["deps-audit"]
    assert job["needs"] == "file-size"
    return {step.get("name", step.get("uses")): step for step in job["steps"]}


def uv_calls(run: str) -> list[list[str]]:
    """Each ``uv`` command line of a ``run:`` script, split into words."""
    lines = [line.split() for line in join_continuations(run).splitlines()]
    return [words[words.index("uv") :] for words in lines if "uv" in words]


def test_AC_PLT_26_deps_audit_job_runs_audit_deps() -> None:
    steps = deps_audit_steps()
    setup = steps["./.github/actions/setup"]
    # No code of the PR runs before the gate: pnpm only, no setup-node nor `pnpm install` (B-2);
    # uv + Python only, no `uv sync` of the PR's uv.lock nor its venv on PATH (B-3).
    assert setup["with"] == {
        "python": "true",
        "node": "true",
        "frontend-deps": "false",
        "backend-deps": "false",
    }
    runs = [step.get("run", "") for step in steps.values()]
    assert not [run for run in runs if "pnpm install" in run or "uv sync" in run]
    assert steps["audit_deps.py"]["run"] == f"{TOOLS_PYTHON} scripts/audit_deps.py"


def test_AC_PLT_26_deps_audit_tools_come_pinned_and_hashed_not_from_the_lock() -> None:
    steps = deps_audit_steps()
    names = list(steps)
    assert names.index("Install the pinned audit tools") < names.index("audit_deps.py")
    install = join_continuations(steps["Install the pinned audit tools"]["run"]).split()
    venv = ["uv", "venv", "--no-config", "--no-project", "--python", "3.12.16"]
    assert install[: len(venv) + 1] == [*venv, '"$RUNNER_TEMP/audit-tools"']
    pip = install[len(venv) + 1 :]
    assert pip[:3] == ["uv", "pip", "install"]
    # N-1: --no-cache, not the uv cache restored by setup-uv (other jobs of the run write it).
    assert {"--no-config", "--no-cache", "--require-hashes", "--no-build"} <= set(pip)
    assert pip[pip.index("--python") + 1] == TOOLS_PYTHON
    assert pip[pip.index("-r") + 1] == "scripts/audit_tool_requirements.txt"
    assert "backend" not in " ".join(install)


def test_AC_PLT_26_audit_tool_requirements_pin_pip_audit_with_hashes() -> None:
    text = (REPO_ROOT / "scripts" / "audit_tool_requirements.txt").read_text(encoding="utf-8")
    # One requirement per logical line; comments and the indented `# via` notes are skipped.
    lines = join_continuations(text).splitlines()
    entries = [line for line in lines if line and line[0] not in "# "]
    assert entries
    pins: dict[str, str] = {}
    for entry in entries:
        requirement, *rest = entry.split()
        name, sep, version = requirement.partition("==")
        assert sep, entry
        assert version, entry
        assert rest, entry
        assert all(item.startswith("--hash=sha256:") for item in rest), entry
        pins[name] = version
    assert pins["pip-audit"] == "2.10.1"


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


def test_AC_PLT_26_backend_deps_input_gates_only_sync_and_path() -> None:
    inputs = load_yaml(".github", "actions", "setup", "action.yml")["inputs"]
    assert inputs["backend-deps"]["default"] == "true"
    steps = setup_steps()
    gated = "inputs.python == 'true' && inputs.backend-deps == 'true'"
    assert steps["Install the backend env from the lockfile"]["if"] == gated
    assert steps["Put the backend env on PATH"]["if"] == gated
    # uv and Python itself still come with backend-deps "false".
    assert steps["Set up uv"]["if"] == "inputs.python == 'true'"
    assert steps["Install Python 3.12.16"]["if"] == "inputs.python == 'true'"
    runs_sync = [name for name, step in steps.items() if "uv sync" in step.get("run", "")]
    assert runs_sync == ["Install the backend env from the lockfile"]


def test_AC_PLT_26_shared_install_runs_no_scripts_nor_pnpmfile() -> None:
    install = setup_steps()["Install the frontend deps from the lockfile"]
    assert install["run"] == "pnpm install --frozen-lockfile --ignore-scripts --ignore-pnpmfile"


def test_AC_PLT_26_shared_backend_sync_builds_nothing() -> None:
    # B-3 (defence in depth): wheels only, so a local `source = { directory }` in uv.lock cannot
    # run its build backend in the jobs that do install the backend env.
    sync = setup_steps()["Install the backend env from the lockfile"]
    assert sync["run"] == "uv sync --no-config --frozen --no-build --python 3.12.16"


def test_AC_PLT_26_python_install_reads_no_repo_config() -> None:
    # B-5: a PR's /uv.toml (or [tool.uv] in /pyproject.toml) with python-downloads-json-url
    # installed a tampered CPython, the base of the tools venv that runs the gate.
    install = setup_steps()["Install Python 3.12.16"]
    assert install["run"] == "uv python install --no-config 3.12.16"
    assert "working-directory" not in install


def test_AC_PLT_26_every_uv_call_reads_no_repo_config() -> None:
    # B-5: every uv command line of the setup action and of ci.yml passes --no-config.
    workflow = load_yaml(".github", "workflows", "ci.yml")
    runs = [step.get("run", "") for step in setup_steps().values()]
    for job in workflow["jobs"].values():
        runs += [step.get("run", "") for step in job["steps"]]
    calls = [call for run in runs for call in uv_calls(run)]
    assert len(calls) >= 4
    assert [call for call in calls if "--no-config" not in call] == []
    # And for setup-uv's own calls in the gate job (its post-step cache prune included).
    assert workflow["jobs"]["deps-audit"]["env"] == {"UV_NO_CONFIG": "1"}


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
        # Patches grouped in one PR; minors stay separate; majors are decided by spec (C-13).
        groups = list(entry["groups"].values())
        assert [group["update-types"] for group in groups] == [["patch"]], name
        majors = [rule for rule in entry["ignore"] if rule["dependency-name"] == "*"]
        assert majors == [
            {"dependency-name": "*", "update-types": ["version-update:semver-major"]}
        ], name
    eslint = [rule for rule in updates["npm"]["ignore"] if rule["dependency-name"] == "eslint"]
    assert eslint == [
        {"dependency-name": "eslint", "update-types": ["version-update:semver-major"]}
    ]


def test_RN_PLT_14_setup_checks_pnpm_version_and_skips_cache_on_tags() -> None:
    steps = load_yaml(".github", "actions", "setup", "action.yml")["runs"]["steps"]
    names = [step.get("name") for step in steps]
    check = steps[names.index("Check pnpm matches packageManager")]
    assert names.index("Set up pnpm") < names.index("Check pnpm matches packageManager")
    assert "packageManager" in check["run"]
    # N-3: from $RUNNER_TEMP, so a PR's /package.json (packageManager) cannot pick another pnpm.
    assert 'actual="$(cd "$RUNNER_TEMP" && pnpm --version)"' in check["run"]
    assert check["run"].count("pnpm --version") == 1
    assert "working-directory" not in check
    node = steps[names.index("Set up Node")]["with"]
    # `cond && '' || 'pnpm'` would always yield 'pnpm' ('' is falsy): the empty value goes last.
    assert node["cache"] == "${{ !startsWith(github.ref, 'refs/tags/') && 'pnpm' || '' }}"
