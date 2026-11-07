"""Format of the refresh token, ``state``, ``nonce``, binding and PKCE (design.md §4.5, §5).

Pure: nothing here is stored or sent, that belongs to the session and login tasks.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable
from uuid import UUID

import pytest

from apps.identity.domain.errors import IdentityErrorCode, MalformedRefreshTokenError
from apps.identity.domain.secrets_format import (
    code_challenge_s256,
    generate_code_verifier,
    generate_nonce,
    generate_refresh_token,
    generate_state,
    hash_secret,
    is_login_binding,
    matches_hash,
    parse_refresh_token,
)

SID = UUID("0193c2f4-7a1e-7c3a-9d2b-5e8f1a2b3c4d")
URL_SECRET = re.compile(r"[A-Za-z0-9_-]{43}")


def test_RN_IDA_10_refresh_token_format_and_round_trip() -> None:
    token = generate_refresh_token(SID)
    prefix, sid, secret = token.split(".")
    assert prefix == "rt1"
    assert base64.urlsafe_b64decode(sid + "==") == SID.bytes
    assert URL_SECRET.fullmatch(secret)
    assert parse_refresh_token(token) == SID


def test_RN_IDA_10_refresh_tokens_never_repeat() -> None:
    assert generate_refresh_token(SID) != generate_refresh_token(SID)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda token: "",
        lambda token: "garbage",
        lambda token: token.replace("rt1.", "rt2.", 1),
        lambda token: token + "\n",
        lambda token: token + ".extra",
        lambda token: token[:-1],
        lambda token: token.rpartition(".")[0] + ".",
        lambda token: "rt1." + token.split(".")[2],
        lambda token: token[:-1] + "+",
        lambda token: token[:-1] + "ñ",
    ],
    ids=[
        "empty",
        "garbage",
        "unknown_version",
        "trailing_newline",
        "extra_segment",
        "short_secret",
        "empty_secret",
        "missing_sid",
        "not_base64url",
        "not_ascii",
    ],
)
def test_RN_IDA_10_malformed_refresh_token_is_rejected(mutate: Callable[[str], str]) -> None:
    with pytest.raises(MalformedRefreshTokenError):
        parse_refresh_token(mutate(generate_refresh_token(SID)))


def test_RN_IDA_10_non_canonical_base64_is_rejected() -> None:
    """Spare bits set: the same bytes once decoded, written as another string."""
    canonical = base64.urlsafe_b64encode(SID.bytes).rstrip(b"=").decode()
    alias = canonical[:-1] + chr(ord(canonical[-1]) + 1)
    assert base64.urlsafe_b64decode(alias + "==") == SID.bytes

    with pytest.raises(MalformedRefreshTokenError):
        parse_refresh_token(f"rt1.{alias}.{'A' * 43}")


def test_RNF_IDA_03_rejection_does_not_carry_the_token() -> None:
    token = generate_refresh_token(SID)[:-1]
    with pytest.raises(MalformedRefreshTokenError) as caught:
        parse_refresh_token(token)

    assert caught.value.code is IdentityErrorCode.TOKEN_INVALID
    assert token not in repr(caught.value)
    assert token not in str(caught.value)
    assert caught.value.__context__ is None


def test_RN_IDA_10_hash_is_sha256_hex_of_the_whole_token() -> None:
    token = generate_refresh_token(SID)
    assert hash_secret(token) == hashlib.sha256(token.encode()).hexdigest()
    assert len(hash_secret(token)) == 64


def test_RN_IDA_02_hash_accepts_any_text_a_client_can_send() -> None:
    """A lone surrogate survives ``json.loads``: it has to miss the lookup, not raise a 500."""
    assert len(hash_secret("\ud800")) == 64
    assert not matches_hash("\ud800", hash_secret("state"))


def test_RN_IDA_02_matches_hash() -> None:
    assert matches_hash("value", hash_secret("value"))
    assert not matches_hash("other", hash_secret("value"))


@pytest.mark.parametrize("generate", [generate_state, generate_nonce])
def test_RN_IDA_02_state_and_nonce_carry_32_random_bytes(generate: Callable[[], str]) -> None:
    value = generate()
    assert URL_SECRET.fullmatch(value)
    assert generate() != value


def test_RN_IDA_02_login_binding_format() -> None:
    assert is_login_binding(generate_state())
    for bad in ("", "a" * 42, "a" * 44, "a" * 42 + "+", "a" * 43 + "\n", "ñ" * 43):
        assert not is_login_binding(bad)


def test_RN_IDA_02_pkce_challenge_matches_rfc_7636_appendix_b() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_RN_IDA_02_code_verifier_fits_rfc_7636() -> None:
    verifier = generate_code_verifier()
    assert URL_SECRET.fullmatch(verifier)  # 43 is the RFC minimum; the column holds up to 128.
    assert generate_code_verifier() != verifier
