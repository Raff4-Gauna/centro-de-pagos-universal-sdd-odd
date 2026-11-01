"""pnpm settings that would hide advisories from ``pnpm audit`` (AC-PLT-26, RN-PLT-14, Q-037).

Used by ``audit_deps.py``. The only way to accept a vulnerability is a dated exception with a reason
in ``scripts/audit_exceptions.toml``; pnpm has its own channels, so they make the audit fail closed:

- ``auditLevel`` drops advisories below a level. ``audit_deps.py`` passes ``--audit-level low``,
  which beats the workspace file and the environment, but a stray setting is still refused.
- ``auditConfig`` (``ignoreGhsas``, ``ignoreCves``, ``ignoreUnfixable``) drops advisories even
  with that flag, from ``pnpm-workspace.yaml`` and from the global ``config.yaml`` (checked with
  pnpm 12.16.1). ``pnpm config get auditConfig`` prints ``undefined`` in both cases, so the files
  are read instead.
- ``PNPM_CONFIG_AUDIT*`` / ``NPM_CONFIG_AUDIT*`` variables (any case).

pnpm 12 ignores audit settings in ``.npmrc``; ``frontend/.npmrc`` and
``frontend/pnpm-workspace.yaml`` are red-zone paths anyway (T-PLT-06), which also covers YAML
tricks this line-based check misses (anchors, merge keys). Stdlib only: no YAML parser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

ENV_PREFIXES = ("PNPM_CONFIG_AUDIT", "NPM_CONFIG_AUDIT")
# A top-level key: no indentation, optionally quoted, followed by ':'.
_TOP_LEVEL_KEY = re.compile(r"""^["']?([A-Za-z0-9_-]+)["']?\s*:""")


def _normalized(text: str) -> str:
    return re.sub(r"[-_\"'\s]", "", text).lower()


def audit_keys(text: str) -> list[str]:
    """Top-level keys of a YAML text starting with ``audit`` (``auditConfig``, ``audit-level``...).

    A flow mapping at the top level (``{auditConfig: ...}``) that mentions audit also counts.
    """
    found = []
    for line in text.splitlines():
        if not line or line[0] in " \t#":
            continue
        match = _TOP_LEVEL_KEY.match(line)
        if match and _normalized(match.group(1)).startswith("audit"):
            found.append(match.group(1))
        elif line.startswith("{") and "audit" in _normalized(line):
            found.append(line.strip()[:40])
    return found


def env_problems(environ: Mapping[str, str]) -> list[str]:
    return [
        f"environment variable {name} is set"
        for name in sorted(environ)
        if name.upper().startswith(ENV_PREFIXES)
    ]


def file_problems(path: Path) -> list[str]:
    """Audit keys in a pnpm YAML settings file; a missing file has none."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path}: cannot read ({exc.__class__.__name__})"]
    return [f"{path} sets {key}" for key in audit_keys(text)]


def config_problems(
    frontend: Path, environ: Mapping[str, str], global_config: Path | None
) -> list[str]:
    """Every pnpm setting that could hide advisories; empty when ``pnpm audit`` can be trusted."""
    problems = env_problems(environ)
    problems += file_problems(frontend / "pnpm-workspace.yaml")
    if global_config is not None:
        problems += file_problems(global_config)
    return problems
