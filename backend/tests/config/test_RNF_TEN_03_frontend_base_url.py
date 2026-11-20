"""``FRONTEND_BASE_URL``: the app's origin the invitation link is built on (SPEC-02 design.md §6).

Only ``scheme://host[:port]``: a path, query, fragment or credentials would end up in front of the
token of ``<origin>/invitacion#token=...`` (RNF-TEN-03). Empty is unset (creating an invitation
fails closed). Prod takes only ``https`` (``ProdEnv``), in a subprocess like the other prod checks.
"""

from __future__ import annotations

import pytest

from config.settings.env import PlatformEnv
from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.config.test_AC_PLT_04_check_deploy import assert_does_not_start, output_of
from tests.conftest import RunDjango

REQUIRED = {
    "DJANGO_SECRET_KEY": "test-only-not-a-secret",
    "DATABASE_URL": "postgres://db.example/hub",
    "REDIS_URL": "redis://redis.example:6379/0",
}
NAME = "FRONTEND_BASE_URL"


def env_with(value: str) -> PlatformEnv:
    return PlatformEnv(**REQUIRED, FRONTEND_BASE_URL=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value", ["http://localhost:3000", "https://app.hub.example", "https://[::1]:8443", ""]
)
def test_RNF_TEN_03_an_origin_or_nothing_is_accepted(value: str) -> None:
    assert value == env_with(value).FRONTEND_BASE_URL


@pytest.mark.parametrize(
    "value",
    [
        "localhost:3000",
        "ftp://app.hub.example",
        "https://app.hub.example/",
        "https://app.hub.example/invitacion",
        "https://app.hub.example?x=1",
        "https://app.hub.example#token=",
        "https://user:pass@app.hub.example",
        "https://app.hub.example:99999",
        "HTTPS://app.hub.example",
        "https://",
    ],
)
def test_RNF_TEN_03_anything_but_an_origin_does_not_start(value: str) -> None:
    with pytest.raises(ValueError, match="origin_format"):
        env_with(value)


def test_RNF_TEN_03_prod_refuses_plain_http(run_django: RunDjango) -> None:
    value = "http://app.hub.example"
    result = run_django(
        "manage.py", "check", settings_module=PROD, values={**VALID_PROD_ENV, NAME: value}
    )
    assert_does_not_start(result, NAME, "origin_not_https", value)


def test_RNF_TEN_03_prod_starts_with_https(run_django: RunDjango) -> None:
    values = {**VALID_PROD_ENV, NAME: "https://app.hub.example"}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert result.returncode == 0, output_of(result)
