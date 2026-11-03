"""The isolated run of ``pnpm audit`` used by ``audit_deps.py`` (AC-PLT-26, RN-PLT-14, Q-037).

``audit_deps.py`` explains why: no project or user pnpm setting may reach the audit. This module
only builds the run: argv, a project dir with the lockfile and a reduced ``package.json``, an
environment whose config/cache dirs are new and empty, and the check that the ``pnpm`` found there
is exactly the ``packageManager`` version (no shim on PATH, no corepack picking another one).
Errors are ``OSError``/``ValueError``; ``audit_deps.py`` turns them into exit 2. Stdlib only.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# CLI flags beat any setting; --ignore-pnpmfile drops updateConfig hooks, --registry a custom one.
PNPM_VERSION = ("pnpm", "--version")
PNPM_AUDIT = (
    "pnpm",
    "audit",
    "--json",
    "--audit-level",
    "low",
    "--ignore-pnpmfile",
    "--registry=https://registry.npmjs.org/",
)
# The only package.json keys the isolated audit sees (no "pnpm" field, no packageManager).
PACKAGE_JSON_KEYS = (
    "name",
    "version",
    "private",
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# Inherited by the isolated pnpm: only what the OS needs to find and start it (no PNPM_*/NPM_*,
# no NODE_OPTIONS, no proxies). pnpm on PATH is enough: PNPM_HOME is only for global installs.
PNPM_ENV_ALLOWLIST = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC")
# `pnpm@<version>` with the optional `+sha512...` that pnpm/action-setup drops.
PACKAGE_MANAGER = re.compile(r"pnpm@([0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.-]*)(\+.*)?")
# User-level config/cache locations, pointed at empty dirs inside the temp dir.
PNPM_ISOLATED_DIRS = {
    "HOME": "home",
    "USERPROFILE": "home",
    "APPDATA": "appdata",
    "LOCALAPPDATA": "localappdata",
    "XDG_CONFIG_HOME": "config",
    "XDG_DATA_HOME": "data",
    "XDG_CACHE_HOME": "cache",
    "TMPDIR": "tmp",
    "TEMP": "tmp",
    "TMP": "tmp",
}


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class IsolatedRun:
    project: Path
    env: dict[str, str]
    pnpm_version: str


def isolated_dirs(root: Path) -> dict[str, Path]:
    """Create the empty HOME/XDG/APPDATA/TMP dirs in ``root``; variable name -> dir."""
    dirs = {name: root / subdir for name, subdir in PNPM_ISOLATED_DIRS.items()}
    for path in dirs.values():
        path.mkdir(exist_ok=True)
    return dirs


def isolated_env(environ: Mapping[str, str], dirs: Mapping[str, Path]) -> dict[str, str]:
    """Allowlisted variables of ``environ`` plus ``dirs``; pure (nothing is created here)."""
    upper = {name.upper(): value for name, value in environ.items()}
    env = {name: upper[name] for name in PNPM_ENV_ALLOWLIST if name in upper}
    env.update({name: str(path) for name, path in dirs.items()})
    return env


def expected_pnpm_version(manifest: Mapping[str, object]) -> str:
    """The version pinned by ``packageManager`` (``pnpm@12.16.1+sha512...`` -> ``12.16.1``)."""
    value = manifest.get("packageManager")
    match = PACKAGE_MANAGER.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"package.json packageManager must be pnpm@<version>, not {value!r}")
    return match.group(1)


def isolated_project(root: Path, manifest: Mapping[str, object], lockfile: bytes) -> Path:
    """``root/project`` with only ``pnpm-lock.yaml`` (as is) and the reduced ``package.json``."""
    project = root / "project"
    project.mkdir()
    reduced = {key: manifest[key] for key in PACKAGE_JSON_KEYS if key in manifest}
    (project / "package.json").write_text(json.dumps(reduced, indent=2) + "\n", encoding="utf-8")
    (project / "pnpm-lock.yaml").write_bytes(lockfile)
    return project


def prepare(frontend: Path, root: Path, environ: Mapping[str, str]) -> IsolatedRun:
    """Everything the isolated run needs, built inside ``root`` from the real frontend files."""
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lockfile = (frontend / "pnpm-lock.yaml").read_bytes()
    if not isinstance(manifest, dict):
        raise ValueError("package.json is not a JSON object")
    version = expected_pnpm_version(manifest)
    env = isolated_env(environ, isolated_dirs(root))
    return IsolatedRun(isolated_project(root, manifest, lockfile), env, version)


def check_pnpm_version(run: IsolatedRun, runner: Runner) -> None:
    """``pnpm --version`` with the isolated cwd and env must be exactly ``packageManager``."""
    completed = runner(list(PNPM_VERSION), run.project, run.env)
    actual = (completed.stdout or "").strip()[:40]
    if completed.returncode != 0 or actual != run.pnpm_version:
        raise ValueError(
            f"the isolated pnpm is {actual or 'not runnable'!r}, packageManager pins "
            f"{run.pnpm_version}"
        )
