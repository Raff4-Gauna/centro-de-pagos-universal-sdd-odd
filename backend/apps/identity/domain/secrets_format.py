"""Shape of the secrets of a session and of a login attempt (design.md §4.5, §5; ADR-0004 §1).

Stdlib only. Refresh token: ``rt1.<sid>.<secret>``, base64url without padding of the 16 bytes of the
session id and of 32 random bytes. ``state``, ``nonce``, binding and PKCE verifier also carry 32
bytes (43 characters), so plain SHA-256 is enough: there is nothing to guess (design.md §5).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from uuid import UUID

from apps.identity.domain.errors import MalformedRefreshTokenError

SECRET_BYTES = 32

_REFRESH_TOKEN = re.compile(r"rt1\.([A-Za-z0-9_-]{22})\.([A-Za-z0-9_-]{43})")
_LOGIN_BINDING = re.compile(r"[A-Za-z0-9_-]{43}")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _random_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def generate_refresh_token(session_id: UUID) -> str:
    return f"rt1.{_encode(session_id.bytes)}.{_random_secret()}"


def parse_refresh_token(raw: str) -> UUID:
    """The session id of ``raw``, without proving it is genuine: only its hash does that.

    The re-encoding refuses base64 with spare bits set, which decodes to the same bytes.
    """
    match = _REFRESH_TOKEN.fullmatch(raw)
    if match is None:
        raise MalformedRefreshTokenError
    sid, secret = (_decode(text) for text in match.groups())
    if _encode(sid) != match[1] or _encode(secret) != match[2]:
        raise MalformedRefreshTokenError
    return UUID(bytes=sid)


def hash_secret(value: str) -> str:
    """SHA-256 hex. ``surrogatepass``: a lone surrogate from JSON must hash, not raise."""
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def matches_hash(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), expected_hash)


def generate_state() -> str:
    return _random_secret()


def generate_nonce() -> str:
    return _random_secret()


def is_login_binding(value: str) -> bool:
    """The BFF creates the binding (design.md §6.3); Django only checks its shape and hashes it."""
    return _LOGIN_BINDING.fullmatch(value) is not None


def generate_code_verifier() -> str:
    return _random_secret()


def code_challenge_s256(verifier: str) -> str:
    return _encode(hashlib.sha256(verifier.encode("ascii")).digest())
