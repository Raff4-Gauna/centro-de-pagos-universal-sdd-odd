"""AC-PLT-21 (frontend, RN-PLT-11): ``tsc --noEmit`` runs in ``strict`` mode in step 4 (T-PLT-27).

A type error only fails the pipeline if the compiler is strict and the ``typecheck`` job really runs
it. So this checks three links of that chain: ``frontend/tsconfig.json`` has ``strict: true`` and
does not switch any strict-family flag back off, the ``typecheck`` script of ``package.json`` is
``tsc --noEmit``, and the ``typecheck`` job of ``ci.yml`` calls that script. The tsconfig is kept as
plain JSON (no comments) so that the stdlib parser reads it exactly as ``tsc`` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
TSCONFIG = FRONTEND / "tsconfig.json"
PACKAGE_JSON = FRONTEND / "package.json"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Flags that `strict: true` turns on; setting any of them to false weakens strict mode again.
STRICT_FAMILY = (
    "alwaysStrict",
    "noImplicitAny",
    "noImplicitThis",
    "strictBindCallApply",
    "strictBuiltinIteratorReturn",
    "strictFunctionTypes",
    "strictNullChecks",
    "strictPropertyInitialization",
    "useUnknownInCatchVariables",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def strict_errors(tsconfig: dict[str, Any]) -> list[str]:
    options = tsconfig.get("compilerOptions", {})
    errors = [] if options.get("strict") is True else ["compilerOptions.strict is not true"]
    errors += [
        f"compilerOptions.{flag} is false" for flag in STRICT_FAMILY if options.get(flag) is False
    ]
    if "extends" in tsconfig:
        errors.append("tsconfig extends another config: strict could be decided elsewhere")
    return errors


def test_AC_PLT_21_tsconfig_has_strict_true() -> None:
    assert strict_errors(load_json(TSCONFIG)) == []
    # The check is not vacuous: missing, false or weakened strict mode is reported.
    assert strict_errors({"compilerOptions": {}}) == ["compilerOptions.strict is not true"]
    assert strict_errors({"compilerOptions": {"strict": False}}) != []
    weakened = {"compilerOptions": {"strict": True, "strictNullChecks": False}}
    assert strict_errors(weakened) == ["compilerOptions.strictNullChecks is false"]
    assert strict_errors({"extends": "./base.json", "compilerOptions": {"strict": True}}) != []


def test_AC_PLT_21_typecheck_script_is_tsc_noemit() -> None:
    scripts = load_json(PACKAGE_JSON)["scripts"]
    assert scripts["typecheck"] == "tsc --noEmit"


def test_AC_PLT_21_typecheck_job_runs_pnpm_typecheck() -> None:
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    runs = [step.get("run", "") for step in jobs["typecheck"]["steps"]]
    assert any("pnpm typecheck" in run for run in runs)
