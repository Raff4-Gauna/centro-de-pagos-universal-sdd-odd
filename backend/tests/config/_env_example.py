"""Shared helpers for the env example tests (AC-PLT-05, AC-PLT-06, RN-PLT-04; T-PLT-39).

Paths are those of the checkout, and of the dev ``backend`` container, where only ``backend/``,
``specs/_contracts/`` and both ``env.example`` files are mounted under ``/repo``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / "env.example"
SPIKES_ENV_EXAMPLE = REPO_ROOT / "spikes" / "env.example"
# Present in every checkout (host and CI), never mounted in the container.
CHECKOUT_MARKER = REPO_ROOT / ".github"

_LINE = re.compile(r"(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>.*)")


def parse_env_example(text: str) -> dict[str, str]:
    """``NAME=value`` per line; blank lines and ``#`` comments are skipped. Anything else (an
    ``export``, a lower-case name, a missing ``=``) or a repeated name raises, naming the line."""
    variables: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"line {number}: not a NAME=value line")
        name = match.group("name")
        if name in variables:
            raise ValueError(f"line {number}: {name} is repeated")
        variables[name] = match.group("value")
    return variables


def root_vars() -> dict[str, str]:
    return parse_env_example(ENV_EXAMPLE.read_text(encoding="utf-8"))


def spike_vars() -> dict[str, str]:
    return parse_env_example(SPIKES_ENV_EXAMPLE.read_text(encoding="utf-8"))


def checkout_path(path: Path) -> Path:
    """``path`` if it exists. Missing, it skips only inside the dev container (no ``.github``
    and no ``CI`` variable); in CI or in a full checkout a missing file fails instead."""
    if path.exists():
        return path
    if os.environ.get("CI") or CHECKOUT_MARKER.exists():
        pytest.fail(f"{path.relative_to(REPO_ROOT).as_posix()} is missing from the checkout")
    pytest.skip("inside the dev container only the env examples are mounted")
