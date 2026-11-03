"""Shared fixtures for the backend tests (T-PLT-08).

Settings are evaluated once per process, so anything that has to *start* Django with another
settings module or another environment runs in a subprocess (``run_django``). The subprocess gets
the parent environment minus every variable the settings read (``PLATFORM_ENV_VARS``) plus exactly
the ones the test passes: no value from the developer's shell or the CI job leaks into the result.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from config.settings.env import PlatformEnv

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Every variable read by config/settings/env.py: the PlatformEnv fields plus the FEATURE_* flags
# (T-PLT-09). Removed from the inherited environment: each subprocess sees only what the test sets.
PLATFORM_ENV_VARS = frozenset(PlatformEnv.model_fields)
FEATURE_PREFIX = "FEATURE_"

RunDjango = Callable[..., subprocess.CompletedProcess[str]]


def django_env(settings_module: str, values: Mapping[str, str]) -> dict[str, str]:
    """Parent env minus the platform/feature variables, plus ``values`` and the module."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in PLATFORM_ENV_VARS and not key.startswith(FEATURE_PREFIX)
    }
    env.update(values)
    env["DJANGO_SETTINGS_MODULE"] = settings_module
    # The child writes UTF-8 whatever the host console encoding is (Windows).
    env["PYTHONUTF8"] = "1"
    return env


@pytest.fixture(scope="session")
def run_django() -> RunDjango:
    """Run ``python <args>`` from ``backend/`` with a controlled environment; never raises.

    Results are cached per (args, settings module, values): several tests assert different things
    about the same start-up, and each start costs a fresh interpreter.
    """
    cache: dict[tuple[object, ...], subprocess.CompletedProcess[str]] = {}

    def run(
        *args: str, settings_module: str, values: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        key = (args, settings_module, tuple(sorted(values.items())))
        if key not in cache:
            cache[key] = subprocess.run(  # noqa: S603 - fixed interpreter, argv built by tests
                [sys.executable, *args],
                cwd=BACKEND_DIR,
                env=django_env(settings_module, values),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=False,
            )
        return cache[key]

    return run
