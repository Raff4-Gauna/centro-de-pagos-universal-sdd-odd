"""Error codes of the module (spec §11, design.md §6): a published contract (ADR-0005)."""

from __future__ import annotations

from apps.identity.domain.errors import IdentityError, IdentityErrorCode


def test_error_codes_are_the_published_ones() -> None:
    assert {code.value for code in IdentityErrorCode} == {
        "email_not_verified",
        "google_auth_failed",
        "google_unavailable",
        "identity_conflict",
        "login_cancelled",
        "login_disabled",
        "not_invited",
        "rate_limited",
        "session_revoked",
        "token_expired",
        "token_invalid",
        "unauthenticated",
        "user_inactive",
    }


def test_error_carries_only_its_code() -> None:
    error = IdentityError(IdentityErrorCode.SESSION_REVOKED)
    assert error.code is IdentityErrorCode.SESSION_REVOKED
    assert str(error) == "session_revoked"
