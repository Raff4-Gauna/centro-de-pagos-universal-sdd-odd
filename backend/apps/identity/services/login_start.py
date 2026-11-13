"""Start a login with Google (RF-IDA-01, RN-IDA-02, RN-IDA-13, design.md §4.1).

Creates the attempt and the URL the browser goes to. ``state``, ``nonce`` and the PKCE verifier are
generated here, 32 random bytes each, and tied to this attempt together with the binding the BFF
keeps in its cookie; the table holds their SHA-256, except the verifier (design.md §5). None of them
is logged or returned apart from the URL itself, which is how ``state`` and ``nonce`` reach Google.

Behind ``FEATURE_IDENTITY_GOOGLE_LOGIN`` (RNF-IDA-06): off, nothing is created and nobody is sent
to Google. The gateway is resolved before the insert, so a Hub without its Google client leaves no
row either. The rate limit is the view's (it runs before this, RN-IDA-15).
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from apps.common import feature_flags
from apps.common.logging import get_logger
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.return_path import sanitize_return_path
from apps.identity.domain.secrets_format import (
    generate_code_verifier,
    generate_nonce,
    generate_state,
    hash_secret,
)
from apps.identity.models.login_attempt import LOGIN_ATTEMPT_LIFETIME, LoginAttempt
from apps.identity.oidc.provider import get_google_gateway

LOGIN_FLAG = "IDENTITY_GOOGLE_LOGIN"
LOGIN_STARTED_EVENT = "identity.login_started"

logger = get_logger(__name__)


class LoginDisabledError(IdentityError):
    def __init__(self) -> None:
        super().__init__(IdentityErrorCode.LOGIN_DISABLED)


def start_login(*, return_path: object, login_binding: str, now: datetime | None = None) -> str:
    """The authorization URL of a new attempt; ``login_binding`` already has its shape checked."""
    if not feature_flags.is_enabled(LOGIN_FLAG):
        raise LoginDisabledError
    gateway = get_google_gateway()
    created_at = now or timezone.now()
    state = generate_state()
    nonce = generate_nonce()
    code_verifier = generate_code_verifier()
    LoginAttempt.objects.create(
        state_hash=hash_secret(state),
        nonce_hash=hash_secret(nonce),
        binding_hash=hash_secret(login_binding),
        code_verifier=code_verifier,
        return_path=sanitize_return_path(return_path),
        created_at=created_at,
        expires_at=created_at + LOGIN_ATTEMPT_LIFETIME,
    )
    logger.info(LOGIN_STARTED_EVENT)
    return gateway.build_authorization_url(state=state, nonce=nonce, code_verifier=code_verifier)
