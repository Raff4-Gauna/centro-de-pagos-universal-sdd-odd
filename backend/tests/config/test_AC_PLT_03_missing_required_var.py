"""AC-PLT-03 (RN-PLT-02) and RF-PLT-03: settings validated at start-up, errors without values.

Every start runs in a subprocess (``run_django``) with ``config.settings.prod``: the process must
not start when a required variable is missing or malformed, the error must name the variable and it
must not carry any value. Every value in the base environment contains the word ``sentinel``, so a
case-insensitive search over stdout + stderr catches a leak of any of them, the offending one too.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

import pytest

RunDjango = Callable[..., subprocess.CompletedProcess[str]]

PROD = "config.settings.prod"
SENTINEL = "sentinel"

# A complete, valid prod environment. Each value carries the sentinel. The secret key is already
# strong (>= 50 chars, >= 5 distinct, no "django-insecure") so T-PLT-09's check keeps it valid, and
# low-entropy so gitleaks does not take it for a real key.
VALID_PROD_ENV = {
    "DJANGO_SECRET_KEY": "sentinel-not-a-secret-" * 3,
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": "sentinel-host-a.example,sentinel-host-b.example",
    "DATABASE_URL": "postgres://sentinel_user:sentinel-db-pass@sentinel-db-host:5432/sentinel_db",
    "REDIS_URL": "redis://:sentinel-redis-pass@sentinel-redis-host:6379/0",
    "APP_VERSION": "sentinel-version",
}

# RN-PLT-02: required in prod, no default.
REQUIRED_IN_PROD = ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DATABASE_URL", "REDIS_URL")

# (variable, malformed value). Each value carries the sentinel too. An empty value counts as
# missing (env_ignore_empty), see test_AC_PLT_03_empty_required_var_counts_as_missing.
_DB = "postgres://sentinel_user:sentinel-pass@sentinel-host:5432"
INVALID_VALUES = (
    ("DJANGO_DEBUG", "sentinel-maybe"),
    ("DJANGO_DEBUG", "1"),
    ("DJANGO_ALLOWED_HOSTS", "sentinel-a.example,,sentinel-b.example"),
    ("DATABASE_URL", "not a url sentinel"),
    ("DATABASE_URL", "mysql://sentinel_user:sentinel-pass@sentinel-host:3306/sentinel_db"),
    # Only postgres/postgresql: a driver suffix is not what Django's backend speaks.
    ("DATABASE_URL", "postgresql+asyncpg://sentinel_user:sentinel-pass@sentinel-host/sentinel_db"),
    ("DATABASE_URL", _DB),
    ("DATABASE_URL", "postgres://sentinel-a:5432,sentinel-b:5432/sentinel_db"),
    # Fail closed: options in the URL would be silently dropped by databases().
    ("DATABASE_URL", f"{_DB}/sentinel_db?sslmode=disable"),
    ("DATABASE_URL", f"{_DB}/sentinel_db#sentinel"),
    ("DATABASE_URL", f"{_DB}/sentinel_db/extra"),
    ("REDIS_URL", "http://sentinel-redis-host:6379/0"),
)


def without(variable: str) -> dict[str, str]:
    return {key: value for key, value in VALID_PROD_ENV.items() if key != variable}


def with_value(variable: str, value: str) -> dict[str, str]:
    return {**VALID_PROD_ENV, variable: value}


def start_prod(run_django: RunDjango, values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run_django("manage.py", "check", settings_module=PROD, values=values)


def assert_fails_naming_only(result: subprocess.CompletedProcess[str], variable: str) -> str:
    """The start failed with ImproperlyConfigured listing ``variable`` and no other variable."""
    assert result.returncode != 0
    assert "django.core.exceptions.ImproperlyConfigured" in result.stderr
    assert f"- {variable}: " in result.stderr
    others = [name for name in VALID_PROD_ENV if name != variable]
    assert [name for name in others if f"- {name}: " in result.stderr] == []
    return result.stderr


def test_AC_PLT_03_complete_env_starts(run_django: RunDjango) -> None:
    # Control: the base environment is valid, so every failure below comes from the one change.
    result = start_prod(run_django, VALID_PROD_ENV)
    assert result.returncode == 0, result.stderr
    assert "System check identified no issues" in result.stdout


@pytest.mark.parametrize("variable", REQUIRED_IN_PROD)
def test_AC_PLT_03_each_missing_required_var_fails_naming_it(
    run_django: RunDjango, variable: str
) -> None:
    stderr = assert_fails_naming_only(start_prod(run_django, without(variable)), variable)
    assert f"- {variable}: missing" in stderr


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        pytest.param(name, value, id=f"{name}-{index}")
        for index, (name, value) in enumerate(INVALID_VALUES)
    ],
)
def test_AC_PLT_03_invalid_format_fails_naming_it(
    run_django: RunDjango, variable: str, value: str
) -> None:
    stderr = assert_fails_naming_only(start_prod(run_django, with_value(variable, value)), variable)
    assert f"- {variable}: missing" not in stderr


@pytest.mark.parametrize("variable", REQUIRED_IN_PROD)
def test_AC_PLT_03_empty_required_var_counts_as_missing(
    run_django: RunDjango, variable: str
) -> None:
    stderr = assert_fails_naming_only(start_prod(run_django, with_value(variable, "")), variable)
    assert f"- {variable}: missing" in stderr


@pytest.mark.parametrize(
    "values",
    [pytest.param(without(name), id=f"missing-{name}") for name in REQUIRED_IN_PROD]
    + [pytest.param(with_value(name, ""), id=f"empty-{name}") for name in REQUIRED_IN_PROD]
    + [
        pytest.param(with_value(name, value), id=f"invalid-{name}-{index}")
        for index, (name, value) in enumerate(INVALID_VALUES)
    ],
)
def test_AC_PLT_03_error_contains_no_sentinel_value(
    run_django: RunDjango, values: dict[str, str]
) -> None:
    result = start_prod(run_django, values)
    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert SENTINEL not in output
    # The search is meaningful: the values given to the process do carry the sentinel.
    assert any(SENTINEL in value for value in values.values())


# Reads the effective settings in a fresh process; the JSON on stdout is the only output.
READ_LOCALE = (
    "import json, sys, django; django.setup(); from django.conf import settings as s; "
    "sys.stdout.write(json.dumps([s.USE_TZ, s.TIME_ZONE, s.LANGUAGE_CODE]))"
)


@pytest.mark.parametrize("module", ["dev", "test", "prod"])
def test_RF_PLT_03_timezone_and_language_defaults(run_django: RunDjango, module: str) -> None:
    result = run_django(
        "-c", READ_LOCALE, settings_module=f"config.settings.{module}", values=VALID_PROD_ENV
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [True, "America/Argentina/Buenos_Aires", "es-ar"]
