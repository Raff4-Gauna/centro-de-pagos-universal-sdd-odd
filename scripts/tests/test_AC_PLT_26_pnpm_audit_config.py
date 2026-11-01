"""AC-PLT-26 / Q-037 (T-PLT-28 review, B-1): pnpm settings cannot hide advisories from the gate.

pnpm 12.16.1 drops advisories with ``auditLevel`` (workspace file or ``PNPM_CONFIG_AUDIT_LEVEL``)
and with ``auditConfig.ignoreGhsas``/``ignoreCves`` (workspace file or global ``config.yaml``, even
with ``--audit-level low``). The only exception channel is ``audit_exceptions.toml``, so any of
those settings is a config error (exit 2) and ``pnpm audit`` does not even run. No network.
"""

from __future__ import annotations

from pathlib import Path

import audit_deps
import pnpm_audit_guard
import pytest
from audit_deps_fakes import REPO_ROOT, TODAY, FakeOsv, FakeRunner, run_audit, write_exceptions

ALLOW_BUILDS = "allowBuilds:\n  unrs-resolver: false\n"


def frontend_with(tmp_path: Path, workspace: str) -> Path:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "pnpm-workspace.yaml").write_text(ALLOW_BUILDS + workspace, encoding="utf-8")
    return frontend


def audit_ran(runner: FakeRunner) -> bool:
    return any(argv[:2] == ["pnpm", "audit"] for argv, _ in runner.calls)


@pytest.mark.parametrize(
    "workspace",
    [
        "auditLevel: critical\n",
        "auditConfig:\n  ignoreGhsas:\n    - GHSA-g3hv-75wg-m249\n",
        "auditConfig:\n  ignoreCves: [CVE-2026-0001]\n",
        '"auditConfig": {ignoreGhsas: [GHSA-g3hv-75wg-m249]}\n',
        "audit-level: high\n",
    ],
    ids=["audit-level", "ignore-ghsas", "ignore-cves", "quoted-flow", "kebab-case"],
)
def test_AC_PLT_26_workspace_audit_setting_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, workspace: str
) -> None:
    runner = FakeRunner()

    code, _, err = run_audit(capsys, tmp_path, runner, frontend=frontend_with(tmp_path, workspace))

    assert code == 2
    assert "pnpm-workspace.yaml sets" in err
    assert "scripts/audit_exceptions.toml" in err
    assert not audit_ran(runner)


def test_AC_PLT_26_top_level_flow_mapping_with_audit_exits_2() -> None:
    assert pnpm_audit_guard.audit_keys("{auditConfig: {ignoreGhsas: [GHSA-x]}}\n") != []


def test_AC_PLT_26_workspace_without_audit_settings_passes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # Comments and nested keys are not pnpm settings; the repo's own file is clean too.
    workspace = "# auditLevel: high\noverrides:\n  auditLevel: '1.0.0'\n"
    runner = FakeRunner()

    code, _, err = run_audit(capsys, tmp_path, runner, frontend=frontend_with(tmp_path, workspace))

    assert code == 0, err
    assert audit_ran(runner)
    assert pnpm_audit_guard.file_problems(REPO_ROOT / "frontend" / "pnpm-workspace.yaml") == []


@pytest.mark.parametrize(
    "name",
    [
        "PNPM_CONFIG_AUDIT_LEVEL",
        "pnpm_config_audit_config",
        "npm_config_audit_level",
        "NPM_CONFIG_AUDIT",
    ],
)
def test_AC_PLT_26_pnpm_audit_env_var_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str
) -> None:
    runner = FakeRunner()

    code, _, err = run_audit(capsys, tmp_path, runner, environ={name: "high", "PNPM_HOME": "/x"})

    assert code == 2
    assert f"environment variable {name} is set" in err
    assert "PNPM_HOME" not in err
    assert not audit_ran(runner)


def test_AC_PLT_26_env_defaults_to_process_environment(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PNPM_CONFIG_AUDIT_LEVEL", "critical")
    argv = ["--exceptions", str(write_exceptions(tmp_path))]

    code = audit_deps.main(argv, runner=FakeRunner(), fetch=FakeOsv({}), today=TODAY)

    assert code == 2
    assert "PNPM_CONFIG_AUDIT_LEVEL" in capsys.readouterr().err


def test_AC_PLT_26_global_pnpm_config_with_audit_config_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("auditConfig:\n  ignoreGhsas:\n    - GHSA-g3hv-75wg-m249\n", encoding="utf-8")
    runner = FakeRunner(global_config=str(config))

    code, _, err = run_audit(capsys, tmp_path, runner)

    assert code == 2
    assert "config.yaml sets auditConfig" in err
    assert not audit_ran(runner)

    # A global config path that does not exist (the usual CI case) is fine.
    runner = FakeRunner(global_config=str(tmp_path / "missing" / "config.yaml"))
    code, _, err = run_audit(capsys, tmp_path, runner)
    assert code == 0, err
