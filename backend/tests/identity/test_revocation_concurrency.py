"""Revoking sessions while one of them refreshes (RN-IDA-07, RN-IDA-10, RN-IDA-20; design.md §4.5).

"Cerrar las demás" (``revoke_other_sessions``, AC-IDA-33) and ``deactivate_user`` (AC-IDA-27) each
race a refresh of a session they end, in both orders. Two threads, each with its own connection and
transaction, as in ``test_refresh_concurrency.py``: the first one is held inside its transaction
with the session row locked until PostgreSQL shows the second waiting on a lock, so the order is
forced, not hoped for. ``transaction=True``: the other connection has to see committed rows.

What must hold either way: neither deadlocks nor fails, the session ends ``revoked``, and nothing
the refresh hands out still works. If the refresh wins, its new pair dies with the session; if the
revocation wins, the refresh answers ``401 session_revoked`` and issues nothing.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User
from apps.identity.services import refresh as refresh_service
from apps.identity.services import sessions as sessions_service
from apps.identity.services import user_status as user_status_service
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.services.user_status import PlatformOperator, UserTarget, deactivate_user
from tests.identity.fakes import install_ports
from tests.identity.test_refresh_concurrency import (
    BFF,
    CREDENTIAL,
    PATIENCE,
    REFRESH,
    wait_for_a_blocked_backend,
)

ME = "/api/me/"
OPERATOR = PlatformOperator(name="ops", os_user="deploy")

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def bff(settings: SettingsWrapper) -> Iterator[None]:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    install_ports(settings)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana() -> User:
    return User.objects.create_user(google_sub="sub-revocation-race", email="ana@example.com")


def refresh(refresh_token: str) -> Any:
    body = json.dumps({"refresh_token": refresh_token})
    return Client().post(REFRESH, body, content_type="application/json", headers=BFF)


class Worker(threading.Thread):
    """One request or command on its own connection; its result or error is handed to the test."""

    def __init__(self, action: Callable[[], Any]) -> None:
        super().__init__(daemon=True)
        self.action = action
        self.result: Any = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self.action()
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            connection.close()


class Hold:
    """Stops ``first`` right after ``module.name`` returns, inside its transaction."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> None:
        self.reached = threading.Event()
        self.go_on = threading.Event()
        self.first: Worker | None = None
        original: Callable[..., Any] = getattr(module, name)

        def held(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            if threading.current_thread() is self.first and not self.reached.is_set():
                self.reached.set()
                assert self.go_on.wait(PATIENCE)
            return result

        monkeypatch.setattr(module, name, held)


def race(hold: Hold, first: Worker, second: Worker) -> None:
    """``first`` locks and waits; ``second`` starts and blocks on that lock; then both finish."""
    hold.first = first
    first.start()
    try:
        assert hold.reached.wait(PATIENCE), "the first one never reached its hold point"
        second.start()
        assert wait_for_a_blocked_backend(), "the second one did not wait for the first"
    finally:
        hold.go_on.set()
        first.join(PATIENCE)
        if second.ident is not None:
            second.join(PATIENCE)
    assert not first.is_alive()
    assert not second.is_alive()
    assert (first.error, second.error) == (None, None)


def assert_dead(opened: OpenedSession, reason: RevokeReason, refreshed: Any) -> None:
    """The session ended for ``reason`` and no token the refresh handed out works."""
    session = AuthSession.objects.get(pk=opened.session.pk)
    assert (session.status, session.revoke_reason) == (SessionStatus.REVOKED, reason)
    if refreshed.status_code == 200:
        body = refreshed.json()
        assert refresh(body["refresh_token"]).json()["code"] == "session_revoked"
        bearer = {"Authorization": f"Bearer {body['access_token']}"}
        assert Client().get(ME, headers=bearer).json()["code"] == "session_revoked"
    else:
        assert (refreshed.status_code, refreshed.json()["code"]) == (401, "session_revoked")
        # Nothing was issued: the one token is the original, unused.
        assert RefreshToken.objects.filter(session_id=session.pk).count() == 1
    assert refresh(opened.refresh_token).status_code == 401


def revoke_others(user: User, keep: UUID) -> Callable[[], int]:
    return lambda: sessions_service.revoke_other_sessions(
        user_id=user.pk, current_session_id=keep, now=timezone.now()
    )


def deactivate(user: User) -> Callable[[], Any]:
    return lambda: deactivate_user(
        target=UserTarget(user_id=user.pk), operator=OPERATOR, note=None, now=timezone.now()
    )


def test_AC_IDA_33_revoke_others_waits_for_a_refresh(
    monkeypatch: pytest.MonkeyPatch, ana: User
) -> None:
    current = open_session(ana, now=timezone.now())
    other = open_session(ana, now=timezone.now())
    hold = Hold(monkeypatch, refresh_service, "issue_refresh_token")
    tab, command = (
        Worker(lambda: refresh(other.refresh_token)),
        Worker(revoke_others(ana, current.session.pk)),
    )

    race(hold, tab, command)

    assert tab.result.status_code == 200
    assert command.result == 1
    assert_dead(other, RevokeReason.REVOKED_OTHERS, tab.result)
    assert AuthSession.objects.get(pk=current.session.pk).status == SessionStatus.ACTIVE


def test_AC_IDA_33_refresh_waits_for_revoke_others(
    monkeypatch: pytest.MonkeyPatch, ana: User
) -> None:
    current = open_session(ana, now=timezone.now())
    other = open_session(ana, now=timezone.now())
    hold = Hold(monkeypatch, sessions_service, "revoke")
    command, tab = (
        Worker(revoke_others(ana, current.session.pk)),
        Worker(lambda: refresh(other.refresh_token)),
    )

    race(hold, command, tab)

    assert command.result == 1
    assert_dead(other, RevokeReason.REVOKED_OTHERS, tab.result)


def test_AC_IDA_27_deactivate_waits_for_a_refresh(
    monkeypatch: pytest.MonkeyPatch, ana: User
) -> None:
    opened = open_session(ana, now=timezone.now())
    hold = Hold(monkeypatch, refresh_service, "issue_refresh_token")
    tab, command = Worker(lambda: refresh(opened.refresh_token)), Worker(deactivate(ana))

    race(hold, tab, command)

    assert tab.result.status_code == 200
    assert command.result.revoked_sessions == 1
    assert_dead(opened, RevokeReason.USER_DEACTIVATED, tab.result)


def test_AC_IDA_27_refresh_waits_for_deactivate(monkeypatch: pytest.MonkeyPatch, ana: User) -> None:
    opened = open_session(ana, now=timezone.now())
    hold = Hold(monkeypatch, user_status_service, "revoke")
    command, tab = Worker(deactivate(ana)), Worker(lambda: refresh(opened.refresh_token))

    race(hold, command, tab)

    assert command.result.revoked_sessions == 1
    assert_dead(opened, RevokeReason.USER_DEACTIVATED, tab.result)
