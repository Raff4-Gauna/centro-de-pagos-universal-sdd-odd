"""AC-IDA-07, AC-IDA-08 (``nonce``) and AC-IDA-36 at the ID token (RN-IDA-02, RNF-IDA-01).

No network: ``FakeGoogle`` signs the tokens and serves its JWKS through the urllib opener that
``PyJWKClient`` builds, so PyJWT's own fetch, cache and cooldown are what runs.
"""

from __future__ import annotations

import logging
import time
import types
import urllib.error
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.secrets_format import generate_nonce, hash_secret
from apps.identity.oidc.google_gateway import GoogleAuthFailedError, GoogleUnavailableError
from apps.identity.oidc.id_token import (
    JWKS_REFRESH_COOLDOWN_SECONDS,
    JWKS_TIMEOUT_SECONDS,
    GoogleIdentity,
    IdTokenVerifier,
)
from tests.fakes.google import CLIENT_ID, OTHER_CLIENT_ID, SUB, FakeGoogle, config, rsa_key

NONCE = generate_nonce()
NONCE_HASH = hash_secret(NONCE)
# Past the 60 s of tolerance, with room for a slow run.
EXPIRED_AGO = 65


class Clock:
    """``time.monotonic`` as PyJWKClient's cooldown sees it, moved by hand."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    fake = FakeGoogle()
    fake.install_jwks(monkeypatch)
    return fake


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake_clock = Clock()
    monkeypatch.setattr(
        jwt.jwks_client, "time", types.SimpleNamespace(monotonic=fake_clock.monotonic)
    )
    return fake_clock


@pytest.fixture
def verifier(google: FakeGoogle) -> IdTokenVerifier:
    return IdTokenVerifier(config())


def verify(verifier: IdTokenVerifier, token: str) -> GoogleIdentity:
    return verifier.verify(token, expected_nonce_hash=NONCE_HASH)


def assert_auth_failed(verifier: IdTokenVerifier, token: str) -> None:
    with pytest.raises(GoogleAuthFailedError) as raised:
        verify(verifier, token)
    assert raised.value.code is IdentityErrorCode.GOOGLE_AUTH_FAILED


def test_RN_IDA_02_valid_token_returns_the_identity(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    identity = verify(verifier, google.id_token(nonce=NONCE))
    assert identity == GoogleIdentity(
        sub=SUB,
        email="ana@example.com",
        email_verified=True,
        name="Ana",
        picture="https://lh3.googleusercontent.com/a/ana",
    )


def test_RN_IDA_02_both_google_issuers_are_accepted(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    assert verify(verifier, google.id_token(nonce=NONCE, iss="accounts.google.com")).sub == SUB


def test_RN_IDA_03_email_verified_is_returned_as_sent(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    """Judging it is T-IDA-11's (``True`` or ``"true"``): here it is only carried."""
    token = google.id_token(nonce=NONCE, email_verified="true", name=None, picture=7)
    identity = verify(verifier, token)
    assert identity.email_verified == "true"
    assert (identity.name, identity.picture) == ("", "")


def test_AC_IDA_07_bad_signature(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    assert_auth_failed(verifier, google.id_token(nonce=NONCE, key=rsa_key(99)))


def test_AC_IDA_07_tampered_payload(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    header, _, signature = google.id_token(nonce=NONCE).split(".")
    _, payload, _ = google.id_token(nonce=NONCE, sub="someone-else").split(".")
    assert_auth_failed(verifier, f"{header}.{payload}.{signature}")


def test_AC_IDA_07_foreign_aud(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    assert_auth_failed(verifier, google.id_token(nonce=NONCE, aud=OTHER_CLIENT_ID))


def test_AC_IDA_07_aud_list_is_rejected(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    """Google's ``aud`` is one string: a list holding ours as well is not ours alone."""
    assert_auth_failed(verifier, google.id_token(nonce=NONCE, aud=[CLIENT_ID, OTHER_CLIENT_ID]))


def test_AC_IDA_07_foreign_iss(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    for issuer in ("https://evil.example.com", "https://accounts.google.com.evil.example"):
        assert_auth_failed(verifier, google.id_token(nonce=NONCE, iss=issuer))


def test_AC_IDA_07_expired(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    now = int(time.time())
    token = google.id_token(nonce=NONCE, iat=now - 3600, exp=now - EXPIRED_AGO)
    assert_auth_failed(verifier, token)


def test_AC_IDA_07_expired_within_the_60s_tolerance_is_accepted(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    now = int(time.time())
    token = google.id_token(nonce=NONCE, iat=now - 3600, exp=now - 30)
    assert verify(verifier, token).sub == SUB


def test_AC_IDA_07_issued_in_the_future_is_rejected(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    now = int(time.time())
    assert_auth_failed(verifier, google.id_token(nonce=NONCE, iat=now + 120, exp=now + 3600))


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "iat", "sub", "nonce"])
def test_AC_IDA_07_missing_claim_is_rejected(
    google: FakeGoogle, verifier: IdTokenVerifier, claim: str
) -> None:
    claims = google.claims(nonce=NONCE)
    del claims[claim]
    token = jwt.encode(claims, rsa_key(0), algorithm="RS256", headers={"kid": google.kid})
    assert_auth_failed(verifier, token)


def test_AC_IDA_07_empty_sub_is_rejected(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    assert_auth_failed(verifier, google.id_token(nonce=NONCE, sub=""))


def test_AC_IDA_07_other_algorithms_are_rejected(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    """Only RS256: not ``none``, not HS256 keyed with anything, not another key type."""
    claims = google.claims(nonce=NONCE)
    headers = {"kid": google.kid}
    unsigned = jwt.encode(claims, "", algorithm="none", headers=headers)
    hs256 = jwt.encode(claims, "x" * 32, algorithm="HS256", headers=headers)
    es256 = jwt.encode(
        claims, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers=headers
    )
    ps256 = jwt.encode(claims, rsa_key(0), algorithm="PS256", headers=headers)
    for token in (unsigned, hs256, es256, ps256):
        assert_auth_failed(verifier, token)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_AC_IDA_07_malformed_token_is_rejected(verifier: IdTokenVerifier, token: str) -> None:
    assert_auth_failed(verifier, token)


def test_AC_IDA_07_token_without_kid_is_rejected(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    token = jwt.encode(google.claims(nonce=NONCE), rsa_key(0), algorithm="RS256")
    assert_auth_failed(verifier, token)


def test_AC_IDA_08_nonce_mismatch(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    assert_auth_failed(verifier, google.id_token(nonce=generate_nonce()))


@pytest.mark.parametrize("nonce", ["", 42, None])
def test_AC_IDA_08_nonce_of_the_wrong_shape(
    google: FakeGoogle, verifier: IdTokenVerifier, nonce: Any
) -> None:
    assert_auth_failed(verifier, google.id_token(nonce=nonce))


def test_AC_IDA_08_the_hash_is_compared_not_the_text(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    """The attempt stores only ``nonce#`` (design.md sec. 5): the nonce itself is not a match."""
    with pytest.raises(GoogleAuthFailedError):
        verifier.verify(google.id_token(nonce=NONCE), expected_nonce_hash=NONCE)


def test_RNF_IDA_01_jwks_is_cached(google: FakeGoogle, verifier: IdTokenVerifier) -> None:
    for _ in range(3):
        verify(verifier, google.id_token(nonce=NONCE))
    assert google.jwks_fetches == [JWKS_TIMEOUT_SECONDS]


def test_RNF_IDA_01_unknown_kid_refreshes_once(
    google: FakeGoogle, verifier: IdTokenVerifier, clock: Clock
) -> None:
    verify(verifier, google.id_token(nonce=NONCE))
    google.rotate_key()
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    assert verify(verifier, google.id_token(nonce=NONCE)).sub == SUB
    assert len(google.jwks_fetches) == 2


def test_RNF_IDA_01_unknown_kid_within_the_cooldown_does_not_refetch(
    google: FakeGoogle, verifier: IdTokenVerifier, clock: Clock
) -> None:
    """A stream of forged ``kid`` values cannot turn every login into a fetch from Google."""
    verify(verifier, google.id_token(nonce=NONCE))
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    for index in range(3):
        assert_auth_failed(verifier, google.id_token(nonce=NONCE, kid=f"forged-{index}"))
    assert len(google.jwks_fetches) == 2


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("slow"), urllib.error.URLError("down"), 500, 503, 429],
    ids=["timeout", "unreachable", "500", "5xx", "429"],
)
def test_AC_IDA_36_jwks_down_is_unavailable(
    google: FakeGoogle, verifier: IdTokenVerifier, failure: int | Exception
) -> None:
    """Without keys in cache, a token is never accepted unverified: it is ``google_unavailable``."""
    google.fail_jwks(failure)
    with pytest.raises(GoogleUnavailableError) as raised:
        verify(verifier, google.id_token(nonce=NONCE))
    assert raised.value.code is IdentityErrorCode.GOOGLE_UNAVAILABLE


def test_AC_IDA_36_jwks_that_is_not_json_is_unavailable(
    google: FakeGoogle, verifier: IdTokenVerifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(google, "jwks", lambda: "not a key set")
    with pytest.raises(GoogleUnavailableError):
        verify(verifier, google.id_token(nonce=NONCE))


def test_AC_IDA_36_cached_keys_survive_google_going_down(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    verify(verifier, google.id_token(nonce=NONCE))
    google.fail_jwks(503, 503)
    assert verify(verifier, google.id_token(nonce=NONCE)).sub == SUB


def test_AC_IDA_36_jwks_down_during_a_rotation_is_unavailable(
    google: FakeGoogle, verifier: IdTokenVerifier, clock: Clock
) -> None:
    """The cached keys do not hold the new ``kid`` and the refresh fails: never accepted."""
    verify(verifier, google.id_token(nonce=NONCE))
    google.rotate_key()
    google.fail_jwks(503)
    clock.now += JWKS_REFRESH_COOLDOWN_SECONDS + 1
    with pytest.raises(GoogleUnavailableError):
        verify(verifier, google.id_token(nonce=NONCE))


def test_AC_IDA_36_next_login_recovers_once_google_is_back(
    google: FakeGoogle, verifier: IdTokenVerifier
) -> None:
    google.fail_jwks(TimeoutError("slow"))
    with pytest.raises(GoogleUnavailableError):
        verify(verifier, google.id_token(nonce=NONCE))
    assert verify(verifier, google.id_token(nonce=NONCE)).sub == SUB


def test_RNF_IDA_03_rejection_leaks_no_token_nor_nonce(
    google: FakeGoogle, verifier: IdTokenVerifier, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    token = google.id_token(nonce=generate_nonce())
    with pytest.raises(GoogleAuthFailedError) as raised:
        verify(verifier, token)
    error = raised.value
    for text in (str(error), repr(error), caplog.text):
        assert token not in text
        assert token.split(".")[1] not in text
        assert NONCE not in text
    assert error.__suppress_context__ or error.__context__ is None
