"""Fail when the documented state drifts from git, tests and verification (process tooling).

Usage (from the repo root):
    python scripts/check_spec_state.py                 # every spec in specs/NN-*/
    python scripts/check_spec_state.py --spec 00-platform
    python scripts/check_spec_state.py --write         # regenerate the conciliation block

Checks, per spec:
1. A commit whose subject names ``T-XX-NN`` must have that row in ``✅``/``🧪`` (not
   pending/review).
2. A ``✅``/``🧪`` row must cite a PR **and** a merge SHA, and they must match ``git log``. A squash
   that lost the task ID is linked by ``squashed_without_id`` in the baseline.
3. A ``🧪`` row must have its AC in ``verification.md``.
4. Every AC of the spec must be referenced by a test file (``test_*``/``*.test.*``), unless the
   baseline lists it under ``allow_missing_tests``.
5. A spec in ``Implemented``/``Verified`` must have ``verification.md``; its ACs must exist in the
   spec.

The ``--write`` mode only rewrites the block between ``<!-- check_spec_state:begin -->`` and
``<!-- check_spec_state:end -->`` of each ``tasks.md``. Exit codes: 0 no drift, 1 drift, 2 usage or
parse error.

The parsing rules live in ``scripts/spec_state.py``: this file only wires them to the CLI, so both
stay under the 400-line limit (``C-14``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from spec_state import (
    DEFAULT_BASELINE,
    StateError,
    check_spec,
    discover_specs,
    git_commits,
    load_baseline,
    squashed_without_id,
    summarize,
    test_corpus,
    write_conciliation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detecta drift entre documentos y git.")
    parser.add_argument("--root", default=".", help="raíz del repo (default: .)")
    parser.add_argument("--spec", help="una spec, por carpeta (ej. 00-platform)")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="JSON de excepciones")
    parser.add_argument("--write", action="store_true", help="regenera la conciliación con git")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        baseline = load_baseline(Path(args.baseline))
        discovered = discover_specs(root, args.spec)
        specs = [path for path in discovered if (path / "tasks.md").is_file()]
        skipped = [path.name for path in discovered if path not in specs]
        linked = squashed_without_id(root, baseline)
        found = git_commits(root)
        # A commit naming the task wins, unless it has no PR and the baseline links a real merge.
        commits = {**linked, **{k: v for k, v in found.items() if v.pr or k not in linked}}
        corpus = test_corpus(root)
        results = [check_spec(spec, commits, corpus, baseline) for spec in specs]
        if args.write:
            for result in results:
                write_conciliation(root / "specs" / result.module, result.tasks, commits)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if skipped:
        print(f"sin tasks.md (se omiten): {', '.join(skipped)}")
    if not results:
        print("error: ninguna spec tiene tasks.md", file=sys.stderr)
        return 2

    drift = [(result.module, message) for result in results for message in result.drift]
    for result in results:
        print(summarize(result))
        for message in result.drift:
            print(f"  DRIFT {message}")
    if drift:
        print(f"\n{len(drift)} drift(s) detectado(s).", file=sys.stderr)
        return 1
    print("\nOK: sin drift.")
    return 0


if __name__ == "__main__":
    # Windows consoles default to cp1252 and cannot print the status symbols.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
