"""AC-IDA-10..13 and 34 at token level (RN-IDA-08, RN-IDA-09, RNF-IDA-01): no database, no network.

``config.settings.test`` generates the key pair of each run. Hostile tokens are built here, with
PyJWT where it allows them and by hand where it refuses to (``alg=none``, HS256 keyed with the
public key), so what is under test is the verifier and not the encoder's own checks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

from apps.identity.tokens.access_token import (
    AccessTokenExpiredError,
    AccessTokenInvalidError,
    issue_access_token,
    verify_access_token,
)

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
SESSION_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
ALL_CLAIMS = ("aud", "exp", "iat", "iss", "nbf", "sid", "sub")
# Past the 60 s of tolerance, with room for a slow run.
EXPIRED_ISSUED_AGO = 900 + 65


def claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": django_settings.IDENTITY_JWT_ISSUER,
        "aud": django_settings.IDENTITY_JWT_AUDIENCE,
        "sub": str(USER_ID),
        "sid": str(SESSION_ID),
        "iat": now,
        "nbf": now,
        "exp": now + 900,
    } | overrides


def expired_claims(**overrides: Any) -> dict[str, Any]:
    issued_at = int(time.time()) - EXPIRED_ISSUED_AGO
    return claims(iat=issued_at, nbf=issued_at, exp=issued_at + 900, **overrides)


def header(**overrides: Any) -> dict[str, Any]:
    kid = django_settings.IDENTITY_JWT_SIGNING_KID
    return {"alg": "ES256", "kid": kid, "typ": "at+jwt"} | overrides


def forge(payload: dict[str, Any] | None = None, key: Any = None, **headers: Any) -> str:
    """A token signed with ``key`` (by default, the Hub's): only what the test changes differs."""
    return jwt.encode(
        claims() if payload is None else payload,
        django_settings.IDENTITY_JWT_SIGNING_KEY if key is None else key,
        algorithm=headers.get("alg", "ES256"),
        headers=header(**headers),
    )


def by_hand(token_header: dict[str, Any], signature: Callable[[bytes], bytes]) -> str:
    def encode(part: bytes) -> bytes:
        return base64.urlsafe_b64encode(part).rstrip(b"=")

    parts = (json.dumps(token_header).encode(), json.dumps(claims()).encode())
    signed = b".".join(encode(part) for part in parts)
    return b".".join((signed, encode(signature(signed)))).decode()


def assert_invalid(token: str) -> None:
    with pytest.raises(AccessTokenInvalidError) as info:
        verify_access_token(token)
    assert info.value.code == "token_invalid"
    assert str(info.value) == ""  # nothing of the token travels in the error (C-06)


def issued_ago(seconds: int) -> str:
    moment = datetime.now(UTC) - timedelta(seconds=seconds)
    return issue_access_token(user_id=USER_ID, session_id=SESSION_ID, now=moment)


def other_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_AC_IDA_10_issued_14_min_ago_is_valid() -> None:
    identity = verify_access_token(issued_ago(14 * 60))
    assert (identity.user_id, identity.session_id) == (USER_ID, SESSION_ID)


def test_AC_IDA_10_expired_over_60s() -> None:
    with pytest.raises(AccessTokenExpiredError) as info:
        verify_access_token(issued_ago(EXPIRED_ISSUED_AGO))
    assert info.value.code == "token_expired"
    assert str(info.value) == ""


@pytest.mark.parametrize(
    "change",
    [{"aud": "other"}, {"iss": "other"}, {"sid": "not-a-uuid"}, {"sub": "not-a-uuid"}],
    ids=["aud", "iss", "sid", "sub"],
)
def test_RN_IDA_08_expired_and_something_else_is_invalid(change: dict[str, str]) -> None:
    # token_expired is only "si solo venció", and PyJWT looks at exp before aud and iss.
    assert_invalid(forge(expired_claims(**change)))


def test_RN_IDA_08_expired_with_a_foreign_type_is_invalid() -> None:
    assert_invalid(forge(expired_claims(), typ="JWT"))


def test_RN_IDA_08_expired_and_signed_by_another_key_is_invalid() -> None:
    assert_invalid(forge(expired_claims(), key=other_key()))


def test_AC_IDA_11_altered_signature_rejected() -> None:
    head, payload, signature = issued_ago(0).split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert_invalid(f"{head}.{payload}.{flipped}")


def test_AC_IDA_11_altered_payload_rejected() -> None:
    head, _, signature = issued_ago(0).split(".")
    _, payload, _ = forge(claims(sub=str(uuid.uuid4()))).split(".")
    assert_invalid(f"{head}.{payload}.{signature}")


def test_AC_IDA_11_signed_with_another_key_rejected() -> None:
    assert_invalid(forge(key=other_key()))


def test_AC_IDA_11_alg_none_and_hs256_rejected() -> None:
    kid = django_settings.IDENTITY_JWT_SIGNING_KID
    public_pem = django_settings.IDENTITY_JWT_VERIFICATION_KEYS[kid]
    # The classic confusion: HS256 keyed with the verifier's public key.
    assert_invalid(
        by_hand(
            header(alg="HS256"),
            lambda signed: hmac.new(public_pem.encode(), signed, hashlib.sha256).digest(),
        )
    )
    assert_invalid(by_hand(header(alg="none"), lambda _: b""))
    assert_invalid(by_hand(header(alg="None"), lambda _: b""))


def test_AC_IDA_11_algorithm_out_of_the_list_rejected() -> None:
    assert_invalid(forge(key=rsa_key(), alg="RS256"))
    assert_invalid(forge(key=ec.generate_private_key(ec.SECP384R1()), alg="ES384"))


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "..", "é.é.é", "e30.e30.e30"])
def test_AC_IDA_11_not_a_token_rejected(token: str) -> None:
    assert_invalid(token)


def test_AC_IDA_12_foreign_iss_aud() -> None:
    assert_invalid(forge(claims(iss="https://other.example")))
    assert_invalid(forge(claims(aud="other-api")))
    # A list that includes the Hub is not "the Hub's aud": issue_access_token writes one string.
    assert_invalid(forge(claims(aud=[django_settings.IDENTITY_JWT_AUDIENCE, "other-api"])))


def test_AC_IDA_12_google_token_rejected() -> None:
    google = claims(iss="https://accounts.google.com", aud="client.apps.example", sub="123")
    assert_invalid(jwt.encode(google, rsa_key(), "RS256", headers={"kid": "google-kid"}))
    # Even if a kid collides with one of the Hub's, the algorithm and the key are not the Hub's.
    kid = django_settings.IDENTITY_JWT_SIGNING_KID
    assert_invalid(jwt.encode(google, rsa_key(), "RS256", headers={"kid": kid}))


def test_RN_IDA_08_unknown_kid_rejected_without_network() -> None:
    # No PyJWKClient here (RNF-IDA-01): an unknown kid is simply not a key of the Hub.
    assert_invalid(forge(kid="retired"))
    assert_invalid(jwt.encode(claims(), django_settings.IDENTITY_JWT_SIGNING_KEY, "ES256"))


@pytest.mark.parametrize("typ", ["JWT", "AT+JWT", "id+jwt"])
def test_RN_IDA_08_other_token_types_rejected(typ: str) -> None:
    assert_invalid(forge(typ=typ))


@pytest.mark.parametrize("claim", ALL_CLAIMS)
def test_RN_IDA_08_every_claim_is_required(claim: str) -> None:
    payload = claims()
    del payload[claim]
    assert_invalid(forge(payload))


@pytest.mark.parametrize(
    "bad",
    [{"sub": "not-a-uuid"}, {"sid": "not-a-uuid"}, {"sid": 123}, {"iat": "x"}, {"nbf": "x"}],
    ids=["sub", "sid", "sid-number", "iat", "nbf"],
)
def test_RN_IDA_08_malformed_claims_with_a_good_signature_rejected(bad: dict[str, Any]) -> None:
    assert_invalid(forge(claims(**bad)))


def test_AC_IDA_13_exact_claims() -> None:
    now = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
    token = issue_access_token(user_id=USER_ID, session_id=SESSION_ID, now=now)

    assert jwt.get_unverified_header(token) == {
        "alg": "ES256",
        "kid": django_settings.IDENTITY_JWT_SIGNING_KID,
        "typ": "at+jwt",
    }
    issued_at = int(now.timestamp())
    assert jwt.decode(token, options={"verify_signature": False}) == {
        "iss": django_settings.IDENTITY_JWT_ISSUER,
        "aud": django_settings.IDENTITY_JWT_AUDIENCE,
        "sub": str(USER_ID),
        "sid": str(SESSION_ID),
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + 15 * 60,
    }


def test_AC_IDA_34_skew_30s_accepted_120s_rejected() -> None:
    now = int(time.time())
    assert verify_access_token(issued_ago(900 + 30)).session_id == SESSION_ID
    for claim in ("iat", "nbf"):
        assert verify_access_token(forge(claims(**{claim: now + 30}))).user_id == USER_ID
        assert_invalid(forge(claims(**{claim: now + 120})))


def test_RN_IDA_08_rotation_keeps_the_previous_key_until_it_is_removed(
    settings: Any,
) -> None:
    old_token = issued_ago(0)
    old_kid = settings.IDENTITY_JWT_SIGNING_KID
    new_key = other_key()
    public_pem = new_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    settings.IDENTITY_JWT_VERIFICATION_KEYS = {
        **settings.IDENTITY_JWT_VERIFICATION_KEYS,
        "next": public_pem.decode(),
    }
    settings.IDENTITY_JWT_SIGNING_KID = "next"
    settings.IDENTITY_JWT_SIGNING_KEY = new_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    new_token = issued_ago(0)
    assert jwt.get_unverified_header(new_token)["kid"] == "next"
    assert verify_access_token(new_token).user_id == USER_ID
    assert verify_access_token(old_token).user_id == USER_ID  # the overlap of design.md §10

    settings.IDENTITY_JWT_VERIFICATION_KEYS = {
        kid: pem for kid, pem in settings.IDENTITY_JWT_VERIFICATION_KEYS.items() if kid != old_kid
    }
    assert_invalid(old_token)


def test_RN_IDA_08_no_verification_keys_fails_closed(settings: Any) -> None:
    token = issued_ago(0)
    settings.IDENTITY_JWT_VERIFICATION_KEYS = {}
    with pytest.raises(ImproperlyConfigured, match="IDENTITY_JWT_VERIFICATION_KEYS"):
        verify_access_token(token)


@pytest.mark.parametrize("setting", ["IDENTITY_JWT_SIGNING_KID", "IDENTITY_JWT_SIGNING_KEY"])
def test_RN_IDA_08_no_signing_key_issues_nothing(settings: Any, setting: str) -> None:
    setattr(settings, setting, "")
    with pytest.raises(ImproperlyConfigured, match="IDENTITY_JWT_SIGNING"):
        issued_ago(0)
