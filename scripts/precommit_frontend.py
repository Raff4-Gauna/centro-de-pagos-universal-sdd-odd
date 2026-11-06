"""Run eslint or prettier on the frontend files of a commit (RF-PLT-12, design.md sec. 3.6, Q-060).

Usage (hooks ``eslint`` and ``prettier`` of ``.pre-commit-config.yaml``, from the repo root):
    python scripts/precommit_frontend.py {eslint,prettier} PATH...

Both tools run with ``frontend/`` as working directory, so the paths lose that prefix. It is the
cwd and not ``pnpm --dir frontend``: corepack picks the pnpm version from the ``package.json`` of
the cwd, and from the repo root (which has none) it starts its default version, which pnpm rejects
(ERR_PNPM_BAD_PM_VERSION). The checks are the ones of the CI job ``lint`` (``pnpm lint``, ``pnpm
format:check``), limited to the files each tool covers there. Generated types (``src/types/``)
never reach them, and with nothing left to check pnpm does not run at all.

Needs Node 24 + pnpm and ``pnpm install`` in ``frontend/`` on the host (Q-060). No pnpm is an error,
not a skip: a hook that passes without checking anything is worse than one that fails.
Exit codes: the tool's own, 0 with nothing to check, 2 usage error or pnpm not found. Stdlib only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_PREFIX = "frontend/"
GENERATED_PREFIX = "src/types/"

# The flags of frontend/package.json; `--no-warn-ignored` because `eslint .` never reports a file
# of its globalIgnores, while one named on the command line is a warning and --max-warnings 0 fails.
ESLINT = ("eslint", "--max-warnings", "0", "--no-warn-ignored")
PRETTIER = ("prettier", "--check", "--ignore-path", "../.gitignore")
COMMANDS = {"eslint": ESLINT, "prettier": PRETTIER}

# What each CI command reaches. Prettier also knows Markdown and YAML, which CI does not check.
SUFFIXES = {
    "eslint": (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"),
    "prettier": (".ts", ".tsx", ".mts", ".mjs", ".json", ".css"),
}


def targets(tool: str, paths: Sequence[str]) -> list[str]:
    """The paths relative to ``frontend/`` that ``tool`` has to check."""
    relative = [p.removeprefix(FRONTEND_PREFIX) for p in paths if p.startswith(FRONTEND_PREFIX)]
    return [
        path
        for path in relative
        if path.endswith(SUFFIXES[tool]) and not path.startswith(GENERATED_PREFIX)
    ]


def command(pnpm: str, tool: str, files: Sequence[str]) -> list[str]:
    """``--`` ends the options: a file called ``-x.ts`` stays a file."""
    return [pnpm, "exec", *COMMANDS[tool], "--", *files]


def spawnable(argv: Sequence[str]) -> str | list[str]:
    """On Windows pnpm is a ``.cmd`` shim: cmd.exe parses the line, and an unquoted ``)`` of a Next
    route group such as ``(dashboard)`` closes a block of the shim. Paths cannot contain ``"``."""
    return " ".join(f'"{arg}"' for arg in argv) if os.name == "nt" else list(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tool", choices=sorted(COMMANDS))
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)

    files = targets(args.tool, args.paths)
    if not files:
        return 0
    # pnpm.cmd first: corepack also leaves a sh script `pnpm`, and `which` may return that one.
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    if pnpm is None:
        print("pnpm not found: install Node 24 and run `corepack enable`", file=sys.stderr)
        return 2
    return subprocess.run(  # noqa: S603 - fixed tool, no shell
        spawnable(command(pnpm, args.tool, files)), cwd=FRONTEND_DIR, check=False
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
