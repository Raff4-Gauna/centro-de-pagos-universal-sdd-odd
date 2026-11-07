"""AC-IDA-15, AC-IDA-16 and AC-IDA-28 at decision level (RN-IDA-10, RN-IDA-11, ADR-0004 §3).

Pure, no database: the constraints and the refresh service that apply these rules are other tasks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.identity.domain.session_policy import (
    ABSOLUTE_LIFETIME,
    ACCESS_TOKEN_LIFETIME,
    IDLE_LIFETIME,
    REFRESH_GRACE,
    RefreshDecision,
    absolute_expiry,
    decide_refresh,
    idle_expiry,
    is_expired,
)

LOGIN = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)


def test_RN_IDA_11_lifetimes() -> None:
    lifetimes = (ACCESS_TOKEN_LIFETIME, IDLE_LIFETIME, ABSOLUTE_LIFETIME, REFRESH_GRACE)
    assert lifetimes == (
        timedelta(minutes=15),
        timedelta(days=7),
        timedelta(days=30),
        timedelta(seconds=30),
    )


def test_AC_IDA_16_idle_and_absolute_expiry() -> None:
    absolute = absolute_expiry(LOGIN)
    idle = idle_expiry(LOGIN, absolute)
    assert idle == LOGIN + timedelta(days=7)
    assert absolute == LOGIN + timedelta(days=30)

    assert not is_expired(idle_expires_at=idle, absolute_expires_at=absolute, now=idle - SECOND)
    # Exactly at the deadline is already expired: design.md §4.4 keeps a session alive on ``> now``.
    assert is_expired(idle_expires_at=idle, absolute_expires_at=absolute, now=idle)
    assert is_expired(idle_expires_at=idle, absolute_expires_at=absolute, now=idle + SECOND)

    # The absolute deadline wins on its own, even over an idle one that sits past it.
    late_idle = absolute + timedelta(days=1)
    assert is_expired(idle_expires_at=late_idle, absolute_expires_at=absolute, now=absolute)


def test_AC_IDA_16_absolute_never_extends() -> None:
    absolute = absolute_expiry(LOGIN)
    idle = idle_expiry(LOGIN, absolute)

    now = LOGIN
    for _day in range(29):  # Used every day: idle rolls forward, absolute stays put.
        now += timedelta(days=1)
        assert not is_expired(idle_expires_at=idle, absolute_expires_at=absolute, now=now)
        idle = idle_expiry(now, absolute)
        assert idle == min(now + timedelta(days=7), absolute)

    assert idle == absolute
    assert is_expired(idle_expires_at=idle, absolute_expires_at=absolute, now=absolute)
    assert idle_expiry(absolute + timedelta(days=5), absolute) == absolute


def test_RN_IDA_10_unused_token_rotates() -> None:
    decision = decide_refresh(used_at=None, successor_is_live=False, now=LOGIN)
    assert decision is RefreshDecision.ROTATE


@pytest.mark.parametrize(
    "elapsed",
    [timedelta(0), SECOND, timedelta(seconds=30), -SECOND],
    ids=["same_instant", "one_second", "window_edge", "instance_clock_behind"],
)
def test_AC_IDA_28_within_grace_is_not_reuse(elapsed: timedelta) -> None:
    decision = decide_refresh(used_at=LOGIN, successor_is_live=True, now=LOGIN + elapsed)
    assert decision is RefreshDecision.GRACE


@pytest.mark.parametrize(
    "elapsed",
    [timedelta(seconds=30, microseconds=1), timedelta(minutes=5), timedelta(days=2)],
    ids=["just_past_the_edge", "minutes_later", "days_later"],
)
def test_AC_IDA_15_outside_grace_is_reuse(elapsed: timedelta) -> None:
    decision = decide_refresh(used_at=LOGIN, successor_is_live=True, now=LOGIN + elapsed)
    assert decision is RefreshDecision.REUSE


def test_AC_IDA_15_within_grace_with_a_spent_successor_is_reuse() -> None:
    decision = decide_refresh(used_at=LOGIN, successor_is_live=False, now=LOGIN + SECOND)
    assert decision is RefreshDecision.REUSE
