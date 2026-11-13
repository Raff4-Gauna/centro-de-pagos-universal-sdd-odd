"""``domain/login_rules.py``: what the callback accepts from Google's claims (design.md §4.2, 5-6).

Pure, no database. An unusable ``sub`` or email rejects the login as ``google_auth_failed`` (the
token is not one the Hub can use); an unusable name or avatar never does (spec §12): it is stored
cleaned, cut or empty.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.login_rules import LoginRejectedError, evaluate_identity
from apps.identity.domain.profile import MAX_DISPLAY_NAME


def claims(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "sub": "1234567890",
        "email": " Ana@X.com ",
        "email_verified": True,
        "name": "Ana",
        "picture": "https://lh3.example.com/a.png",
    }
    return {**values, **overrides}


def rejection_of(**overrides: Any) -> LoginRejectedError:
    with pytest.raises(LoginRejectedError) as raised:
        evaluate_identity(**claims(**overrides))
    return raised.value


@pytest.mark.parametrize("verified", [True, "true"])
def test_RN_IDA_03_verified_email_is_accepted(verified: object) -> None:
    identity = evaluate_identity(**claims(email_verified=verified))
    assert identity.sub == "1234567890"
    assert identity.email == "ana@x.com"
    assert identity.display_name == "Ana"
    assert identity.avatar_url == "https://lh3.example.com/a.png"


@pytest.mark.parametrize("verified", [False, "false", "True", "TRUE", 1, "1", None, ""])
def test_RN_IDA_03_anything_else_is_email_not_verified(verified: object) -> None:
    rejection = rejection_of(email_verified=verified)
    assert rejection.code == IdentityErrorCode.EMAIL_NOT_VERIFIED
    assert rejection.user_id is None
    assert isinstance(rejection, IdentityError)


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        "ana@x.com\x00",
        "ana\t@x.com",
        "ana\u00a0@x.com",
        "ana\u3000@x.com",
        "ana@x\u200b.com",
        "ana@x.com\x7f",
        "ana@x\ud800.com",
        "a" * 250 + "@x.com",
    ],
)
def test_RF_IDA_02_unusable_email_is_google_auth_failed(email: str) -> None:
    # The database CHECK only trims spaces (reviewer of #65): the rest is refused here.
    rejection = rejection_of(email=email)
    assert rejection.code == IdentityErrorCode.GOOGLE_AUTH_FAILED


def test_RF_IDA_02_unusable_email_wins_over_unverified() -> None:
    # Step 5 (the token) comes before step 6 (email_verified) in design.md §4.2.
    assert rejection_of(email="", email_verified=False).code == IdentityErrorCode.GOOGLE_AUTH_FAILED


@pytest.mark.parametrize("sub", ["", " ", "12 34", "12\x0034", "1" * 256])
def test_RN_IDA_04_unusable_sub_is_google_auth_failed(sub: str) -> None:
    assert rejection_of(sub=sub).code == IdentityErrorCode.GOOGLE_AUTH_FAILED


def test_RN_IDA_21_surrounding_whitespace_of_any_kind_is_trimmed() -> None:
    identity = evaluate_identity(**claims(email="\u3000\tAna@X.com\u00a0\n"))
    assert identity.email == "ana@x.com"


def test_RN_IDA_21_name_without_nul_and_clamped() -> None:
    raw = "A\x00na" + "x" * MAX_DISPLAY_NAME
    identity = evaluate_identity(**claims(name=raw))
    assert "\x00" not in identity.display_name
    assert identity.display_name.startswith("Ana")
    assert len(identity.display_name) == MAX_DISPLAY_NAME


def test_RN_IDA_21_name_without_lone_surrogates() -> None:
    assert evaluate_identity(**claims(name="An\ud800a")).display_name == "Ana"


@pytest.mark.parametrize(
    "picture",
    [
        "https://lh3.example.com/a\x00.png",
        "https://lh3.example.com/a\ud800.png",
        "http://lh3.example.com/a.png",
        "",
    ],
)
def test_RN_IDA_21_unusable_avatar_is_empty(picture: str) -> None:
    assert evaluate_identity(**claims(picture=picture)).avatar_url == ""


def test_RN_IDA_21_missing_name_and_avatar_never_reject() -> None:
    identity = evaluate_identity(**claims(name="", picture=""))
    assert (identity.display_name, identity.avatar_url) == ("", "")


def test_RNF_IDA_05_rejection_carries_neither_email_nor_sub() -> None:
    rejection = rejection_of(email_verified=False)
    assert "ana" not in repr(rejection).lower()
    assert "1234567890" not in repr(rejection)
    assert str(rejection) == "email_not_verified"


def test_RNF_IDA_05_identity_repr_has_neither_email_nor_sub() -> None:
    text = repr(evaluate_identity(**claims()))
    assert "ana@x.com" not in text
    assert "1234567890" not in text
