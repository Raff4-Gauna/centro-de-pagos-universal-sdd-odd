"""RN-IDA-16, RN-PLT-02, C-06: the Hub's JWT keys, at start and in memory.

Every key is generated here at run time. A key that cannot sign or verify stops the process naming
the variable, never showing its value, and the signing key stays masked wherever it can be rendered.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.core.exceptions import ImproperlyConfigured

from apps.common.logging.report_filter import CredentialSafeReporterFilter
from apps.identity.tokens.keys import active_signing_key, verification_key
from config.settings.env import PlatformEnv, load_env
from tests.config.test_AC_PLT_03_missing_required_var import SENTINEL, VALID_PROD_ENV

RunDjango = Callable[..., subprocess.CompletedProcess[str]]


def private_pem(key: Any) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def public_pem(key: Any) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


P256 = ec.generate_private_key(ec.SECP256R1())
OTHER_P256 = ec.generate_private_key(ec.SECP256R1())
P384 = ec.generate_private_key(ec.SECP384R1())
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
VERIFICATION_KEYS = json.dumps({"k1": public_pem(P256)})
GOOD_PAIR = {
    "IDENTITY_JWT_SIGNING_KID": "k1",
    "IDENTITY_JWT_SIGNING_KEY": private_pem(P256),
    "IDENTITY_JWT_VERIFICATION_KEYS": VERIFICATION_KEYS,
}
SIGNING = "IDENTITY_JWT_SIGNING_KEY"
VERIFICATION = "IDENTITY_JWT_VERIFICATION_KEYS"


def set_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_RN_PLT_02_good_pair_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, GOOD_PAIR)
    env = load_env(PlatformEnv)
    assert env.IDENTITY_JWT_SIGNING_KID == "k1"
    assert list(env.IDENTITY_JWT_VERIFICATION_KEYS) == ["k1"]


def test_RN_PLT_02_verification_only_process_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, {VERIFICATION: VERIFICATION_KEYS})
    assert load_env(PlatformEnv).IDENTITY_JWT_SIGNING_KID == ""


@pytest.mark.parametrize(
    ("variable", "value", "error"),
    [
        pytest.param(SIGNING, "not a pem", "jwt_signing_key_format", id="garbage"),
        pytest.param(SIGNING, private_pem(RSA_KEY), "jwt_signing_key_format", id="rsa"),
        pytest.param(SIGNING, private_pem(P384), "jwt_signing_key_format", id="p384"),
        pytest.param(SIGNING, public_pem(P256), "jwt_signing_key_format", id="public"),
        pytest.param(VERIFICATION, "{not json", "json_object", id="not-json"),
        pytest.param(VERIFICATION, '["k1"]', "json_object", id="json-list"),
        pytest.param(VERIFICATION, '{"k1": 1}', "string_type", id="json-number"),
        pytest.param(
            VERIFICATION,
            json.dumps({"k1": private_pem(P256)}),
            "jwt_verification_key_format",
            id="private-as-public",
        ),
        pytest.param(
            VERIFICATION,
            json.dumps({"k1": public_pem(P384)}),
            "jwt_verification_key_format",
            id="public-p384",
        ),
    ],
)
def test_RN_PLT_02_unusable_key_fails_naming_the_variable_only(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, error: str
) -> None:
    set_env(monkeypatch, {**GOOD_PAIR, variable: value})
    with pytest.raises(ImproperlyConfigured) as info:
        load_env(PlatformEnv)
    message = str(info.value)
    assert f"- {variable}" in message
    assert error in message
    assert value not in message
    assert "BEGIN" not in message
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


@pytest.mark.parametrize(
    ("change", "error"),
    [
        pytest.param({"IDENTITY_JWT_SIGNING_KID": ""}, "jwt_signing_pair", id="no-kid"),
        pytest.param({SIGNING: ""}, "jwt_signing_pair", id="no-key"),
        pytest.param(
            {"IDENTITY_JWT_SIGNING_KID": "not-listed"},
            "jwt_signing_key_not_verifiable",
            id="kid-not-listed",
        ),
        pytest.param(
            {VERIFICATION: json.dumps({"k1": public_pem(OTHER_P256)})},
            "jwt_signing_key_not_verifiable",
            id="other-public-key",
        ),
    ],
)
def test_RN_PLT_02_signer_must_verify_its_own_tokens(
    monkeypatch: pytest.MonkeyPatch, change: dict[str, str], error: str
) -> None:
    set_env(monkeypatch, {**GOOD_PAIR, **change})
    with pytest.raises(ImproperlyConfigured, match=error):
        load_env(PlatformEnv)


def test_RN_PLT_02_prod_with_a_bad_key_does_not_start(run_django: RunDjango) -> None:
    result = run_django(
        "manage.py",
        "check",
        settings_module="config.settings.prod",
        values={**VALID_PROD_ENV, SIGNING: f"{SENTINEL} not a pem"},
    )
    assert result.returncode != 0
    assert f"- {SIGNING}: jwt_signing_key_format" in result.stderr
    assert SENTINEL not in (result.stdout + result.stderr).lower()


def test_C_06_env_masks_the_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, GOOD_PAIR)
    env = load_env(PlatformEnv)
    for text in (repr(env), str(env), str(env.model_dump()), env.model_dump_json()):
        assert "PRIVATE KEY" not in text


def test_C_06_error_reports_hide_the_keys() -> None:
    reporter = CredentialSafeReporterFilter()
    safe = reporter.get_safe_settings()
    assert "PRIVATE KEY" not in str(safe)
    assert safe[SIGNING] == reporter.cleansed_substitute
    assert safe["IDENTITY_JWT_ISSUER"] != reporter.cleansed_substitute  # the filter did run


def test_C_06_signing_key_repr_shows_only_the_kid() -> None:
    signing = active_signing_key()
    assert signing.kid in repr(signing)
    assert "key=" not in repr(signing)


def test_RNF_IDA_01_keys_are_parsed_once() -> None:
    # Verification is local and in memory: the PEM is not parsed on every request.
    kid = active_signing_key().kid
    assert verification_key(kid) is verification_key(kid)
    assert active_signing_key().key is active_signing_key().key


def test_RN_IDA_08_unknown_kid_has_no_key() -> None:
    assert verification_key("unknown") is None
