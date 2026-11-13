"""The Hub's access JWT: issuing and verifying it (RN-IDA-08, RN-IDA-09, ADR-0004 sec. 5).

Local and without I/O (RNF-IDA-01). Whether the session is still alive is not read from the token:
``HubJWTAuthentication`` checks that on every request (RN-IDA-20). The errors carry only their code,
never a part of the token (C-06).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from django.conf import settings
from django.utils import timezone
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.session_policy import ACCESS_TOKEN_LIFETIME
from apps.identity.tokens.keys import active_signing_key, verification_key

ALGORITHMS = ["ES256"]
TOKEN_TYPE = "at+jwt"  # noqa: S105 - the JOSE `typ`, not a credential
# The 15 minutes and the error codes live in the domain (RN-IDA-11, spec §11): one source each.
ACCESS_TOKEN_TTL_SECONDS = int(ACCESS_TOKEN_LIFETIME.total_seconds())
CLOCK_SKEW_SECONDS = 60
REQUIRED_CLAIMS = ["exp", "iat", "nbf", "iss", "aud", "sub", "sid"]


class AccessTokenError(Exception):
    code: ClassVar[IdentityErrorCode]


class AccessTokenExpiredError(AccessTokenError):
    """Expired past the tolerance, and nothing else is wrong with it."""

    code = IdentityErrorCode.TOKEN_EXPIRED


class AccessTokenInvalidError(AccessTokenError):
    code = IdentityErrorCode.TOKEN_INVALID


@dataclass(frozen=True, slots=True)
class AccessTokenIdentity:
    user_id: UUID
    session_id: UUID


def issue_access_token(*, user_id: UUID, session_id: UUID, now: datetime | None = None) -> str:
    """Identity and validity only: no role, organization or permission travels here (RN-IDA-09)."""
    signing = active_signing_key()
    issued_at = int((now or timezone.now()).timestamp())
    claims = {
        "iss": settings.IDENTITY_JWT_ISSUER,
        "aud": settings.IDENTITY_JWT_AUDIENCE,
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL_SECONDS,
    }
    headers = {"kid": signing.kid, "typ": TOKEN_TYPE}
    return jwt.encode(claims, signing.key, algorithm=ALGORITHMS[0], headers=headers)


def verify_access_token(token: str) -> AccessTokenIdentity:
    """The identity in ``token``, or ``AccessTokenExpiredError`` / ``AccessTokenInvalidError``.

    ``token_expired`` means "only expired" (RN-IDA-08), and PyJWT reports ``exp`` before ``aud`` and
    ``iss``: an expired token goes through every other check again before it is called expired.
    """
    try:
        key = _key_of(token)
        try:
            return _identity(_decode(token, key, verify_exp=True))
        except ExpiredSignatureError:
            _identity(_decode(token, key, verify_exp=False))
    except (InvalidTokenError, ValueError):
        raise AccessTokenInvalidError from None
    raise AccessTokenExpiredError


def verify_access_token_ignoring_expiry(token: str) -> AccessTokenIdentity:
    """The identity in ``token`` however long ago it expired, for logout only (RN-IDA-14).

    Every check of ``verify_access_token`` but ``exp``: key by ``kid``, algorithm, signature,
    ``iss``, ``aud``, ``typ``, ``nbf`` and the claims. It proves the caller held a token of the
    session, not that the session is alive, so it never authenticates a request. Anything wrong is
    ``AccessTokenInvalidError``.
    """
    try:
        return _identity(_decode(token, _key_of(token), verify_exp=False))
    except (InvalidTokenError, ValueError):
        raise AccessTokenInvalidError from None


def _key_of(token: str) -> EllipticCurvePublicKey:
    """By ``kid`` only: the header is unverified, so it never chooses the algorithm."""
    key = verification_key(jwt.get_unverified_header(token).get("kid", ""))
    if key is None:
        raise InvalidTokenError
    return key


def _decode(token: str, key: EllipticCurvePublicKey, *, verify_exp: bool) -> dict[str, Any]:
    decoded = jwt.decode_complete(
        token,
        key,
        algorithms=ALGORITHMS,
        issuer=settings.IDENTITY_JWT_ISSUER,
        audience=settings.IDENTITY_JWT_AUDIENCE,
        leeway=CLOCK_SKEW_SECONDS,
        options={"require": REQUIRED_CLAIMS, "strict_aud": True, "verify_exp": verify_exp},
    )
    if decoded["header"].get("typ") != TOKEN_TYPE:
        raise InvalidTokenError
    payload: dict[str, Any] = decoded["payload"]
    return payload


def _identity(claims: dict[str, Any]) -> AccessTokenIdentity:
    return AccessTokenIdentity(
        user_id=UUID(str(claims["sub"])), session_id=UUID(str(claims["sid"]))
    )
