"""Verification of Google's ID token (RN-IDA-02, RNF-IDA-01, AC-IDA-07, AC-IDA-08, AC-IDA-36).

Accepted only if: RS256 and nothing else, signed by a key of Google's JWKS, ``iss`` is Google,
``aud`` is the Hub's client ID (a string, exactly), ``exp``/``iat`` within 60 s of tolerance
(Q-104), it has a ``sub``, and its ``nonce`` hashes to the one stored with the login attempt. Any
failure is ``google_auth_failed``; JWKS out of reach is ``google_unavailable``. Never accepted
unverified.

The JWKS lives in memory for an hour (``PyJWKClient``): verifying needs the network only when the
cache is empty or expired, or once for an unknown ``kid`` (a rotation), at most every
``JWKS_REFRESH_COOLDOWN_SECONDS``. One verifier per process keeps that cache; the caller holds it.
What this returns is still to be judged: ``email_verified`` and the access rules are T-IDA-11's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, NoReturn

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    PyJWKClientConnectionError,
    PyJWKClientError,
    PyJWKSetError,
    PyJWTError,
)

from apps.common.logging import get_logger
from apps.identity.domain.secrets_format import matches_hash
from apps.identity.oidc.google_gateway import (
    GoogleAuthFailedError,
    GoogleOidcConfig,
    GoogleUnavailableError,
)

ALGORITHMS: Final = ["RS256"]
CLOCK_SKEW_SECONDS: Final = 60
REQUIRED_CLAIMS: Final = ["iss", "aud", "exp", "iat", "sub", "nonce"]
JWKS_LIFESPAN_SECONDS: Final = 3600
JWKS_TIMEOUT_SECONDS: Final = 5
JWKS_REFRESH_COOLDOWN_SECONDS: Final = 30

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """The verified claims the Hub uses (RNF-IDA-05). Raw: normalizing them is not this layer's.

    ``email_verified`` is kept as Google sent it (``True`` or ``"true"``; RN-IDA-03 judges it).
    """

    sub: str
    email: str
    email_verified: object
    name: str
    picture: str


def jwks_client_for(config: GoogleOidcConfig) -> PyJWKClient:
    return PyJWKClient(
        config.jwks_uri,
        lifespan=JWKS_LIFESPAN_SECONDS,
        timeout=JWKS_TIMEOUT_SECONDS,
        cooldown_duration=JWKS_REFRESH_COOLDOWN_SECONDS,
    )


class IdTokenVerifier:
    def __init__(self, config: GoogleOidcConfig, *, jwks_client: PyJWKClient | None = None) -> None:
        self._config = config
        self._jwks = jwks_client or jwks_client_for(config)

    def verify(self, id_token: str, *, expected_nonce_hash: str) -> GoogleIdentity:
        key = self._signing_key(id_token)
        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=ALGORITHMS,
                audience=self._config.client_id,
                issuer=sorted(self._config.issuers),
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": REQUIRED_CLAIMS, "strict_aud": True},
            )
        except PyJWTError as error:
            # The class says what failed (signature, aud, iss, exp, a key of another type); its
            # message is not logged.
            _rejected(type(error).__name__)
        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not matches_hash(nonce, expected_nonce_hash):
            _rejected("nonce_mismatch")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            _rejected("sub_missing")
        return GoogleIdentity(
            sub=sub,
            email=_text(claims, "email"),
            email_verified=claims.get("email_verified"),
            name=_text(claims, "name"),
            picture=_text(claims, "picture"),
        )

    def _signing_key(self, id_token: str) -> Any:
        """By ``kid`` from Google's JWKS. The header is unverified: it never picks the algorithm."""
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
        except PyJWTError:
            _rejected("malformed")
        if not isinstance(kid, str) or not kid:
            _rejected("kid_missing")
        try:
            # First the key set alone (from the cache if it is fresh): if Google cannot give one,
            # whatever the error, it is Google's side and recoverable (AC-IDA-36).
            self._jwks.get_signing_keys()
        except (PyJWKClientError, PyJWKSetError, ValueError):
            _jwks_unavailable()
        try:
            return self._jwks.get_signing_key(kid).key
        except (PyJWKClientConnectionError, PyJWKSetError, ValueError):
            # The refresh for an unknown kid could not reach Google. ValueError: not JSON.
            _jwks_unavailable()
        except PyJWKClientError:
            # The kid is not Google's, even after the refresh PyJWKClient allows (RNF-IDA-01).
            _rejected("kid_unknown")


def _jwks_unavailable() -> NoReturn:
    logger.warning("identity.google.jwks_unavailable")
    raise GoogleUnavailableError from None


def _rejected(reason: str) -> NoReturn:
    logger.info("identity.google.id_token_rejected", reason=reason)
    raise GoogleAuthFailedError from None


def _text(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    return value if isinstance(value, str) else ""
