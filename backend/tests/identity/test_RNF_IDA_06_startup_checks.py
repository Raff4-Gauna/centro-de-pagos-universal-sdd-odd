"""Start-up checks of identity (RN-IDA-01, RN-IDA-16, RNF-IDA-06, Q-122, design.md §7.5, §10).

* The fake OIDC provider only starts with the dev and test settings: prod (also staging's) does not
  start with it, and ``IdentityConfig.ready()`` refuses it wherever ``IDENTITY_FAKE_OIDC_ALLOWED``
  is off.
* Every secret is distinct: ``checks.py`` fails when two share a value, naming settings only.
* Prod pins Google's endpoints and issuer exactly, and its BFF credentials are long and never the
  public placeholder of ``env.example``.

A process start with other settings runs in a subprocess (``run_django``).
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.core.checks import Error, Warning
from django.core.exceptions import ImproperlyConfigured
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity import checks
from apps.identity.oidc import provider
from tests.config._env_example import root_vars
from tests.config.test_AC_PLT_03_missing_required_var import PROD, VALID_PROD_ENV
from tests.config.test_AC_PLT_04_check_deploy import assert_does_not_start, output_of
from tests.conftest import RunDjango

SHARED = "sentinel-shared-value-of-two-settings"
# Stand-ins, not secrets.
DJANGO_VALUE = "sentinel-django-secret-key-value"
GOOGLE_VALUE = "sentinel-google-client-value"
OTHER_TOKEN_ENDPOINT = "https://sentinel-token.example/token"  # noqa: S105 - a URL
BFF = "IDENTITY_BFF_CREDENTIALS"
# prod.py's minimum; prod.py itself is not importable here (ProdEnv validates this environment).
BFF_CREDENTIAL_MIN_LENGTH = 32


@pytest.fixture
def distinct_secrets(settings: SettingsWrapper) -> SettingsWrapper:
    settings.SECRET_KEY = DJANGO_VALUE
    settings.IDENTITY_JWT_SIGNING_KEY = "sentinel-jwt-signing-key-value"
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = GOOGLE_VALUE
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr("sentinel-bff-current"),)
    return settings


def test_RNF_IDA_06_fake_provider_fails_in_prod_settings(run_django: RunDjango) -> None:
    values = {**VALID_PROD_ENV, "IDENTITY_OIDC_PROVIDER": "fake"}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert result.returncode != 0
    assert "django.core.exceptions.ImproperlyConfigured" in result.stderr
    assert provider.FAKE_NOT_ALLOWED in result.stderr
    assert "sentinel" not in output_of(result).lower()


def test_RNF_IDA_06_ready_refuses_the_fake_provider_without_the_dev_setting(
    settings: SettingsWrapper,
) -> None:
    settings.IDENTITY_OIDC_PROVIDER = "fake"
    settings.IDENTITY_FAKE_OIDC_ALLOWED = False
    with pytest.raises(ImproperlyConfigured, match="Q-122"):
        apps.get_app_config("identity").ready()
    settings.IDENTITY_FAKE_OIDC_ALLOWED = True
    apps.get_app_config("identity").ready()


def test_RNF_IDA_06_only_dev_and_test_allow_the_fake_provider(run_django: RunDjango) -> None:
    from config.settings import base, dev, test

    assert base.IDENTITY_FAKE_OIDC_ALLOWED is False
    assert dev.IDENTITY_FAKE_OIDC_ALLOWED is True
    assert test.IDENTITY_FAKE_OIDC_ALLOWED is True
    probe = "import django; from django.conf import settings; django.setup(); "
    probe += "print(settings.IDENTITY_FAKE_OIDC_ALLOWED)"
    result = run_django("-c", probe, settings_module=PROD, values=VALID_PROD_ENV)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "False"


@pytest.mark.usefixtures("distinct_secrets")
@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("SECRET_KEY", "IDENTITY_JWT_SIGNING_KEY"),
        ("SECRET_KEY", "IDENTITY_GOOGLE_CLIENT_SECRET"),
        ("SECRET_KEY", BFF),
        ("IDENTITY_JWT_SIGNING_KEY", "IDENTITY_GOOGLE_CLIENT_SECRET"),
        ("IDENTITY_JWT_SIGNING_KEY", BFF),
        ("IDENTITY_GOOGLE_CLIENT_SECRET", BFF),
    ],
)
def test_RN_IDA_16_equal_secrets_fail_check(
    settings: SettingsWrapper, first: str, second: str
) -> None:
    for name in (first, second):
        if name == BFF:
            # The previous credential of a rotation counts as much as the current one.
            settings.IDENTITY_BFF_CREDENTIALS = (
                SecretStr("sentinel-bff-current"),
                SecretStr(SHARED),
            )
        else:
            setattr(settings, name, SHARED)
    errors = checks.secrets_are_distinct(None)
    assert [error.id for error in errors] == [checks.EQUAL_SECRETS]
    assert all(isinstance(error, Error) for error in errors)
    shown = {"SECRET_KEY": "DJANGO_SECRET_KEY"}
    assert shown.get(first, first) in errors[0].msg
    assert shown.get(second, second) in errors[0].msg
    assert SHARED not in errors[0].msg + str(errors[0].hint)


@pytest.mark.usefixtures("distinct_secrets")
def test_RN_IDA_16_distinct_or_unset_secrets_pass(settings: SettingsWrapper) -> None:
    assert checks.secrets_are_distinct(None) == []
    # Unset is not shared: without a Google client nor a signer, nothing collides.
    settings.IDENTITY_JWT_SIGNING_KEY = ""
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = ""
    settings.IDENTITY_BFF_CREDENTIALS = ()
    assert checks.secrets_are_distinct(None) == []
    # The same credential twice in the BFF list is one purpose, not two.
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr("sentinel-bff"), SecretStr("sentinel-bff"))
    assert checks.secrets_are_distinct(None) == []


def test_RN_IDA_01_prod_pins_googles_endpoints(
    settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.IDENTITY_FAKE_OIDC_ALLOWED = False
    settings.IDENTITY_OIDC_PROVIDER = "google"
    assert checks.provider_is_google_in_prod(None) == []
    altered = provider.OidcEndpoints(
        authorization_endpoint=provider.GOOGLE_ENDPOINTS.authorization_endpoint,
        token_endpoint=OTHER_TOKEN_ENDPOINT,
        jwks_uri=provider.GOOGLE_ENDPOINTS.jwks_uri,
        issuers=provider.GOOGLE_ENDPOINTS.issuers | {"https://sentinel-issuer.example"},
    )
    monkeypatch.setattr(provider, "oidc_endpoints", lambda: altered)
    errors = checks.provider_is_google_in_prod(None)
    assert [error.id for error in errors] == [checks.NOT_GOOGLE_IN_PROD]
    assert "sentinel" not in errors[0].msg


def test_RN_IDA_01_prod_check_refuses_the_fake_provider(settings: SettingsWrapper) -> None:
    settings.IDENTITY_OIDC_PROVIDER = "fake"
    settings.IDENTITY_FAKE_OIDC_ALLOWED = False
    assert [error.id for error in checks.provider_is_google_in_prod(None)] == [
        checks.NOT_GOOGLE_IN_PROD
    ]
    # dev and test run the fake provider on purpose: not this check's business there.
    settings.IDENTITY_FAKE_OIDC_ALLOWED = True
    assert checks.provider_is_google_in_prod(None) == []


def test_RNF_IDA_06_login_on_without_client_warns(settings: SettingsWrapper) -> None:
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "IDENTITY_GOOGLE_LOGIN": True}
    settings.IDENTITY_GOOGLE_CLIENT_ID = ""
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = GOOGLE_VALUE
    settings.IDENTITY_GOOGLE_REDIRECT_URI = "https://hub.test/api/auth/google/callback"
    warnings = checks.login_has_a_client(None)
    assert [warning.id for warning in warnings] == [checks.LOGIN_WITHOUT_CLIENT]
    assert isinstance(warnings[0], Warning)
    assert "IDENTITY_GOOGLE_CLIENT_ID" in warnings[0].msg
    assert "sentinel" not in warnings[0].msg
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "IDENTITY_GOOGLE_LOGIN": False}
    assert checks.login_has_a_client(None) == []


@pytest.mark.parametrize(
    ("value", "error_type"),
    [
        ("sentinel-short-bff", "bff_credential_too_short"),
        ("sentinel-long-enough-bff-credential-value," + "s" * 20, "bff_credential_too_short"),
        # The public placeholder of env.example: long enough, and known to everybody.
        (root_vars()[BFF], "bff_credential_public"),
    ],
    ids=["short", "short-previous", "env-example-placeholder"],
)
def test_RN_IDA_16_weak_bff_credential_in_prod_does_not_start(
    run_django: RunDjango, value: str, error_type: str
) -> None:
    values = {**VALID_PROD_ENV, BFF: value}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    for part in value.split(","):
        assert_does_not_start(result, BFF, error_type, part)


def test_RN_IDA_16_strong_bff_credentials_start_in_prod(run_django: RunDjango) -> None:
    current = "sentinel-current-bff-credential-value"
    previous = "sentinel-previous-bff-credential-value"
    assert min(len(current), len(previous)) >= BFF_CREDENTIAL_MIN_LENGTH
    values = {**VALID_PROD_ENV, BFF: f"{current},{previous}"}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert result.returncode == 0, output_of(result)
