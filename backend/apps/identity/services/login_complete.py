"""Complete a login with Google: the callback (RF-IDA-02, RN-IDA-17, design.md §4.1, §4.2).

The steps of design.md §4.2 in their fixed order (the throttle, step 1, is the view's and runs
before this):

2. **Consume the attempt.** One ``DELETE … RETURNING`` by the hashes of ``state`` and of the
   browser's binding, only while it is alive: the row is gone whatever happens next, so a callback
   repeated from the history finds nothing (AC-IDA-08), and of two at once only one gets it. It
   commits on its own, before Google is called: a later rollback does not give the attempt back.
   No attempt → ``google_auth_failed`` and Google is never asked (AC-IDA-08).
3. ``error=access_denied`` → ``login_cancelled``; any other ``error``, or no ``code`` →
   ``google_auth_failed``.
4-5. Code exchange and ID token (``oidc/``), with the attempt's verifier and ``nonce`` hash.
6. ``evaluate_identity`` (``domain/login_rules.py``): ``email_not_verified`` and unusable claims.
7. One ``atomic()``: ``provision_user`` (cases (a) and (b)), the session, the access token and the
   ``login_succeeded`` event, so a failure leaves no user, invitation, session nor success event.
   The session keeps the browser and OS of the User-Agent the BFF relays, summarized
   (``domain/client_hint.py``); the raw User-Agent is neither stored nor logged (RNF-IDA-05).

**Audit** (design.md §7.4): success inside the transaction; a rejection after the rollback, in a
write of its own, with the reason only (Q-125: never the email nor the ``sub``) and the user as the
actor when the error names one (``user_inactive``), anonymous otherwise. ``login_cancelled`` and
``google_unavailable`` go to the logs only, like the ``429`` (Q-111). ``UserProvisioningError``
is no rejection: it leaves as it comes, and the API answers ``500 internal_error``.

**Logs** (RNF-IDA-04): one ``auth.login_*`` event per callback with its ``outcome`` and, unless it
succeeded, its ``reason``. Never ``code``, ``code_verifier``, ``state``, ``nonce``, the binding nor
a token (RN-IDA-16).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from apps.common import feature_flags
from apps.common.logging import get_logger
from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
)
from apps.identity.domain.client_hint import summarize_user_agent
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.login_rules import LoginRejectedError, evaluate_identity
from apps.identity.domain.secrets_format import hash_secret
from apps.identity.models import LoginAttempt
from apps.identity.oidc.google_gateway import GoogleAuthFailedError, GoogleUnavailableError
from apps.identity.oidc.provider import get_google_gateway, get_id_token_verifier
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.registry import get_audit_port
from apps.identity.services.login_start import LOGIN_FLAG, LoginDisabledError
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.user_provisioning import provision_user
from apps.identity.tokens.access_token import ACCESS_TOKEN_TTL_SECONDS, issue_access_token

ACCESS_DENIED = "access_denied"
SUCCEEDED_EVENT = "auth.login_succeeded"
REJECTED_EVENT = "auth.login_rejected"
CANCELLED_EVENT = "auth.login_cancelled"
UNAVAILABLE_EVENT = "auth.login_unavailable"

logger = get_logger(__name__)

_ATTEMPTS = LoginAttempt._meta.db_table
# Hashes compared in the database; the expiry by the database's clock too would be a second clock,
# so ``now`` is the caller's, the same one that judged the session.
_CONSUME_SQL = (
    f"DELETE FROM {_ATTEMPTS} "  # noqa: S608 - the table name is the model's, not input
    "WHERE state_hash = %s AND binding_hash = %s AND expires_at > %s "
    "RETURNING nonce_hash, code_verifier, return_path"
)


class LoginCancelledError(IdentityError):
    """The person said no at Google: not a rejection of the Hub (design.md §4.2, step 3)."""

    def __init__(self) -> None:
        super().__init__(IdentityErrorCode.LOGIN_CANCELLED)


@dataclass(frozen=True, slots=True)
class CompletedLogin:
    """What the BFF turns into cookies. The tokens stay out of ``repr`` (C-06)."""

    access_token: str = field(repr=False)
    access_expires_in: int
    refresh_token: str = field(repr=False)
    session_id: UUID
    session_expires_in: int
    return_path: str


@dataclass(frozen=True, slots=True)
class _Attempt:
    nonce_hash: str = field(repr=False)
    code_verifier: str = field(repr=False)
    return_path: str


def complete_login(
    *,
    state: str,
    login_binding: str,
    code: str | None,
    error: str | None,
    client_user_agent: str | None = None,
    now: datetime | None = None,
) -> CompletedLogin:
    """The session of the person Google vouches for, or the error of the first step that fails."""
    if not feature_flags.is_enabled(LOGIN_FLAG):
        raise LoginDisabledError
    moment = now or timezone.now()
    try:
        return _complete(
            state=state,
            login_binding=login_binding,
            code=code,
            error=error,
            client_user_agent=client_user_agent,
            now=moment,
        )
    except LoginRejectedError as rejection:
        # Out of every transaction by now: the rollback already took what the login did.
        _audit_rejection(rejection, now=moment)
        raise
    except LoginCancelledError:
        logger.info(
            CANCELLED_EVENT, outcome="cancelled", reason=IdentityErrorCode.LOGIN_CANCELLED.value
        )
        raise
    except GoogleUnavailableError:
        logger.warning(
            UNAVAILABLE_EVENT,
            outcome="unavailable",
            reason=IdentityErrorCode.GOOGLE_UNAVAILABLE.value,
        )
        raise


def _complete(
    *,
    state: str,
    login_binding: str,
    code: str | None,
    error: str | None,
    client_user_agent: str | None,
    now: datetime,
) -> CompletedLogin:
    attempt = _consume_attempt(state=state, login_binding=login_binding, now=now)
    if error == ACCESS_DENIED:
        raise LoginCancelledError
    if error or not code:
        _reject(IdentityErrorCode.GOOGLE_AUTH_FAILED)
    try:
        id_token = get_google_gateway().exchange_code(
            code=code, code_verifier=attempt.code_verifier
        )
        claims = get_id_token_verifier().verify(id_token, expected_nonce_hash=attempt.nonce_hash)
    except GoogleAuthFailedError:
        raise LoginRejectedError(IdentityErrorCode.GOOGLE_AUTH_FAILED) from None
    identity = evaluate_identity(
        sub=claims.sub,
        email=claims.email,
        email_verified=claims.email_verified,
        name=claims.name,
        picture=claims.picture,
    )
    client = summarize_user_agent(client_user_agent)
    with transaction.atomic():
        user = provision_user(identity, now=now)
        opened = open_session(user, now=now, client_browser=client.browser, client_os=client.os)
        session = opened.session
        access_token = issue_access_token(user_id=user.pk, session_id=session.pk, now=now)
        _record(
            AuditEvent(
                action=IdentityAuditAction.LOGIN_SUCCEEDED,
                result=AuditResult.SUCCESS,
                actor_type=AuditActorType.USER,
                actor_id=user.pk,
                occurred_at=now,
            )
        )
    logger.info(SUCCEEDED_EVENT, outcome="succeeded", user_id=str(user.pk))
    return CompletedLogin(
        access_token=access_token,
        access_expires_in=ACCESS_TOKEN_TTL_SECONDS,
        refresh_token=opened.refresh_token,
        session_id=session.pk,
        session_expires_in=int((session.idle_expires_at - now).total_seconds()),
        return_path=attempt.return_path,
    )


def _consume_attempt(*, state: str, login_binding: str, now: datetime) -> _Attempt:
    """Step 2: the live attempt of this ``state`` and binding, deleted as it is read."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(_CONSUME_SQL, [hash_secret(state), hash_secret(login_binding), now])
        row = cursor.fetchone()
    if row is None:
        _reject(IdentityErrorCode.GOOGLE_AUTH_FAILED)
    nonce_hash, code_verifier, return_path = row
    return _Attempt(nonce_hash=nonce_hash, code_verifier=code_verifier, return_path=return_path)


def _reject(code: IdentityErrorCode) -> NoReturn:
    raise LoginRejectedError(code)


def _audit_rejection(rejection: LoginRejectedError, *, now: datetime) -> None:
    """Q-125: the reason and, for a known user, its id; nothing of whom Google described."""
    user_id = rejection.user_id
    _record(
        AuditEvent(
            action=IdentityAuditAction.LOGIN_REJECTED,
            result=AuditResult.FAILURE,
            reason=rejection.code.value,
            actor_type=AuditActorType.ANONYMOUS if user_id is None else AuditActorType.USER,
            actor_id=user_id,
            occurred_at=now,
        )
    )
    logger.info(
        REJECTED_EVENT,
        outcome="rejected",
        reason=rejection.code.value,
        user_id=None if user_id is None else str(user_id),
    )


def _record(event: AuditEvent) -> None:
    get_audit_port().record(event)
