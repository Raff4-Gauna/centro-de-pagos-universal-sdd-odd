"""Google's side of the login: authorization URL and code exchange (RN-IDA-01, RN-IDA-02, §12).

The only real identity provider (RN-IDA-01). Code flow with PKCE S256 and ``client_secret_post``
(ADR-0004). The exchange has the timeouts of design.md sec. 8.2 and is never retried: the code is
single use. Every failure ends in one of two errors (design.md sec. 4.2, step 4):

* ``GoogleUnavailableError`` (``google_unavailable``): no answer, too slow, 5xx or 429. Recoverable.
* ``GoogleAuthFailedError`` (``google_auth_failed``): Google answered and refused, or answered
  something unusable.

Neither carries the code, the verifier, the response body nor the client secret, and the logs only
say what happened and the status code (C-06, RNF-IDA-03). The endpoints are configurable so the
fake provider of local/test can stand in (Q-122); staging and production pin Google's (T-IDA-20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from urllib.parse import urlencode

import httpx

from apps.common.logging import get_logger
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.secrets_format import code_challenge_s256

GOOGLE_AUTHORIZATION_ENDPOINT: Final = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL
GOOGLE_JWKS_URI: Final = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS: Final = frozenset({"https://accounts.google.com", "accounts.google.com"})
SCOPE: Final = "openid email profile"
# design.md sec. 8.2: connect 3 s / read 5 s. Write and pool are bounded too, so no step of the
# exchange can wait without limit.
TOKEN_ENDPOINT_TIMEOUT: Final = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)

logger = get_logger(__name__)


class GoogleUnavailableError(IdentityError):
    def __init__(self) -> None:
        super().__init__(IdentityErrorCode.GOOGLE_UNAVAILABLE)


class GoogleAuthFailedError(IdentityError):
    def __init__(self) -> None:
        super().__init__(IdentityErrorCode.GOOGLE_AUTH_FAILED)


@dataclass(frozen=True, slots=True)
class GoogleOidcConfig:
    """What the Hub registered with Google. ``client_secret`` stays out of ``repr`` (C-06)."""

    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    authorization_endpoint: str = GOOGLE_AUTHORIZATION_ENDPOINT
    token_endpoint: str = GOOGLE_TOKEN_ENDPOINT
    jwks_uri: str = GOOGLE_JWKS_URI
    issuers: frozenset[str] = GOOGLE_ISSUERS


class GoogleGateway:
    """``transport`` is for tests only (``httpx.MockTransport``): Google is never called in CI."""

    def __init__(
        self, config: GoogleOidcConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._config = config
        self._transport = transport

    def build_authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        """Where the browser goes to log in. Only the S256 challenge leaves; the verifier stays."""
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge_s256(code_verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{self._config.authorization_endpoint}?{urlencode(params)}"

    def exchange_code(self, *, code: str, code_verifier: str) -> str:
        """The ID token Google returns for ``code``, unverified: ``id_token.py`` verifies it."""
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "redirect_uri": self._config.redirect_uri,
        }
        try:
            with httpx.Client(
                timeout=TOKEN_ENDPOINT_TIMEOUT, transport=self._transport, follow_redirects=False
            ) as client:
                response = client.post(
                    self._config.token_endpoint, data=form, headers={"Accept": "application/json"}
                )
        except httpx.TimeoutException:
            logger.warning("identity.google.token_exchange_failed", outcome="timeout")
            raise GoogleUnavailableError from None
        except httpx.HTTPError:
            # Only the class: the message of a transport error may echo the request.
            logger.warning("identity.google.token_exchange_failed", outcome="transport_error")
            raise GoogleUnavailableError from None
        return _id_token_of(response)


def _id_token_of(response: httpx.Response) -> str:
    status = response.status_code
    if status == httpx.codes.TOO_MANY_REQUESTS or status >= httpx.codes.INTERNAL_SERVER_ERROR:
        logger.warning(
            "identity.google.token_exchange_failed", outcome="unavailable", status=status
        )
        raise GoogleUnavailableError
    if status != httpx.codes.OK:
        # 400 invalid_grant (code used, expired or not ours) and every other refusal.
        logger.warning("identity.google.token_exchange_failed", outcome="refused", status=status)
        raise GoogleAuthFailedError
    try:
        id_token = response.json().get("id_token")
    except (ValueError, AttributeError):
        id_token = None
    if not isinstance(id_token, str) or not id_token:
        logger.warning(
            "identity.google.token_exchange_failed", outcome="no_id_token", status=status
        )
        raise GoogleAuthFailedError
    return id_token
