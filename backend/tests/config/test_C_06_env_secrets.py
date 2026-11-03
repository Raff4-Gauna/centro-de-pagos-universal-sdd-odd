# ruff: noqa: N999 - the module name carries the uppercase AC/RF/C ID (AGENTS.md); flagged
# since tests/config/ is a package. The repo-wide fix belongs in ruff.toml (T-PLT-08 review).
"""C-06 (RN-PLT-02): the validated environment never shows a secret (T-PLT-08 review B-2, N-1).

``DJANGO_SECRET_KEY``, ``DATABASE_URL`` and ``REDIS_URL`` carry credentials: ``repr``, ``str`` and
``model_dump`` of the env object mask them, the settings modules drop the object once they have read
it (``del _env``), and a failed ``load_env`` keeps no ``ValidationError`` in ``__context__`` or
``__cause__`` (that error renders the inputs). Only the secrets carry the sentinel here; the hosts
and the version are not secrets and may be shown.
"""

from __future__ import annotations

import subprocess
import traceback
from collections.abc import Callable

import pytest
from config.settings.env import PlatformEnv, load_env
from django.core.exceptions import ImproperlyConfigured

RunDjango = Callable[..., subprocess.CompletedProcess[str]]

SENTINEL = "sentinel"
ENV_WITH_SECRETS = {
    "DJANGO_SECRET_KEY": "sentinel-not-a-secret-" * 3,
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": "hub.example",
    "DATABASE_URL": "postgres://sentinel_user:sentinel-db-pass@sentinel-db-host:5432/sentinel_db",
    "REDIS_URL": "redis://:sentinel-redis-pass@sentinel-redis-host:6379/0",
    "APP_VERSION": "1.2.3",
}


def renderings(env: PlatformEnv) -> list[str]:
    return [repr(env), str(env), str(env.model_dump()), env.model_dump_json()]


def test_C_06_env_repr_and_str_contain_no_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in ENV_WITH_SECRETS.items():
        monkeypatch.setenv(name, value)
    env = load_env(PlatformEnv)
    for text in renderings(env):
        assert SENTINEL not in text.lower()
        assert "hub.example" in text  # the rendering did happen; only secrets are masked
    # The values are still there for the settings to use.
    assert SENTINEL in env.DATABASE_URL.get_secret_value().hosts()[0]["password"]

    # A failure keeps no trace of the inputs: no chained ValidationError, nothing in the text.
    monkeypatch.setenv("DATABASE_URL", "mysql://sentinel_user:sentinel-db-pass@sentinel-host/db")
    with pytest.raises(ImproperlyConfigured) as info:
        load_env(PlatformEnv)
    error = info.value
    assert error.__context__ is None
    assert error.__cause__ is None
    # format_exception_only: the frames would show this test's own name, which has the sentinel.
    rendered = "".join(traceback.format_exception_only(error))
    assert "- DATABASE_URL: url_scheme" in rendered
    assert SENTINEL not in rendered.lower()


# Imports the settings module as Django would, then renders a fresh env object of its class.
RENDER_ENV = (
    "import importlib, os, sys\n"
    "from config.settings.env import PlatformEnv\n"
    "module = importlib.import_module(os.environ['DJANGO_SETTINGS_MODULE'])\n"
    "env = getattr(module, 'ProdEnv', PlatformEnv)()\n"
    "parts = [repr(env), str(env), env.model_dump_json(), str(hasattr(module, '_env'))]\n"
    "sys.stdout.write('|'.join(parts))\n"
)


@pytest.mark.parametrize("module", ["dev", "test", "prod"])
def test_C_06_settings_modules_keep_no_env_object(run_django: RunDjango, module: str) -> None:
    result = run_django(
        "-c", RENDER_ENV, settings_module=f"config.settings.{module}", values=ENV_WITH_SECRETS
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("|False")  # `del _env` ran
    assert SENTINEL not in (result.stdout + result.stderr).lower()
    assert "hub.example" in result.stdout
