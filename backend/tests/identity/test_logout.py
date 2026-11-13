"""``services/logout.py``: which session a logout ends and what it leaves (RF-IDA-05, RN-IDA-14;
AC-IDA-17 backend, AC-IDA-35; design.md §4.6, §7.4).

One caller at a time, every mark from the ``now`` passed in. The JWTs are issued at a past ``now``
on purpose: logout takes a token whose signature is good even long after it expired.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.audit_events import AuditActorType, AuditResult, IdentityAuditAction
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.secrets_format import generate_refresh_token
from apps.identity.models import AuthSession, RevokeReason, SessionStatus, User
from apps.identity.services.logout import logout
from apps.identity.services.refresh import refresh_session
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import TOKEN_TYPE, issue_access_token
from tests.identity.fakes import Ports, install_ports

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
LATER = NOW + timedelta(hours=2)  # the JWT issued at NOW expired 1 h 45 min before

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-logout", email="ana@example.com")


@pytest.fixture
def opened(user: User) -> OpenedSession:
    return open_session(user, now=NOW)


def session_of(opened: OpenedSession) -> AuthSession:
    return AuthSession.objects.get(pk=opened.session.pk)


def access_of(opened: OpenedSession, *, now: datetime = NOW) -> str:
    return issue_access_token(user_id=opened.session.user_id, session_id=opened.session.pk, now=now)


def assert_untouched(opened: OpenedSession) -> None:
    session = session_of(opened)
    assert (session.status, session.ended_at, session.revoke_reason) == (
        SessionStatus.ACTIVE,
        None,
        None,
    )


# --- By the refresh token (AC-IDA-17) ------------------------------------------------------------


def test_AC_IDA_17_logout_revokes_and_audits(opened: OpenedSession, ports: Ports) -> None:
    with capture_logs() as logs:
        ended = logout(refresh_token=opened.refresh_token, now=LATER)

    assert ended is True
    session = session_of(opened)
    assert (session.status, session.revoke_reason, session.ended_at) == (
        SessionStatus.REVOKED,
        RevokeReason.LOGOUT,
        LATER,
    )
    with pytest.raises(IdentityError) as refused:  # the refresh token stops working
        refresh_session(opened.refresh_token, now=LATER)
    assert refused.value.code is IdentityErrorCode.SESSION_REVOKED
    [event] = ports.audit.events
    assert event.action is IdentityAuditAction.LOGOUT
    assert (event.result, event.reason) == (AuditResult.SUCCESS, None)
    assert (event.actor_type, event.actor_id) == (AuditActorType.USER, opened.session.user_id)
    assert (event.organization_id, event.occurred_at) == (None, LATER)
    assert event.metadata == {"sid": str(opened.session.pk)}
    assert opened.refresh_token not in str(logs) + str(event)


def test_AC_IDA_17_second_logout_no_effects(opened: OpenedSession, ports: Ports) -> None:
    logout(refresh_token=opened.refresh_token, now=LATER)

    again = logout(refresh_token=opened.refresh_token, now=LATER + timedelta(minutes=5))

    assert again is False
    assert session_of(opened).ended_at == LATER  # the first logout's mark stays
    assert len(ports.audit.events) == 1


def test_AC_IDA_17_a_used_refresh_token_still_logs_out(opened: OpenedSession, ports: Ports) -> None:
    # The cookie may hold the token of the grace window: rotated by another tab, not yet replaced.
    refresh_session(opened.refresh_token, now=NOW + timedelta(minutes=1))

    assert logout(refresh_token=opened.refresh_token, now=LATER) is True
    assert session_of(opened).status == SessionStatus.REVOKED


def test_unknown_or_malformed_refresh_token_has_no_effects(
    opened: OpenedSession, ports: Ports
) -> None:
    forged = generate_refresh_token(opened.session.pk)
    for raw in (forged, "rt1.garbage", "", f"{opened.refresh_token}x"):
        assert logout(refresh_token=raw, now=LATER) is False
    assert_untouched(opened)
    assert ports.audit.events == []


def test_nothing_to_identify_a_session_has_no_effects(ports: Ports) -> None:
    assert logout(now=LATER) is False
    assert ports.audit.events == []


# --- By an access JWT, valid signature even if expired (AC-IDA-35) -------------------------------


def test_AC_IDA_35_expired_jwt_still_revokes(opened: OpenedSession, ports: Ports) -> None:
    assert logout(access_token=access_of(opened), now=LATER) is True

    session = session_of(opened)
    assert (session.status, session.revoke_reason) == (SessionStatus.REVOKED, RevokeReason.LOGOUT)
    [event] = ports.audit.events
    assert event.action is IdentityAuditAction.LOGOUT


def test_AC_IDA_35_jwt_signed_by_another_key_has_no_effects(
    opened: OpenedSession, ports: Ports
) -> None:
    claims = jwt.decode(access_of(opened), options={"verify_signature": False})
    forged = jwt.encode(
        claims,
        ec.generate_private_key(ec.SECP256R1()),
        algorithm="ES256",
        headers={"kid": jwt.get_unverified_header(access_of(opened))["kid"], "typ": TOKEN_TYPE},
    )

    assert logout(access_token=forged, now=LATER) is False
    assert_untouched(opened)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_AC_IDA_35_not_a_jwt_has_no_effects(
    opened: OpenedSession, ports: Ports, token: str
) -> None:
    assert logout(access_token=token, now=LATER) is False
    assert_untouched(opened)


def test_AC_IDA_35_jwt_of_another_user_for_the_session_has_no_effects(
    opened: OpenedSession, ports: Ports
) -> None:
    other = User.objects.create_user(google_sub="sub-other", email="otra@example.com")
    signed = issue_access_token(user_id=other.pk, session_id=opened.session.pk, now=NOW)

    assert logout(access_token=signed, now=LATER) is False
    assert_untouched(opened)


def test_refresh_token_comes_before_the_jwt(
    user: User, opened: OpenedSession, ports: Ports
) -> None:
    other = open_session(user, now=NOW)

    logout(refresh_token=opened.refresh_token, access_token=access_of(other), now=LATER)

    assert session_of(opened).status == SessionStatus.REVOKED
    assert_untouched(other)


def test_unknown_refresh_token_falls_back_to_the_jwt(opened: OpenedSession, ports: Ports) -> None:
    forged = generate_refresh_token(opened.session.pk)

    assert logout(refresh_token=forged, access_token=access_of(opened), now=LATER) is True


# --- Reasons and sessions already out of active --------------------------------------------------


def test_superseded_is_audited_as_session_revoked(opened: OpenedSession, ports: Ports) -> None:
    logout(refresh_token=opened.refresh_token, reason=RevokeReason.SUPERSEDED, now=LATER)

    assert session_of(opened).revoke_reason == RevokeReason.SUPERSEDED
    [event] = ports.audit.events
    assert (event.action, event.reason) == (IdentityAuditAction.SESSION_REVOKED, "superseded")
    assert (event.actor_type, event.actor_id) == (AuditActorType.USER, opened.session.user_id)
    assert event.organization_id is None


@pytest.mark.parametrize(
    "reason", [RevokeReason.USER_REVOKED, RevokeReason.REFRESH_REUSE, RevokeReason.REVOKED_OTHERS]
)
def test_logout_takes_only_its_two_reasons(opened: OpenedSession, reason: RevokeReason) -> None:
    with pytest.raises(ValueError, match="logout"):
        logout(refresh_token=opened.refresh_token, reason=reason, now=LATER)
    assert_untouched(opened)


def test_session_past_its_deadline_is_expired_not_logged_out(
    opened: OpenedSession, ports: Ports
) -> None:
    past_idle = session_of(opened).idle_expires_at + timedelta(seconds=1)

    assert logout(refresh_token=opened.refresh_token, now=past_idle) is False

    session = session_of(opened)
    assert (session.status, session.revoke_reason) == (SessionStatus.EXPIRED, None)
    assert session.ended_at == session.idle_expires_at
    assert ports.audit.events == []  # it had already ended: no logout happened


def test_logout_after_a_reuse_revocation_keeps_its_reason(
    opened: OpenedSession, ports: Ports
) -> None:
    successor = refresh_session(opened.refresh_token, now=NOW).refresh_token
    assert successor is not None
    refresh_session(successor, now=NOW + timedelta(minutes=1))
    with pytest.raises(IdentityError):  # the first token, well past grace: reuse
        refresh_session(opened.refresh_token, now=NOW + timedelta(minutes=10))
    events_before = len(ports.audit.events)

    assert logout(refresh_token=opened.refresh_token, now=LATER) is False
    assert session_of(opened).revoke_reason == RevokeReason.REFRESH_REUSE
    assert len(ports.audit.events) == events_before


def test_logout_logs_ids_never_tokens(opened: OpenedSession, ports: Ports) -> None:
    access = access_of(opened)
    with capture_logs() as logs:
        logout(refresh_token=opened.refresh_token, access_token=access, now=LATER)
        logout(refresh_token=f"{opened.refresh_token}x", access_token=f"{access}x", now=LATER)
    text = str(logs)
    for secret in (opened.refresh_token, access, opened.refresh_token.rsplit(".", 1)[1]):
        assert secret not in text
    assert [entry["event"] for entry in logs] == ["identity.logout", "identity.logout"]
    assert [entry["result"] for entry in logs] == ["revoked", "no_session"]
