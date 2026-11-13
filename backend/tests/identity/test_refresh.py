"""``services/refresh.py``: rotation, deadlines and the used token (RF-IDA-04, RN-IDA-10, RN-IDA-11;
AC-IDA-09, 14, 15, 16, 28; design.md §4.5).

One caller at a time: two refreshes racing on two connections are ``T-IDA-15``'s. Every mark comes
from the ``now`` passed in, so the deadlines are exact to the microsecond.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from django.db import connection
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.audit_events import (
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
)
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.secrets_format import generate_refresh_token, hash_secret
from apps.identity.domain.session_policy import (
    ABSOLUTE_LIFETIME,
    IDLE_LIFETIME,
    REFRESH_GRACE,
    RefreshDecision,
)
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User
from apps.identity.ports.audit import AuditEvent
from apps.identity.services.refresh import RefreshedSession, refresh_session
from apps.identity.services.session_lifecycle import OpenedSession, open_session, revoke

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class RecordingAuditPort:
    events: list[AuditEvent] = []  # noqa: RUF012 - reset by the fixture, read by the tests

    def record(self, event: AuditEvent) -> None:
        RecordingAuditPort.events.append(event)


@pytest.fixture(autouse=True)
def audit(settings: SettingsWrapper) -> None:
    RecordingAuditPort.events = []
    settings.IDENTITY_AUDIT_PORT = f"{__name__}.RecordingAuditPort"


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-refresh", email="ana@example.com")


@pytest.fixture
def opened(user: User) -> OpenedSession:
    return open_session(user, now=NOW)


def session_of(opened: OpenedSession) -> AuthSession:
    return AuthSession.objects.get(pk=opened.session.pk)


def rejected_code(raw: str, *, now: datetime) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as info:
        refresh_session(raw, now=now)
    return info.value.code


def rotate(raw: str, *, now: datetime) -> str:
    refreshed = refresh_session(raw, now=now)
    assert refreshed.refresh_token is not None
    return refreshed.refresh_token


def claims_of(access_token: str) -> dict[str, Any]:
    """Its claims, unverified: the JWT was issued at ``NOW`` and is long expired by the wall clock
    (``tests/identity/tokens`` verifies them; ``api/test_refresh_view.py`` too, on a live one)."""
    claims: dict[str, Any] = jwt.decode(access_token, options={"verify_signature": False})
    return claims


def stored_text() -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT row_to_json(s)::text FROM auth_sessions s"
            " UNION ALL SELECT row_to_json(t)::text FROM refresh_tokens t"
        )
        return "\n".join(row for (row,) in cursor.fetchall())


# --- Rotation (AC-IDA-14) ------------------------------------------------------------------------


def test_AC_IDA_14_rotation_new_pair(opened: OpenedSession) -> None:
    moment = NOW + timedelta(hours=1)

    refreshed = refresh_session(opened.refresh_token, now=moment)

    assert refreshed.decision is RefreshDecision.ROTATE
    assert refreshed.refresh_token is not None
    assert refreshed.refresh_token != opened.refresh_token
    claims = claims_of(refreshed.access_token)
    assert (claims["sub"], claims["sid"]) == (str(opened.session.user_id), str(opened.session.pk))
    assert claims["iat"] == int(moment.timestamp())
    old = RefreshToken.objects.get(token_hash=hash_secret(opened.refresh_token))
    new = RefreshToken.objects.get(token_hash=hash_secret(refreshed.refresh_token))
    assert old.used_at == moment  # the same clock as everything else
    assert old.replaced_by_id == new.pk
    assert (new.issued_at, new.used_at, new.session_id) == (moment, None, opened.session.pk)
    session = session_of(opened)
    assert session.last_used_at == moment
    assert session.idle_expires_at == moment + IDLE_LIFETIME
    assert refreshed.session_expires_in == int(IDLE_LIFETIME.total_seconds())
    text = stored_text()
    assert refreshed.refresh_token not in text
    assert refreshed.refresh_token.rsplit(".", 1)[1] not in text


def test_AC_IDA_14_the_new_token_rotates_again(opened: OpenedSession) -> None:
    second = rotate(opened.refresh_token, now=NOW + timedelta(minutes=14))
    third = rotate(second, now=NOW + timedelta(minutes=28))
    assert len({opened.refresh_token, second, third}) == 3
    assert RefreshToken.objects.filter(session=opened.session, used_at__isnull=True).count() == 1


def test_refreshed_session_hides_its_tokens(opened: OpenedSession) -> None:
    refreshed = refresh_session(opened.refresh_token, now=NOW + timedelta(minutes=1))
    assert isinstance(refreshed, RefreshedSession)
    assert refreshed.access_token not in repr(refreshed)
    assert str(refreshed.refresh_token) not in repr(refreshed)


# --- Deadlines (AC-IDA-16) -----------------------------------------------------------------------


@pytest.mark.parametrize("past", [timedelta(0), timedelta(microseconds=1), timedelta(days=1)])
def test_AC_IDA_16_idle_expired_refresh(opened: OpenedSession, past: timedelta) -> None:
    moment = NOW + IDLE_LIFETIME + past

    assert rejected_code(opened.refresh_token, now=moment) is IdentityErrorCode.SESSION_REVOKED

    session = session_of(opened)
    assert session.status == SessionStatus.EXPIRED  # materialized on the spot, and committed
    assert session.ended_at == NOW + IDLE_LIFETIME
    assert session.revoke_reason is None
    assert RefreshToken.objects.filter(session=opened.session).count() == 1
    assert RecordingAuditPort.events == []


def test_AC_IDA_16_just_before_the_idle_deadline_still_rotates(opened: OpenedSession) -> None:
    moment = NOW + IDLE_LIFETIME - timedelta(microseconds=1)
    assert refresh_session(opened.refresh_token, now=moment).decision is RefreshDecision.ROTATE


def test_AC_IDA_16_absolute_expired_refresh(opened: OpenedSession) -> None:
    # Used every day: the idle deadline never comes, the absolute one does.
    raw = opened.refresh_token
    for day in range(1, 30):
        raw = rotate(raw, now=NOW + timedelta(days=day))
    absolute = NOW + ABSOLUTE_LIFETIME

    assert rejected_code(raw, now=absolute) is IdentityErrorCode.SESSION_REVOKED

    session = session_of(opened)
    assert session.status == SessionStatus.EXPIRED
    assert session.ended_at == absolute


def test_AC_IDA_16_refresh_never_moves_absolute(opened: OpenedSession) -> None:
    absolute = NOW + ABSOLUTE_LIFETIME
    raw = opened.refresh_token
    # Never more than 7 days apart, the last one an hour before the absolute deadline.
    moments = [NOW + timedelta(days=day) for day in (6, 12, 18, 24)] + [
        absolute - timedelta(hours=1)
    ]
    for moment in moments:
        refreshed = refresh_session(raw, now=moment)
        assert refreshed.refresh_token is not None
        raw = refreshed.refresh_token
        session = session_of(opened)
        assert session.absolute_expires_at == absolute
        assert session.created_at == NOW
        assert session.idle_expires_at == min(moment + IDLE_LIFETIME, absolute)
        assert refreshed.session_expires_in == int(
            (session.idle_expires_at - moment).total_seconds()
        )
    assert refreshed.session_expires_in == 3600  # the last day: capped by the absolute deadline


# --- What can no longer refresh ------------------------------------------------------------------


def test_AC_IDA_09_inactive_user_refresh(opened: OpenedSession, user: User) -> None:
    User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=NOW)

    code = rejected_code(opened.refresh_token, now=NOW + timedelta(minutes=5))

    assert code is IdentityErrorCode.SESSION_REVOKED
    token = RefreshToken.objects.get(session=opened.session)
    assert token.used_at is None  # no tokens: nothing was issued nor spent
    assert RecordingAuditPort.events == []


@pytest.mark.parametrize("reason", [RevokeReason.LOGOUT, RevokeReason.USER_DEACTIVATED])
def test_revoked_session_refresh_is_session_revoked(
    opened: OpenedSession, reason: RevokeReason
) -> None:
    revoke(opened.session.pk, reason=reason, now=NOW + timedelta(minutes=1))

    code = rejected_code(opened.refresh_token, now=NOW + timedelta(minutes=2))

    assert code is IdentityErrorCode.SESSION_REVOKED
    assert session_of(opened).revoke_reason == reason  # untouched
    assert RefreshToken.objects.filter(session=opened.session).count() == 1


def test_unknown_token_is_token_invalid(opened: OpenedSession) -> None:
    # The right session id with another secret: only the hash proves a token is genuine.
    forged = generate_refresh_token(opened.session.pk)
    assert rejected_code(forged, now=NOW) is IdentityErrorCode.TOKEN_INVALID
    assert session_of(opened).last_used_at == NOW


def test_token_of_another_session_id_is_token_invalid(opened: OpenedSession, user: User) -> None:
    # Its hash is known, its <sid> is not its session's: it does not exist as presented.
    other = open_session(user, now=NOW).session
    prefix, _, secret = opened.refresh_token.split(".")
    other_sid = generate_refresh_token(other.pk).split(".")[1]
    assert rejected_code(f"{prefix}.{other_sid}.{secret}", now=NOW) is (
        IdentityErrorCode.TOKEN_INVALID
    )


@pytest.mark.parametrize("raw", ["", "garbage", "rt1..", "rt1.x.y"])
def test_malformed_token_is_token_invalid(raw: str) -> None:
    assert rejected_code(raw, now=NOW) is IdentityErrorCode.TOKEN_INVALID


# --- The used token: grace and reuse (AC-IDA-28, AC-IDA-15; the race itself is T-IDA-15) ---------


def test_AC_IDA_28_used_token_within_grace_gets_access_only(opened: OpenedSession) -> None:
    rotated_at = NOW + timedelta(minutes=10)
    successor = rotate(opened.refresh_token, now=rotated_at)
    before = session_of(opened)

    late = refresh_session(opened.refresh_token, now=rotated_at + REFRESH_GRACE)

    assert late.decision is RefreshDecision.GRACE
    assert late.refresh_token is None
    assert claims_of(late.access_token)["sid"] == str(opened.session.pk)
    after = session_of(opened)
    assert (after.status, after.last_used_at, after.idle_expires_at) == (
        SessionStatus.ACTIVE,
        before.last_used_at,
        before.idle_expires_at,
    )
    assert RefreshToken.objects.filter(session=opened.session).count() == 2
    assert RecordingAuditPort.events == []
    # The tab that rotated goes on with its token.
    assert rotate(successor, now=rotated_at + timedelta(minutes=1))


def test_AC_IDA_15_used_token_past_grace_revokes_session(opened: OpenedSession) -> None:
    rotated_at = NOW + timedelta(minutes=10)
    successor = rotate(opened.refresh_token, now=rotated_at)
    replay_at = rotated_at + REFRESH_GRACE + timedelta(microseconds=1)

    with capture_logs() as logs:
        code = rejected_code(opened.refresh_token, now=replay_at)

    assert code is IdentityErrorCode.SESSION_REVOKED
    session = session_of(opened)
    assert (session.status, session.revoke_reason, session.ended_at) == (
        SessionStatus.REVOKED,
        RevokeReason.REFRESH_REUSE,
        replay_at,
    )
    # The live token of the session is worth nothing either.
    assert rejected_code(successor, now=replay_at) is IdentityErrorCode.SESSION_REVOKED
    detected, revoked = RecordingAuditPort.events
    assert detected.action == IdentityAuditAction.REFRESH_REUSE_DETECTED
    assert revoked.action == IdentityAuditAction.SESSION_REVOKED
    assert revoked.reason == "refresh_reuse"
    assert (revoked.result, detected.result) == (AuditResult.SUCCESS, AuditResult.FAILURE)
    for event in (detected, revoked):
        assert event.actor_type == AuditActorType.SYSTEM
        assert event.organization_id is None
        assert event.occurred_at == replay_at
        assert event.metadata == {
            "sid": str(opened.session.pk),
            "user_id": str(opened.session.user_id),
        }
    [alert] = [entry for entry in logs if entry["event"] == "identity.refresh_reuse_detected"]
    assert alert["alert"] is True
    assert opened.refresh_token not in str(logs)
    assert successor not in str(logs)


def test_AC_IDA_15_used_token_whose_successor_was_used_is_reuse(opened: OpenedSession) -> None:
    # Within 30 s, but the chain moved on: a replay, not a concurrent tab (ADR-0004 §3).
    second = rotate(opened.refresh_token, now=NOW + timedelta(seconds=1))
    rotate(second, now=NOW + timedelta(seconds=2))

    code = rejected_code(opened.refresh_token, now=NOW + timedelta(seconds=3))

    assert code is IdentityErrorCode.SESSION_REVOKED
    assert session_of(opened).revoke_reason == RevokeReason.REFRESH_REUSE


def test_AC_IDA_23_refresh_logs_carry_no_token(opened: OpenedSession) -> None:
    with capture_logs() as logs:
        refreshed = refresh_session(opened.refresh_token, now=NOW + timedelta(minutes=1))
        rejected_code("rt1.garbage", now=NOW)
    text = str(logs)
    for secret in (opened.refresh_token, refreshed.refresh_token, refreshed.access_token):
        assert str(secret) not in text
    assert hash_secret(opened.refresh_token) not in text
    events = [entry["event"] for entry in logs]
    assert events == ["identity.refresh_succeeded", "identity.refresh_rejected"]
