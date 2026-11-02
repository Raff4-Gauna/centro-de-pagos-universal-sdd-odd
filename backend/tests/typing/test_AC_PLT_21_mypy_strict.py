"""AC-PLT-21 (RNF-PLT-09, Q-033): mypy fails on a type error, and on an unannotated def in
``apps/common/`` or a ``domain/`` (T-PLT-10).

Runs the real ``[tool.mypy]`` of ``backend/pyproject.toml`` (the one the CI ``typecheck`` job uses)
in-process with ``mypy.api.run``. The synthetic modules under ``synthetic/`` are passed explicitly:
``exclude`` keeps them out of ``mypy .``, not out of an explicit file list. With
``--explicit-package-bases`` and ``MYPYPATH=synthetic/`` mypy names them ``apps.common.untyped``,
``apps.demo.domain.untyped`` and ``apps.demo.services.untyped``, the names the strict override
(``apps.common.*``, ``apps.*.domain.*``) matches. Both only affect module naming, never a check.
The three files hold the same unannotated def, so only its location changes the outcome.
A last test checks that the ``typecheck`` job of ``ci.yml`` really runs this mypy.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from mypy import api

BACKEND = Path(__file__).resolve().parents[2]
PYPROJECT = BACKEND / "pyproject.toml"
CI_WORKFLOW = BACKEND.parent / ".github" / "workflows" / "ci.yml"
SYNTHETIC = Path(__file__).resolve().parent / "synthetic"
# run_mypy(*args) -> (exit status, stdout + stderr)
MypyRunner = Callable[..., tuple[int, str]]
UNTYPED_DEF = "error: Function is missing a type annotation  [no-untyped-def]"


@pytest.fixture(scope="module")
def mypy_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One cache for the module: the first run analyses Django and its stubs, the rest reuse it."""
    return tmp_path_factory.mktemp("mypy-cache")


@pytest.fixture
def run_mypy(mypy_cache: Path, monkeypatch: pytest.MonkeyPatch) -> MypyRunner:
    # The Django plugin resolves config.settings.test from the working directory.
    monkeypatch.chdir(BACKEND)
    monkeypatch.setenv("MYPYPATH", str(SYNTHETIC))

    def run(*args: str) -> tuple[int, str]:
        stdout, stderr, status = api.run(
            [
                "--config-file",
                str(PYPROJECT),
                "--cache-dir",
                str(mypy_cache),
                "--explicit-package-bases",
                *args,
            ]
        )
        return status, stdout + stderr

    return run


def synthetic(relative: str) -> str:
    return str(SYNTHETIC / "apps" / relative / "untyped.py")


def test_AC_PLT_21_untyped_def_in_common_fails(run_mypy: MypyRunner) -> None:
    status, output = run_mypy(synthetic("common"))
    assert status == 1, output
    assert UNTYPED_DEF in output


def test_AC_PLT_21_untyped_def_in_domain_fails(run_mypy: MypyRunner) -> None:
    status, output = run_mypy(synthetic("demo/domain"))
    assert status == 1, output
    assert UNTYPED_DEF in output


def test_AC_PLT_21_untyped_def_in_services_passes(run_mypy: MypyRunner) -> None:
    # Outside the strict modules only check_untyped_defs applies: the body is checked, the
    # missing annotations are allowed.
    status, output = run_mypy(synthetic("demo/services"))
    assert status == 0, output
    assert "Success: no issues found in 1 source file" in output


def test_AC_PLT_21_type_error_fails(run_mypy: MypyRunner) -> None:
    # A type error inside an *unannotated* function of a non-strict module: without
    # check_untyped_defs mypy would skip its body and pass.
    status, output = run_mypy("-c", "def total():\n    return 1 + 'one'\n")
    assert status == 1, output
    assert "[operator]" in output


def test_AC_PLT_21_typecheck_job_runs_mypy_on_backend_and_scripts() -> None:
    # From backend/, so mypy picks up backend/pyproject.toml and the Django plugin finds config/.
    steps = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["typecheck"]["steps"]
    mypy_steps = [step for step in steps if step.get("run", "").startswith("mypy ")]
    assert [(step.get("working-directory"), step["run"]) for step in mypy_steps] == [
        ("backend", "mypy . ../scripts")
    ]
