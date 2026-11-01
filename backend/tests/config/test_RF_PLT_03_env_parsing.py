# ruff: noqa: N999 - the module name carries the uppercase AC/RF/C ID (AGENTS.md); flagged
# since tests/config/ is a package. The repo-wide fix belongs in ruff.toml (T-PLT-08 review).
"""RF-PLT-03 (RN-PLT-02): how ``PlatformEnv`` turns variables into settings.

T-PLT-08 review N-3 (``databases()``) and N-6 (an empty variable counts as unset).

In-process unit tests: ``PlatformEnv`` reads the environment when it is instantiated, so
``monkeypatch`` and keyword arguments are enough; nothing here starts Django.
"""

from __future__ import annotations

import pytest
from config.settings.env import PlatformEnv

REQUIRED = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "REDIS_URL": "redis://redis.example:6379/0",
}


def databases_for(url: str) -> dict[str, object]:
    return PlatformEnv(**REQUIRED, DATABASE_URL=url).databases()["default"]


def test_RF_PLT_03_databases_decodes_percent_encoded_credentials() -> None:
    default = databases_for("postgresql://hub%40ops:p%3Ass%2Fw%25rd@db.example:6543/hub")
    assert default == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "hub",
        "USER": "hub@ops",
        "PASSWORD": "p:ss/w%rd",
        "HOST": "db.example",
        "PORT": "6543",
        "OPTIONS": {"connect_timeout": 2},
    }


def test_RF_PLT_03_databases_without_port_or_user() -> None:
    default = databases_for("postgres://db.example/hub")
    assert (default["USER"], default["PASSWORD"], default["HOST"], default["PORT"]) == (
        "",
        "",
        "db.example",
        "",
    )
    assert default["NAME"] == "hub"


def test_RF_PLT_03_empty_optional_var_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DATABASE_URL", "postgres://db.example/hub")
    for name in ("DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS", "APP_VERSION"):
        monkeypatch.setenv(name, "")
    env = PlatformEnv()
    assert env.DJANGO_DEBUG is False
    assert env.DJANGO_ALLOWED_HOSTS == ["localhost", "127.0.0.1"]
    assert env.APP_VERSION == "unknown"
