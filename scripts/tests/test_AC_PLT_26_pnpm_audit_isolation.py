"""AC-PLT-26 / Q-037 (T-PLT-28 re-review, B-1): ``pnpm audit`` runs isolated from any pnpm config.

pnpm 12.16.1 hides advisories through settings the project controls: ``pnpm-workspace.yaml`` in
YAML forms no line parser sees (BOM, indented, ``? key``, escapes, ``--- {...}``, multiline flow),
``.pnpmfile.*`` ``updateConfig`` hooks, a ``registry`` of its own, ``PNPM_*``/``NPM_*`` variables
and the global ``config.yaml``. The gate does not parse them: the audit gets a fresh temp dir with
only the lockfile and a reduced ``package.json``, fixed flags and an allowlisted environment.
Every evasion of the review is planted here at once; the real pnpm run is checked in Docker.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pnpm_isolation
import pytest
from audit_deps_fakes import FakeRunner, PnpmRun, run_audit

GHSA = "GHSA-g3hv-75wg-m249"
IGNORE = {"ignoreGhsas": [GHSA]}
HOOKS = f"{{ updateConfig(c) {{ c.auditConfig = {json.dumps(IGNORE)}; return c }} }}"
HOOK_CJS = f"module.exports = {{ hooks: {HOOKS} }}\n"
HOOK_MJS = f"export const hooks = {HOOKS}\n"
MANIFEST = {
    "name": "frontend",
    "version": "0.1.0",
    "private": True,
    "type": "module",
    "scripts": {"preaudit": "node evil.js"},
    "dependencies": {"next": "16.0.0"},
    "devDependencies": {"eslint": "9.39.1"},
    "optionalDependencies": {"fsevents": "2.3.3"},
    "peerDependencies": {"react": "^19"},
    "packageManager": "pnpm@12.16.1+sha512.abc",
    "pnpm": {"auditConfig": IGNORE, "auditLevel": "critical"},
}
LOCKFILE = b"lockfileVersion: '9.0'\n\nimporters:\n\n  .: {}\n"
EVASIONS = {
    # The reviewer's YAML forms (one file can only hold one; the BOM one is planted).
    "pnpm-workspace.yaml": (
        f"\ufeffauditConfig:\n  ignoreGhsas:\n    - {GHSA}\nregistry: http://127.0.0.1:9/\n"
    ),
    ".npmrc": "registry=http://127.0.0.1:9/\naudit-level=critical\n",
    ".pnpmfile.cjs": HOOK_CJS,
    ".pnpmfile.mjs": HOOK_MJS,
    # Named by a `pnpmfile:` setting: the workspace file never reaches the audit anyway.
    "hook.cjs": HOOK_CJS,
}
ENVIRON = {
    "PATH": "/usr/bin:/bin",
    "SystemRoot": "C:\\Windows",
    "HOME": "/home/runner",
    "XDG_CONFIG_HOME": "/home/runner/.config",
    "PNPM_CONFIG_AUDIT_LEVEL": "critical",
    "pnpm_config_audit_config": json.dumps(IGNORE),
    "npm_config_registry": "http://127.0.0.1:9/",
    "Pnpm_Home": "/home/runner/setup-pnpm",
    "NODE_OPTIONS": "--require /tmp/evil.js",
    "HTTPS_PROXY": "http://127.0.0.1:9/",
}


def evasive_frontend(tmp_path: Path) -> Path:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (frontend / "pnpm-lock.yaml").write_bytes(LOCKFILE)
    for name, content in EVASIONS.items():
        (frontend / name).write_text(content, encoding="utf-8")
    return frontend


def audit_evasive(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> tuple[int, PnpmRun]:
    runner = FakeRunner()
    code, _, err = run_audit(
        capsys, tmp_path, runner, frontend=evasive_frontend(tmp_path), environ=ENVIRON
    )
    assert code == 0, err
    (run,) = runner.pnpm_runs
    return code, run


def test_AC_PLT_26_pnpm_audit_sees_only_lockfile_and_reduced_manifest(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _, run = audit_evasive(capsys, tmp_path)

    assert set(run.files) == {"package.json", "pnpm-lock.yaml"}
    assert run.files["pnpm-lock.yaml"] == LOCKFILE
    assert json.loads(run.files["package.json"]) == {
        key: MANIFEST[key] for key in pnpm_isolation.PACKAGE_JSON_KEYS
    }
    assert not run.cwd.is_relative_to(tmp_path)


def test_AC_PLT_26_pnpm_audit_argv_ignores_pnpmfile_and_pins_registry(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = FakeRunner()

    run_audit(capsys, tmp_path, runner, frontend=evasive_frontend(tmp_path), environ=ENVIRON)

    pnpm = [argv for argv, _ in runner.calls if argv[0] == "pnpm"]
    assert pnpm == [
        ["pnpm", "--version"],
        [
            "pnpm",
            "audit",
            "--json",
            "--audit-level",
            "low",
            "--ignore-pnpmfile",
            "--registry=https://registry.npmjs.org/",
        ],
    ]


def test_AC_PLT_26_pnpm_audit_env_is_allowlisted(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _, run = audit_evasive(capsys, tmp_path)

    assert not [name for name in run.env if name.upper().startswith(("PNPM_", "NPM_"))]
    assert "NODE_OPTIONS" not in run.env
    assert "HTTPS_PROXY" not in run.env
    assert run.env["PATH"] == "/usr/bin:/bin"
    assert run.env["SYSTEMROOT"] == "C:\\Windows"
    allowed = set(pnpm_isolation.PNPM_ENV_ALLOWLIST) | set(pnpm_isolation.PNPM_ISOLATED_DIRS)
    assert set(run.env) <= allowed


def test_AC_PLT_26_pnpm_audit_home_and_xdg_are_empty_dirs_in_the_temp(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, list[str]] = {}
    original = FakeRunner.__call__

    def spy(self: FakeRunner, argv, cwd, env=None):  # type: ignore[no-untyped-def]
        if argv[:2] == ["pnpm", "audit"]:
            for name in pnpm_isolation.PNPM_ISOLATED_DIRS:
                seen[name] = sorted(item.name for item in Path(env[name]).iterdir())
        return original(self, argv, cwd, env)

    monkeypatch.setattr(FakeRunner, "__call__", spy)
    _, run = audit_evasive(capsys, tmp_path)

    temp_root = run.cwd.parent
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        assert Path(run.env[name]).parent == temp_root, name
        assert seen[name] == [], name
    assert run.env["HOME"] != ENVIRON["HOME"]


@pytest.mark.parametrize("pnpm_answer", [None, (1, "not json", "")], ids=["ok", "pnpm-error"])
def test_AC_PLT_26_pnpm_temp_dir_is_removed(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, pnpm_answer: tuple[int, str, str] | None
) -> None:
    runner = FakeRunner(overrides={"pnpm": pnpm_answer} if pnpm_answer else None)

    code, _, _ = run_audit(capsys, tmp_path, runner, frontend=evasive_frontend(tmp_path))

    assert code == (2 if pnpm_answer else 0)
    (run,) = runner.pnpm_runs
    assert not run.cwd.parent.exists()


@pytest.mark.parametrize("broken", ["no-lockfile", "manifest-not-json", "manifest-not-object"])
def test_AC_PLT_26_unreadable_frontend_manifest_or_lockfile_exits_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, broken: str
) -> None:
    frontend = evasive_frontend(tmp_path)
    if broken == "no-lockfile":
        (frontend / "pnpm-lock.yaml").unlink()
    else:
        text = "{" if broken == "manifest-not-json" else "[]"
        (frontend / "package.json").write_text(text, encoding="utf-8")
    runner = FakeRunner()

    code, _, err = run_audit(capsys, tmp_path, runner, frontend=frontend)

    assert code == 2
    assert "cannot prepare the isolated pnpm audit" in err
    assert runner.pnpm_runs == []


@pytest.mark.parametrize(
    ("answer", "package_manager"),
    [
        ((0, "11.0.0\n", ""), "pnpm@12.16.1+sha512.abc"),
        ((0, "12.16.1-shim\n", ""), "pnpm@12.16.1"),
        ((1, "", "corepack: cannot download"), "pnpm@12.16.1"),
        ((0, "12.16.1\n", ""), "npm@10.9.0"),
        ((0, "12.16.1\n", ""), None),
    ],
    ids=["other-version", "shim", "not-runnable", "not-pnpm", "no-package-manager"],
)
def test_AC_PLT_26_isolated_pnpm_must_be_the_package_manager_version(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    answer: tuple[int, str, str],
    package_manager: str | None,
) -> None:
    frontend = evasive_frontend(tmp_path)
    manifest = {key: value for key, value in MANIFEST.items() if key != "packageManager"}
    if package_manager:
        manifest["packageManager"] = package_manager
    (frontend / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    runner = FakeRunner(overrides={"pnpm-version": answer})

    code, _, err = run_audit(capsys, tmp_path, runner, frontend=frontend, environ=ENVIRON)

    assert code == 2
    assert "cannot prepare the isolated pnpm audit" in err
    assert runner.pnpm_runs == []


def test_AC_PLT_26_pnpm_version_is_checked_with_the_isolated_env(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = FakeRunner()

    code, _, err = run_audit(
        capsys, tmp_path, runner, frontend=evasive_frontend(tmp_path), environ=ENVIRON
    )

    assert code == 0, err
    (version_env,) = runner.version_envs
    (run,) = runner.pnpm_runs
    assert version_env == run.env
    assert pnpm_isolation.expected_pnpm_version(MANIFEST) == "12.16.1"


def test_AC_PLT_26_isolated_env_is_pure(tmp_path: Path) -> None:
    dirs = {"HOME": tmp_path / "nowhere"}

    env = pnpm_isolation.isolated_env({"Path": "/bin", "PNPM_HOME": "/x"}, dirs)

    assert env == {"PATH": "/bin", "HOME": str(tmp_path / "nowhere")}
    assert not (tmp_path / "nowhere").exists()


def test_AC_PLT_26_temp_cleanup_errors_do_not_break_the_gate(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both temp dirs (uv export, pnpm) ignore cleanup errors (an open handle on Windows)."""
    real_rmtree = shutil.rmtree
    leaked: list[str] = []

    def locked(path: str, *args: object, onexc: Any = None, **kwargs: object) -> None:
        leaked.append(path)
        onexc(os.rmdir, path, OSError("directory is locked"))

    monkeypatch.setattr(shutil, "rmtree", locked)
    try:
        code, _, err = run_audit(
            capsys, tmp_path, FakeRunner(), frontend=evasive_frontend(tmp_path)
        )
    finally:
        monkeypatch.setattr(shutil, "rmtree", real_rmtree)
        for path in leaked:
            real_rmtree(path, ignore_errors=True)

    assert code == 0, err
    assert sorted(Path(path).name.split("-")[1] for path in leaked) == ["deps", "pnpm"]
