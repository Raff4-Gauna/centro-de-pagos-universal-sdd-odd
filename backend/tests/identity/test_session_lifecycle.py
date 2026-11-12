"""``services/session_lifecycle.py``: opening a session and its conditional transitions.

A transition is one ``UPDATE … WHERE status='active'``: it reports whether it moved the session,
and a terminal session is never touched again (design.md §5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection

from apps.identity.domain.secrets_format import hash_secret, parse_refresh_token
from apps.identity.domain.session_policy import ABSOLUTE_LIFETIME, IDLE_LIFETIME
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User
from apps.identity.services.session_lifecycle import (
    expire,
    issue_refresh_token,
    open_session,
    revoke,
)

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-1", email="ana@x.com")


def stored_text() -> str:
    """Every value of every column of both tables, as text."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT row_to_json(s)::text FROM auth_sessions s"
            " UNION ALL SELECT row_to_json(t)::text FROM refresh_tokens t"
        )
        return "\n".join(row for (row,) in cursor.fetchall())


def test_AC_IDA_16_open_session_fixes_both_deadlines(user: User) -> None:
    opened = open_session(user, now=NOW, client_browser="Firefox", client_os="Linux")
    session = AuthSession.objects.get(pk=opened.session.pk)

    assert session.status == SessionStatus.ACTIVE
    assert session.created_at == session.last_used_at == NOW
    assert session.absolute_expires_at == NOW + ABSOLUTE_LIFETIME
    assert session.idle_expires_at == NOW + IDLE_LIFETIME
    assert session.ended_at is None
    assert session.revoke_reason is None
    assert (session.client_browser, session.client_os) == ("Firefox", "Linux")


def test_open_session_clamps_the_client_hints(user: User) -> None:
    opened = open_session(user, now=NOW, client_browser="b" * 40, client_os="o" * 40)
    assert (opened.session.client_browser, opened.session.client_os) == ("b" * 32, "o" * 32)


def test_AC_IDA_14_only_hash_is_stored(user: User) -> None:
    opened = open_session(user, now=NOW)
    token = RefreshToken.objects.get(session=opened.session)

    assert parse_refresh_token(opened.refresh_token) == opened.session.pk
    assert token.token_hash == hash_secret(opened.refresh_token)
    assert token.issued_at == NOW
    assert token.used_at is None
    assert token.replaced_by is None
    secret = opened.refresh_token.rsplit(".", 1)[1]
    text = stored_text()
    assert opened.refresh_token not in text
    assert secret not in text


def test_AC_IDA_14_issued_token_is_hashed_and_new(user: User) -> None:
    opened = open_session(user, now=NOW)
    RefreshToken.objects.filter(session=opened.session).update(used_at=LATER)

    raw = issue_refresh_token(opened.session, now=LATER)

    assert raw != opened.refresh_token
    assert parse_refresh_token(raw) == opened.session.pk
    live = RefreshToken.objects.get(session=opened.session, used_at__isnull=True)
    assert live.token_hash == hash_secret(raw)
    assert live.issued_at == LATER
    assert raw not in stored_text()


def test_AC_IDA_14_opened_session_repr_hides_the_token(user: User) -> None:
    opened = open_session(user, now=NOW)
    assert opened.refresh_token not in repr(opened)


def test_RN_IDA_10_one_live_token_per_open_session(user: User) -> None:
    first = open_session(user, now=NOW)
    second = open_session(user, now=LATER)
    assert first.session.pk != second.session.pk
    for opened in (first, second):
        assert (
            RefreshToken.objects.filter(session=opened.session, used_at__isnull=True).count() == 1
        )


@pytest.mark.parametrize("reason", list(RevokeReason))
def test_revoke_ends_an_active_session(user: User, reason: RevokeReason) -> None:
    opened = open_session(user, now=NOW)

    assert revoke(opened.session.pk, reason=reason, now=LATER) is True

    session = AuthSession.objects.get(pk=opened.session.pk)
    assert session.status == SessionStatus.REVOKED
    assert session.revoke_reason == reason
    assert session.ended_at == LATER


def test_AC_IDA_16_expire_ends_at_the_idle_deadline(user: User) -> None:
    opened = open_session(user, now=NOW)
    after_idle = NOW + IDLE_LIFETIME + timedelta(days=1)

    assert expire(opened.session.pk, now=after_idle) is True

    session = AuthSession.objects.get(pk=opened.session.pk)
    assert session.status == SessionStatus.EXPIRED
    assert session.ended_at == session.idle_expires_at == NOW + IDLE_LIFETIME
    assert session.revoke_reason is None


def test_AC_IDA_16_expire_at_the_exact_deadline(user: User) -> None:
    opened = open_session(user, now=NOW)
    assert expire(opened.session.pk, now=NOW + IDLE_LIFETIME) is True


def test_AC_IDA_16_expire_leaves_a_live_session_alone(user: User) -> None:
    opened = open_session(user, now=NOW)

    assert expire(opened.session.pk, now=NOW + IDLE_LIFETIME - timedelta(seconds=1)) is False
    assert AuthSession.objects.get(pk=opened.session.pk).status == SessionStatus.ACTIVE


def test_session_terminal_never_returns_to_active(user: User) -> None:
    revoked = open_session(user, now=NOW).session
    expired = open_session(user, now=NOW).session
    after_idle = NOW + IDLE_LIFETIME
    assert revoke(revoked.pk, reason=RevokeReason.LOGOUT, now=LATER)
    assert expire(expired.pk, now=after_idle)

    for session_id in (revoked.pk, expired.pk):
        assert revoke(session_id, reason=RevokeReason.USER_REVOKED, now=after_idle) is False
        assert expire(session_id, now=after_idle + timedelta(days=1)) is False

    revoked.refresh_from_db()
    expired.refresh_from_db()
    assert (revoked.status, revoked.revoke_reason, revoked.ended_at) == (
        SessionStatus.REVOKED,
        RevokeReason.LOGOUT,
        LATER,
    )
    assert (expired.status, expired.revoke_reason, expired.ended_at) == (
        SessionStatus.EXPIRED,
        None,
        after_idle,
    )


def test_transitions_on_an_unknown_session_change_nothing(user: User) -> None:
    opened = open_session(user, now=NOW)
    unknown = parse_refresh_token(open_session(user, now=NOW).refresh_token)
    AuthSession.objects.filter(pk=unknown).delete()

    assert revoke(unknown, reason=RevokeReason.LOGOUT, now=LATER) is False
    assert expire(unknown, now=NOW + ABSOLUTE_LIFETIME) is False
    assert AuthSession.objects.get(pk=opened.session.pk).status == SessionStatus.ACTIVE
