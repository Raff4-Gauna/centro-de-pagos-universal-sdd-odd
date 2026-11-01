"""The isolated run of ``pnpm audit`` used by ``audit_deps.py`` (AC-PLT-26, RN-PLT-14, Q-037).

``audit_deps.py`` explains why: no project or user pnpm setting may reach the audit. This module
only builds the run: argv, a project dir with the lockfile and a reduced ``package.json``, and an
environment whose config/cache dirs are new and empty. Stdlib only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

# CLI flags beat any setting; --ignore-pnpmfile drops updateConfig hooks, --registry a custom one.
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


def isolated_env(root: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Allowlisted variables plus HOME/XDG/APPDATA/TMP pointing at new empty dirs in ``root``."""
    upper = {name.upper(): value for name, value in environ.items()}
    env = {name: upper[name] for name in PNPM_ENV_ALLOWLIST if name in upper}
    for name, subdir in PNPM_ISOLATED_DIRS.items():
        path = root / subdir
        path.mkdir(exist_ok=True)
        env[name] = str(path)
    return env


def isolated_project(frontend: Path, root: Path) -> Path:
    """``root/project`` with only ``pnpm-lock.yaml`` (as is) and the reduced ``package.json``.

    Raises ``OSError``/``ValueError`` when the manifest or the lockfile cannot be read.
    """
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lockfile = (frontend / "pnpm-lock.yaml").read_bytes()
    if not isinstance(manifest, dict):
        raise ValueError("package.json is not a JSON object")
    project = root / "project"
    project.mkdir()
    reduced = {key: manifest[key] for key in PACKAGE_JSON_KEYS if key in manifest}
    (project / "package.json").write_text(json.dumps(reduced, indent=2) + "\n", encoding="utf-8")
    (project / "pnpm-lock.yaml").write_bytes(lockfile)
    return project
