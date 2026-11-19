"""Pure invitation rules (``domain/invitations.py``): AC-TEN-25, AC-TEN-35 (unit), RNF-TEN-03.

No database: the clock is injected, so the expiry edge is exact to the microsecond.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.identity.domain import emails as identity_emails
from apps.tenancy.domain import invitations
from apps.tenancy.domain.invitations import (
    INVITATION_TTL,
    emails_match,
    expires_at_for,
    hash_token,
    is_expired,
    new_token,
    normalize_email,
)

ISSUED = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

# --- AC-TEN-25: valid while now < issued + 7 days -----------------------------------------------


def test_AC_TEN_25_ttl_is_seven_days() -> None:
    assert timedelta(days=7) == INVITATION_TTL
    assert expires_at_for(ISSUED) == datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("elapsed", "expired"),
    [
        pytest.param(timedelta(0), False, id="at-issue"),
        pytest.param(timedelta(days=7) - timedelta(minutes=1), False, id="7d-minus-1min"),
        pytest.param(timedelta(days=7) - timedelta(microseconds=1), False, id="7d-minus-1us"),
        pytest.param(timedelta(days=7), True, id="exactly-7d"),
        pytest.param(timedelta(days=7, minutes=1), True, id="after-7d"),
    ],
)
def test_AC_TEN_25_expiry_edge_with_injected_clock(elapsed: timedelta, expired: bool) -> None:
    assert is_expired(expires_at_for(ISSUED), now=ISSUED + elapsed) is expired


def test_AC_TEN_25_expiry_compares_instants_not_wall_clocks() -> None:
    buenos_aires = timezone(timedelta(hours=-3))
    edge = expires_at_for(ISSUED).astimezone(buenos_aires)

    assert is_expired(expires_at_for(ISSUED), now=edge) is True
    assert is_expired(expires_at_for(ISSUED), now=edge - timedelta(minutes=1)) is False


NAIVE = datetime(2026, 11, 19, 12, 0)  # noqa: DTZ001 - the point of the tests below


def test_AC_TEN_25_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="issued_at"):
        expires_at_for(NAIVE)
    with pytest.raises(ValueError, match="expires_at"):
        is_expired(NAIVE, now=ISSUED)
    with pytest.raises(ValueError, match="now"):
        is_expired(expires_at_for(ISSUED), now=NAIVE)


# --- AC-TEN-35: same address after trim + lowercase, nothing more -------------------------------

# Shared with identity's normalizer (RN-IDA-05, Q-107): both must agree on every row.
NORMALIZATION_CASES = [
    (" X@Dominio.com ", "x@dominio.com"),
    ("x@dominio.com", "x@dominio.com"),
    ("ANA@X.COM", "ana@x.com"),
    ("\tana@x.com\n", "ana@x.com"),
    ("ana.b@x.com", "ana.b@x.com"),
    ("Ana+1@X.com", "ana+1@x.com"),
    ("a n@x.com", "a n@x.com"),
    ("", ""),
]


@pytest.mark.parametrize(("raw", "expected"), NORMALIZATION_CASES)
def test_AC_TEN_35_normalization(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(("raw", "_expected"), NORMALIZATION_CASES)
def test_AC_TEN_35_normalization_agrees_with_identity(raw: str, _expected: str) -> None:
    assert normalize_email(raw) == identity_emails.normalize_email(raw)


@pytest.mark.parametrize(
    ("user_email", "matches"),
    [
        pytest.param("x@dominio.com", True, id="same-address"),
        pytest.param("X@DOMINIO.COM ", True, id="case-and-spaces"),
        pytest.param("x+1@dominio.com", False, id="plus-alias"),
        pytest.param("x.@dominio.com", False, id="extra-dot"),
        pytest.param("x@otro.com", False, id="other-domain"),
    ],
)
def test_AC_TEN_35_emails_match(user_email: str, matches: bool) -> None:
    assert emails_match(" X@Dominio.com ", user_email) is matches


def test_AC_TEN_35_domain_does_not_import_identity() -> None:
    text = Path(invitations.__file__).read_text(encoding="utf-8")

    assert "apps.identity" not in text
    assert not re.search(r"^\s*(from|import)\s+django", text, re.MULTILINE)


# --- RNF-TEN-03: 256-bit token, stored only as its SHA-256 ---------------------------------------


def test_RNF_TEN_03_token_has_256_bits_and_is_url_safe() -> None:
    token = new_token()

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)  # 32 bytes in base64url, no padding
    assert len({new_token() for _ in range(50)}) == 50


def test_RNF_TEN_03_hash_is_sha256_hex() -> None:
    token = new_token()

    assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token(token))
    assert token not in hash_token(token)


def test_RNF_TEN_03_empty_token_has_no_hash() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_token("")
