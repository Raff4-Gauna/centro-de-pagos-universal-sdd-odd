"""``PLATFORM_OPERATOR_EMAILS``: who may run the operator's commands (SPEC-02 design.md §4.5).

A comma-separated list of emails, normalized as ``--operator`` is (trimmed, lower case). Empty or
unset is allowed everywhere, prod included: the Hub starts and every operator command refuses to
run (``apps.common.platform_operators``). That keeps the CI smoke, which runs prod settings with
``env.example`` (empty value), starting. A wrong item does not start, without showing it.
"""

from __future__ import annotations

import pytest

from config.settings.env import PlatformEnv
from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.config.test_AC_PLT_04_check_deploy import assert_does_not_start, output_of
from tests.config.test_RNF_TEN_03_frontend_base_url import REQUIRED
from tests.conftest import RunDjango

NAME = "PLATFORM_OPERATOR_EMAILS"


def env_with(value: str) -> PlatformEnv:
    return PlatformEnv(**REQUIRED, PLATFORM_OPERATOR_EMAILS=value)  # type: ignore[arg-type]


def test_RF_TEN_07_unset_is_an_empty_list() -> None:
    assert PlatformEnv(**REQUIRED).PLATFORM_OPERATOR_EMAILS == []  # type: ignore[arg-type]


def test_RF_TEN_07_emails_are_normalized_and_deduplicated() -> None:
    value = " Ops@Hub.Example , soporte@hub.example,ops@hub.example"
    assert env_with(value).PLATFORM_OPERATOR_EMAILS == ["ops@hub.example", "soporte@hub.example"]


@pytest.mark.parametrize("value", ["ops", "ops@hub.example,not an email", "ops@hub.example,,x@y.z"])
def test_RF_TEN_07_anything_but_emails_does_not_start(value: str) -> None:
    with pytest.raises(ValueError, match=r"operator_email_format|csv_empty_item"):
        env_with(value)


@pytest.mark.parametrize("value", [None, ""])
def test_RF_TEN_07_prod_starts_without_operators(run_django: RunDjango, value: str | None) -> None:
    values = dict(VALID_PROD_ENV) if value is None else {**VALID_PROD_ENV, NAME: value}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert result.returncode == 0, output_of(result)


def test_RF_TEN_07_prod_refuses_a_bad_item_without_showing_it(run_django: RunDjango) -> None:
    value = "secret-looking-value"
    result = run_django(
        "manage.py", "check", settings_module=PROD, values={**VALID_PROD_ENV, NAME: value}
    )
    assert_does_not_start(result, NAME, "operator_email_format", value)
