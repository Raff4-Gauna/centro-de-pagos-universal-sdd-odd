"""The gateway and the verifier of the process, from settings (design.md §8.3, RNF-IDA-01)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.oidc.provider import (
    get_google_gateway,
    get_id_token_verifier,
    google_oidc_config,
)
from tests.fakes import google

CLIENT_VALUE = "a-client-value-nobody-should-read"


@pytest.fixture(autouse=True)
def google_settings(settings: SettingsWrapper) -> None:
    config = google.config()
    settings.IDENTITY_OIDC_PROVIDER = "google"
    settings.IDENTITY_GOOGLE_CLIENT_ID = config.client_id
    settings.IDENTITY_GOOGLE_CLIENT_SECRET = CLIENT_VALUE
    settings.IDENTITY_GOOGLE_REDIRECT_URI = config.redirect_uri


def test_config_comes_from_settings_with_googles_endpoints() -> None:
    config = google_oidc_config()
    assert config.client_id == google.CLIENT_ID
    assert config.client_secret == CLIENT_VALUE
    assert config.redirect_uri == google.config().redirect_uri
    assert config.token_endpoint == google.TOKEN_ENDPOINT
    assert config.jwks_uri == google.JWKS_URI
    assert CLIENT_VALUE not in repr(config)


def test_RNF_IDA_01_one_verifier_per_process_keeps_the_jwks_cache() -> None:
    # A verifier per request would start with an empty JWKS cache and fetch Google's keys each time.
    assert get_id_token_verifier() is get_id_token_verifier()
    assert get_google_gateway() is get_google_gateway()


def test_changed_settings_never_reuse_the_previous_client(settings: SettingsWrapper) -> None:
    before = get_id_token_verifier()
    settings.IDENTITY_GOOGLE_CLIENT_ID = google.OTHER_CLIENT_ID
    assert get_id_token_verifier() is not before


@pytest.mark.parametrize(
    "name",
    [
        "IDENTITY_GOOGLE_CLIENT_ID",
        "IDENTITY_GOOGLE_CLIENT_SECRET",
        "IDENTITY_GOOGLE_REDIRECT_URI",
    ],
)
def test_RN_IDA_16_unconfigured_client_fails_closed_naming_only_the_setting(
    settings: SettingsWrapper, name: str
) -> None:
    setattr(settings, name, "")
    with pytest.raises(ImproperlyConfigured) as info:
        get_google_gateway()
    assert name in str(info.value)
    assert CLIENT_VALUE not in str(info.value)


def test_RNF_IDA_06_fake_provider_uses_dev_oidc_never_google(settings: SettingsWrapper) -> None:
    settings.IDENTITY_OIDC_PROVIDER = "fake"
    settings.IDENTITY_FAKE_OIDC_BASE_URL = "http://localhost:8000/"
    config = google_oidc_config()
    assert config.authorization_endpoint == "http://localhost:8000/dev-oidc/authorize"
    assert config.token_endpoint == "http://localhost:8000/dev-oidc/token"  # noqa: S105 - a URL
    assert config.jwks_uri == "http://localhost:8000/dev-oidc/jwks"
    assert config.issuers == frozenset({"http://localhost:8000/dev-oidc"})
    assert config.client_id == google.CLIENT_ID


@pytest.mark.parametrize(("allowed", "base_url"), [(False, "http://localhost:8000"), (True, "")])
def test_RNF_IDA_06_fake_provider_fails_closed_where_not_allowed(
    settings: SettingsWrapper, allowed: bool, base_url: str
) -> None:
    settings.IDENTITY_OIDC_PROVIDER = "fake"
    settings.IDENTITY_FAKE_OIDC_ALLOWED = allowed
    settings.IDENTITY_FAKE_OIDC_BASE_URL = base_url
    with pytest.raises(ImproperlyConfigured):
        get_google_gateway()
    with pytest.raises(ImproperlyConfigured):
        get_id_token_verifier()
