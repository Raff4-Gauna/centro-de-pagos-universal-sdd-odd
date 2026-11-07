"""Error codes of the module (spec §11, design.md §6) and its domain exceptions.

A code is a published contract (ADR-0005). An exception carries its code and nothing else: no
token, ``state``, ``nonce`` or detail of what was rejected (C-06, RNF-IDA-03).
"""

from __future__ import annotations

from enum import StrEnum


class IdentityErrorCode(StrEnum):
    EMAIL_NOT_VERIFIED = "email_not_verified"
    GOOGLE_AUTH_FAILED = "google_auth_failed"
    GOOGLE_UNAVAILABLE = "google_unavailable"
    IDENTITY_CONFLICT = "identity_conflict"
    LOGIN_CANCELLED = "login_cancelled"
    LOGIN_DISABLED = "login_disabled"
    NOT_INVITED = "not_invited"
    RATE_LIMITED = "rate_limited"
    SESSION_REVOKED = "session_revoked"
    TOKEN_EXPIRED = "token_expired"  # noqa: S105 - an error code, not a credential
    TOKEN_INVALID = "token_invalid"  # noqa: S105 - an error code, not a credential
    UNAUTHENTICATED = "unauthenticated"
    USER_INACTIVE = "user_inactive"


class IdentityError(Exception):
    def __init__(self, code: IdentityErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class MalformedRefreshTokenError(IdentityError):
    """The text is not ``rt1.<sid>.<secret>``: rejected without touching the database."""

    def __init__(self) -> None:
        super().__init__(IdentityErrorCode.TOKEN_INVALID)
