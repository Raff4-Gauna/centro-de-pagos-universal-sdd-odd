"""The ``auth_sessions`` and ``refresh_tokens`` tables (design.md §5): what the database refuses.

Rows go in through ``objects.create``/``update``, which check nothing: what stops a bad row here is
PostgreSQL, so a service bug cannot leave a session or a token in a shape the spec forbids.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import DataError, IntegrityError, connection, transaction

from apps.identity.domain.secrets_format import generate_refresh_token, hash_secret
from apps.identity.domain.session_policy import ABSOLUTE_LIFETIME, IDLE_LIFETIME
from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def user() -> User:
    return User.objects.create_user(google_sub="sub-1", email="ana@x.com")


def session_row(user: User, **overrides: Any) -> dict[str, Any]:
    return {
        "user": user,
        "created_at": NOW,
        "last_used_at": NOW,
        "idle_expires_at": NOW + IDLE_LIFETIME,
        "absolute_expires_at": NOW + ABSOLUTE_LIFETIME,
        **overrides,
    }


def assert_rejected(constraint: str, model: type[Any], **values: Any) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        model.objects.create(**values)


def new_token(session: AuthSession, **overrides: Any) -> RefreshToken:
    token_hash = hash_secret(generate_refresh_token(session.id))
    return RefreshToken.objects.create(
        session=session, token_hash=token_hash, issued_at=NOW, **overrides
    )


# --- auth_sessions ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "absolute", [NOW + ABSOLUTE_LIFETIME + timedelta(seconds=1), NOW + timedelta(days=29)]
)
def test_AC_IDA_16_absolute_expiry_constraint(user: User, absolute: datetime) -> None:
    assert_rejected(
        "auth_sessions_absolute_is_30_days",
        AuthSession,
        **session_row(user, absolute_expires_at=absolute, idle_expires_at=NOW),
    )


def test_AC_IDA_16_absolute_expiry_cannot_be_moved_later(user: User) -> None:
    session = AuthSession.objects.create(**session_row(user))
    later = session.absolute_expires_at + IDLE_LIFETIME
    with (
        pytest.raises(IntegrityError, match="auth_sessions_absolute_is_30_days"),
        transaction.atomic(),
    ):
        AuthSession.objects.filter(pk=session.pk).update(absolute_expires_at=later)


def test_AC_IDA_16_absolute_check_ignores_the_connection_time_zone(user: User) -> None:
    """Across a DST change 30 calendar days are not 720 hours; the check counts hours."""
    created = datetime(2026, 10, 20, 12, tzinfo=UTC)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'America/New_York'")
    session = AuthSession.objects.create(
        **session_row(
            user,
            created_at=created,
            last_used_at=created,
            idle_expires_at=created,
            absolute_expires_at=created + ABSOLUTE_LIFETIME,
        )
    )
    assert session.pk


def test_AC_IDA_16_idle_never_passes_absolute(user: User) -> None:
    assert_rejected(
        "auth_sessions_idle_within_absolute",
        AuthSession,
        **session_row(user, idle_expires_at=NOW + ABSOLUTE_LIFETIME + timedelta(seconds=1)),
    )


def test_AC_IDA_16_idle_equal_to_absolute_is_valid(user: User) -> None:
    session = AuthSession.objects.create(
        **session_row(user, idle_expires_at=NOW + ABSOLUTE_LIFETIME)
    )
    assert session.idle_expires_at == session.absolute_expires_at


@pytest.mark.parametrize(
    ("status", "ended_at", "reason"),
    [
        (SessionStatus.ACTIVE, NOW, None),
        (SessionStatus.EXPIRED, None, None),
        (SessionStatus.REVOKED, None, RevokeReason.LOGOUT),
    ],
)
def test_session_ended_at_iff_terminal(
    user: User, status: str, ended_at: datetime | None, reason: str | None
) -> None:
    values = session_row(user, status=status, ended_at=ended_at, revoke_reason=reason)
    assert_rejected("auth_sessions_active_iff_not_ended", AuthSession, **values)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (SessionStatus.REVOKED, None),
        (SessionStatus.EXPIRED, RevokeReason.LOGOUT),
    ],
)
def test_session_revoke_reason_iff_revoked(user: User, status: str, reason: str | None) -> None:
    values = session_row(user, status=status, ended_at=NOW, revoke_reason=reason)
    assert_rejected("auth_sessions_revoked_iff_reason", AuthSession, **values)


def test_session_active_with_a_reason_is_rejected(user: User) -> None:
    values = session_row(user, revoke_reason=RevokeReason.LOGOUT)
    assert_rejected("auth_sessions_revoked_iff_reason", AuthSession, **values)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("status", "paused", "auth_sessions_status_valid"),
        ("revoke_reason", "whim", "auth_sessions_revoke_reason_valid"),
    ],
)
def test_session_closed_values(user: User, field: str, value: str, constraint: str) -> None:
    values = session_row(user, status=SessionStatus.REVOKED, ended_at=NOW)
    values["revoke_reason"] = RevokeReason.LOGOUT
    values[field] = value
    if field == "status":
        values["revoke_reason"] = None
    assert_rejected(constraint, AuthSession, **values)


def test_session_valid_terminal_rows(user: User) -> None:
    revoked = AuthSession.objects.create(
        **session_row(
            user, status=SessionStatus.REVOKED, ended_at=NOW, revoke_reason=RevokeReason.LOGOUT
        )
    )
    expired = AuthSession.objects.create(
        **session_row(user, status=SessionStatus.EXPIRED, ended_at=NOW + IDLE_LIFETIME)
    )
    assert {revoked.status, expired.status} == {"revoked", "expired"}


def test_session_user_is_protected(user: User) -> None:
    AuthSession.objects.create(**session_row(user))
    with pytest.raises(Exception, match="protected"), transaction.atomic():
        user.delete()


def test_RNF_IDA_05_no_ip_or_raw_user_agent_column() -> None:
    columns = sorted(field.column for field in AuthSession._meta.concrete_fields)
    assert columns == [
        "absolute_expires_at",
        "client_browser",
        "client_os",
        "created_at",
        "ended_at",
        "id",
        "idle_expires_at",
        "last_used_at",
        "revoke_reason",
        "status",
        "user_id",
    ]


def test_RNF_IDA_07_marks_are_timestamptz() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns"
            " WHERE table_name IN ('auth_sessions', 'refresh_tokens')"
            " AND column_name LIKE %s",
            ["%\\_at"],
        )
        types = {(table, column): kind for table, column, kind in cursor.fetchall()}
    assert len(types) == 7
    assert set(types.values()) == {"timestamp with time zone"}


def test_session_partial_indexes_exist() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'auth_sessions'"
        )
        indexes = dict(cursor.fetchall())
    assert "WHERE ((status)::text = 'active'::text)" in indexes["auth_sessions_active_user_idx"]
    assert "WHERE ((status)::text = 'active'::text)" in indexes["auth_sessions_active_idle_idx"]
    assert "WHERE (ended_at IS NOT NULL)" in indexes["auth_sessions_ended_at_idx"]


# --- refresh_tokens -----------------------------------------------------------------------------


def test_AC_IDA_14_column_cannot_hold_a_token_in_clear(user: User) -> None:
    session = AuthSession.objects.create(**session_row(user))
    raw = generate_refresh_token(session.id)
    with pytest.raises(DataError), transaction.atomic():
        RefreshToken.objects.create(session=session, token_hash=raw, issued_at=NOW)


@pytest.mark.parametrize(
    "stored",
    [
        ("rt1." + "A" * 64)[:64],
        "A" * 64,
        "g" * 64,
        "a" * 63,
        "",
    ],
)
def test_AC_IDA_14_database_refuses_anything_but_a_sha256(user: User, stored: str) -> None:
    session = AuthSession.objects.create(**session_row(user))
    assert_rejected(
        "refresh_tokens_hash_is_sha256_hex",
        RefreshToken,
        session=session,
        token_hash=stored,
        issued_at=NOW,
    )


def test_AC_IDA_14_token_hash_is_unique(user: User) -> None:
    first = new_token(AuthSession.objects.create(**session_row(user)))
    other = AuthSession.objects.create(**session_row(user))
    assert_rejected(
        "refresh_tokens_token_hash_key",
        RefreshToken,
        session=other,
        token_hash=first.token_hash,
        issued_at=NOW,
    )


def test_RN_IDA_10_one_live_token_per_session(user: User) -> None:
    session = AuthSession.objects.create(**session_row(user))
    first = new_token(session)
    with (
        pytest.raises(IntegrityError, match="refresh_tokens_one_live_per_session"),
        transaction.atomic(),
    ):
        new_token(session)

    RefreshToken.objects.filter(pk=first.pk).update(used_at=NOW)
    second = new_token(session)
    RefreshToken.objects.filter(pk=first.pk).update(replaced_by=second)
    assert RefreshToken.objects.filter(session=session, used_at__isnull=True).get() == second


def test_RN_IDA_10_two_sessions_each_have_their_live_token(user: User) -> None:
    for _ in range(2):
        new_token(AuthSession.objects.create(**session_row(user)))
    assert RefreshToken.objects.filter(used_at__isnull=True).count() == 2


def test_RN_IDA_10_replaced_only_if_used(user: User) -> None:
    session = AuthSession.objects.create(**session_row(user))
    successor = new_token(session, used_at=NOW)
    with (
        pytest.raises(IntegrityError, match="refresh_tokens_replaced_only_if_used"),
        transaction.atomic(),
    ):
        new_token(session, replaced_by=successor)


def test_RN_IDA_10_tokens_go_with_their_session(user: User) -> None:
    session = AuthSession.objects.create(**session_row(user))
    used = new_token(session, used_at=NOW)
    live = new_token(session)
    RefreshToken.objects.filter(pk=used.pk).update(replaced_by=live)
    session.delete()
    assert not RefreshToken.objects.exists()


def test_AC_IDA_14_str_shows_no_hash(user: User) -> None:
    token = new_token(AuthSession.objects.create(**session_row(user)))
    assert str(token) == str(token.pk)
    assert token.token_hash not in str(token)
