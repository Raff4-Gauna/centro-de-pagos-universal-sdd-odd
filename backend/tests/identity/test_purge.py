"""The periodic purge (RF-IDA-10, RN-IDA-25, Q-118, design.md §3.3): ``services/purge.py``.

One run, at ``now``: active sessions past their idle deadline become ``expired`` (ended at that
deadline), expired login attempts are deleted, and every session that ended more than 90 days
before ``now`` is deleted with all its refresh tokens. Users are never deleted. Each step works in
batches; ``batch_size`` is lowered here so that a few rows cross several batches.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

from apps.common.domain.redaction import is_secret_key
from apps.identity.domain.secrets_format import hash_secret
from apps.identity.models import (
    AuthSession,
    LoginAttempt,
    RefreshToken,
    RevokeReason,
    SessionStatus,
    User,
)
from apps.identity.services import purge as purge_service
from apps.identity.services.purge import PurgeResult, purge_auth_data
from apps.identity.services.session_lifecycle import (
    expire,
    issue_refresh_token,
    open_session,
    revoke,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def ana() -> User:
    return User.objects.create_user(google_sub="sub-purge", email="ana@example.com")


def rotate(session: AuthSession, *, at: datetime) -> None:
    """One refresh as ``services/refresh.py`` writes it: the live token used, a successor."""
    live = RefreshToken.objects.get(session=session, used_at__isnull=True)
    live.used_at = at
    live.save(update_fields=["used_at"])
    raw = issue_refresh_token(session, now=at)
    live.replaced_by = RefreshToken.objects.get(token_hash=hash_secret(raw))
    live.save(update_fields=["replaced_by"])


def ended_days_ago(
    user: User, days: float, *, how: str = "revoked", tokens: int = 3
) -> AuthSession:
    """A session with ``tokens`` refresh tokens in a chain that ended ``days`` before ``NOW``."""
    ended = NOW - timedelta(days=days)
    started = ended - timedelta(days=1)
    session = open_session(user, now=started).session
    for hour in range(1, tokens):
        rotate(session, at=started + timedelta(hours=hour))
    if how == "revoked":
        assert revoke(session.pk, reason=RevokeReason.LOGOUT, now=ended)
    else:
        AuthSession.objects.filter(pk=session.pk).update(idle_expires_at=ended)
        assert expire(session.pk, now=ended)
    return AuthSession.objects.get(pk=session.pk)


def login_attempt(*, created_at: datetime, name: str) -> LoginAttempt:
    digest = hashlib.sha256(name.encode()).hexdigest()
    return LoginAttempt.objects.create(
        state_hash=digest,
        nonce_hash=digest,
        binding_hash=digest,
        code_verifier="v" * 43,
        return_path="/",
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=10),
    )


def exists(session: AuthSession) -> bool:
    return AuthSession.objects.filter(pk=session.pk).exists()


def token_count(session: AuthSession) -> int:
    return RefreshToken.objects.filter(session_id=session.pk).count()


def test_AC_IDA_38_91_days_purged_89_kept(ana: User) -> None:
    old_revoked = ended_days_ago(ana, 91)
    old_expired = ended_days_ago(ana, 91, how="expired")
    young_revoked = ended_days_ago(ana, 89)
    young_expired = ended_days_ago(ana, 89, how="expired")

    result = purge_auth_data(now=NOW)

    assert not exists(old_revoked)
    assert not exists(old_expired)
    assert token_count(old_revoked) == token_count(old_expired) == 0
    assert exists(young_revoked)
    assert exists(young_expired)
    assert token_count(young_revoked) == token_count(young_expired) == 3
    assert (result.deleted_sessions, result.deleted_refresh_tokens) == (2, 6)


def test_AC_IDA_38_exactly_90_days_is_kept(ana: User) -> None:
    on_the_edge = ended_days_ago(ana, 90)

    purge_auth_data(now=NOW)

    assert exists(on_the_edge)
    # The token step uses the same strict cutoff: at exactly 90 days the chain stays whole.
    assert token_count(on_the_edge) == 3


def test_AC_IDA_38_user_is_never_deleted(ana: User) -> None:
    ended_days_ago(ana, 200)
    gone = User.objects.create_user(google_sub="sub-gone", email="gone@example.com")
    ended_days_ago(gone, 120, how="expired")
    User.objects.filter(pk=gone.pk).update(
        is_active=False, deactivated_at=NOW - timedelta(days=150)
    )

    purge_auth_data(now=NOW)

    assert AuthSession.objects.count() == 0
    assert set(User.objects.values_list("pk", flat=True)) == {ana.pk, gone.pk}


def test_AC_IDA_38_active_sessions_past_idle_deadline_become_expired(ana: User) -> None:
    alive = open_session(ana, now=NOW - timedelta(days=1)).session
    idle = open_session(ana, now=NOW - timedelta(days=8)).session
    # Idle so long ago that it is also past the retention: expired and purged in the same run.
    forgotten = open_session(ana, now=NOW - timedelta(days=120)).session

    result = purge_auth_data(now=NOW)

    assert AuthSession.objects.get(pk=alive.pk).status == SessionStatus.ACTIVE
    idle.refresh_from_db()
    assert (idle.status, idle.ended_at) == (SessionStatus.EXPIRED, idle.idle_expires_at)
    assert idle.revoke_reason is None
    assert token_count(idle) == 1
    assert not exists(forgotten)
    assert result.expired_sessions == 2
    assert result.active_sessions == 1


def test_AC_IDA_38_expired_login_attempts_are_deleted(ana: User) -> None:
    stale = login_attempt(created_at=NOW - timedelta(minutes=11), name="stale")
    live = login_attempt(created_at=NOW - timedelta(minutes=9), name="live")

    result = purge_auth_data(now=NOW)

    assert not LoginAttempt.objects.filter(pk=stale.pk).exists()
    assert LoginAttempt.objects.filter(pk=live.pk).exists()
    assert result.deleted_login_attempts == 1


def test_purge_is_idempotent(ana: User) -> None:
    ended_days_ago(ana, 91)
    kept = ended_days_ago(ana, 10)
    open_session(ana, now=NOW - timedelta(days=8))
    login_attempt(created_at=NOW - timedelta(hours=1), name="stale")
    purge_auth_data(now=NOW)
    before = sorted(AuthSession.objects.values_list("pk", "status", "ended_at"))

    again = purge_auth_data(now=NOW)

    assert again == PurgeResult(
        expired_sessions=0,
        deleted_login_attempts=0,
        deleted_refresh_tokens=0,
        deleted_sessions=0,
        active_sessions=0,
    )
    assert sorted(AuthSession.objects.values_list("pk", "status", "ended_at")) == before
    assert exists(kept)


def test_purge_crosses_batches_and_splits_token_chains(ana: User) -> None:
    """Five sessions of three tokens each, two rows per batch: chains are cut between batches."""
    old = [ended_days_ago(ana, 91 + n) for n in range(5)]
    for n in range(5):
        open_session(ana, now=NOW - timedelta(days=8, hours=n))
    for n in range(5):
        login_attempt(created_at=NOW - timedelta(hours=n + 1), name=f"stale-{n}")

    result = purge_auth_data(now=NOW, batch_size=2)

    assert not any(exists(session) for session in old)
    assert result == PurgeResult(
        expired_sessions=5,
        deleted_login_attempts=5,
        deleted_refresh_tokens=15,
        deleted_sessions=5,
        active_sessions=0,
    )
    assert AuthSession.objects.filter(status=SessionStatus.ACTIVE).count() == 0


def test_purge_stops_after_the_batch_limit(ana: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """A backlog bigger than one run is left for the next one: each run is bounded."""
    monkeypatch.setattr(purge_service, "MAX_BATCHES", 2)
    for n in range(5):
        open_session(ana, now=NOW - timedelta(days=8, hours=n))

    first = purge_auth_data(now=NOW, batch_size=2)
    second = purge_auth_data(now=NOW, batch_size=2)

    assert (first.expired_sessions, second.expired_sessions) == (4, 1)


def test_RNF_IDA_04_purge_logs_the_active_sessions_gauge(ana: User) -> None:
    open_session(ana, now=NOW - timedelta(hours=1))
    open_session(ana, now=NOW - timedelta(hours=2))
    open_session(ana, now=NOW - timedelta(days=8))
    old = ended_days_ago(ana, 91)

    with capture_logs() as logs:
        purge_auth_data(now=NOW)

    gauges = [log for log in logs if log["event"] == purge_service.ACTIVE_GAUGE_EVENT]
    assert gauges == [{"event": "auth.sessions_active", "value": 2, "log_level": "info"}]
    [summary] = [log for log in logs if log["event"] == purge_service.PURGED_EVENT]
    counts = {key: value for key, value in summary.items() if key not in {"event", "log_level"}}
    assert counts == {"expired": 1, "login_attempts": 0, "refresh_rows": 3, "ended": 1}
    # The redaction would blank a key holding "session" or "token": none of these does.
    assert not any(is_secret_key(key) for key in counts)
    assert str(old.pk) not in str(logs)
