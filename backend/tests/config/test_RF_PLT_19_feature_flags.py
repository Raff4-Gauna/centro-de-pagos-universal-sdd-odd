"""RF-PLT-19 (Q-052, C-17): feature flags by environment variable, off by default.

``apps/common/feature_flags.py`` holds ``REGISTRY`` (empty in 00) and ``is_enabled(name)``; the only
reader of ``FEATURE_<NAME>`` is ``config/settings/env.py`` (``load_feature_flags``), which every
settings module calls. A name that is not registered raises; an unregistered ``FEATURE_*`` variable
does not start (a typo must not leave a flag "believed on"), and neither does a value other than
``true``/``false``. Errors name the variable, never its value (C-06).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

import pytest
from django.core.exceptions import ImproperlyConfigured
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common import feature_flags
from config.settings.env import FEATURE_PREFIX, load_feature_flags
from tests.config.test_AC_PLT_03_missing_required_var import SENTINEL, VALID_PROD_ENV

RunDjango = Callable[..., subprocess.CompletedProcess[str]]

DEMO = "DEMO_FLAG"


@pytest.fixture
def demo_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """``REGISTRY`` with one test flag and no ``FEATURE_*`` variable in this process."""
    for variable in [name for name in os.environ if name.startswith(FEATURE_PREFIX)]:
        monkeypatch.delenv(variable)
    monkeypatch.setitem(feature_flags.REGISTRY, DEMO, "test only")
    return feature_flags.REGISTRY


def test_RF_PLT_19_flag_off_by_default(
    demo_registry: dict[str, str], settings: SettingsWrapper
) -> None:
    assert load_feature_flags(demo_registry)[DEMO] is False
    settings.FEATURE_FLAGS = load_feature_flags(demo_registry)
    assert feature_flags.is_enabled(DEMO) is False
    # A settings module that forgot FEATURE_FLAGS leaves every flag off too.
    del settings.FEATURE_FLAGS
    assert feature_flags.is_enabled(DEMO) is False


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("TRUE", True), ("false", False)])
def test_RF_PLT_19_flag_follows_its_variable(
    demo_registry: dict[str, str],
    settings: SettingsWrapper,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: bool,
) -> None:
    monkeypatch.setenv(f"FEATURE_{DEMO}", value)
    settings.FEATURE_FLAGS = load_feature_flags(demo_registry)
    assert feature_flags.is_enabled(DEMO) is expected


def test_RF_PLT_19_empty_variable_counts_as_unset(
    demo_registry: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"FEATURE_{DEMO}", "")
    monkeypatch.setenv("FEATURE_NOT_REGISTERED", "")
    assert load_feature_flags(demo_registry)[DEMO] is False


def test_RF_PLT_19_unregistered_flag_name_raises(demo_registry: dict[str, str]) -> None:
    with pytest.raises(KeyError):
        feature_flags.is_enabled("NOT_REGISTERED")


def test_RF_PLT_19_invalid_value_fails_naming_only_the_variable(
    demo_registry: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(f"FEATURE_{DEMO}", "sentinel-yes")
    monkeypatch.setenv("FEATURE_NOT_REGISTERED", "sentinel-on")
    with pytest.raises(ImproperlyConfigured) as info:
        load_feature_flags(demo_registry)
    message = str(info.value)
    assert f"- FEATURE_{DEMO}: bool_format" in message
    assert "- FEATURE_NOT_REGISTERED: feature_unregistered" in message
    assert SENTINEL not in message.lower()
    assert info.value.__context__ is None


@pytest.mark.parametrize("module", ["dev", "test", "prod"])
def test_RF_PLT_19_unregistered_feature_env_var_prevents_start(
    run_django: RunDjango, module: str
) -> None:
    values = {**VALID_PROD_ENV, "FEATURE_TYPO_CHECKOUT": "sentinel-true"}
    result = run_django(
        "manage.py", "check", settings_module=f"config.settings.{module}", values=values
    )
    assert result.returncode != 0
    assert "django.core.exceptions.ImproperlyConfigured" in result.stderr
    assert "- FEATURE_TYPO_CHECKOUT: feature_unregistered" in result.stderr
    assert SENTINEL not in (result.stdout + result.stderr).lower()


def test_RF_PLT_19_settings_expose_every_registered_flag(settings: SettingsWrapper) -> None:
    # The running settings (config.settings.test) loaded the flags at start-up.
    assert dict.fromkeys(feature_flags.REGISTRY, False) == settings.FEATURE_FLAGS
