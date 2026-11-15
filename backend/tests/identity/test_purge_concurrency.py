"""The purge against a refresh and a logout in flight (RN-IDA-25, RN-IDA-10, design.md §3.3, §4.5).

Lock order of the module: a refresh locks its token and then its session; a logout only the
session. The purge never holds a session while it waits for a token, and never waits for a session:
it skips the sessions someone holds (``SKIP LOCKED``) and leaves them for the next run. Two threads,
each with its own connection and transaction, as in ``test_revocation_concurrency.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.models import AuthSession, RefreshToken, RevokeReason, SessionStatus, User
from apps.identity.services import logout as logout_service
from apps.identity.services import purge as purge_service
from apps.identity.services.logout import logout
from apps.identity.services.purge import purge_auth_data
from apps.identity.services.session_lifecycle import OpenedSession, open_session, revoke
from tests.identity.fakes import install_ports
from tests.identity.test_refresh_concurrency import BFF, CREDENTIAL, PATIENCE, REFRESH
from tests.identity.test_revocation_concurrency import Hold, Worker, race

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
    return User.objects.create_user(google_sub="sub-purge-race", email="ana@example.com")


def refresh(refresh_token: str) -> Any:
    body = json.dumps({"refresh_token": refresh_token})
    return Client().post(REFRESH, body, content_type="application/json", headers=BFF)


def ended_long_ago(user: User) -> OpenedSession:
    ended = timezone.now() - timedelta(days=91)
    opened = open_session(user, now=ended - timedelta(days=1))
    assert revoke(opened.session.pk, reason=RevokeReason.LOGOUT, now=ended)
    return opened


def test_AC_IDA_38_refresh_of_a_purged_session_waits_and_finds_nothing(
    monkeypatch: pytest.MonkeyPatch, ana: User
) -> None:
    opened = ended_long_ago(ana)
    hold = Hold(monkeypatch, purge_service, "_lock_token_batch")
    purge, tab = (
        Worker(lambda: purge_auth_data(now=timezone.now())),
        Worker(lambda: refresh(opened.refresh_token)),
    )

    race(hold, purge, tab)

    assert purge.result.deleted_sessions == 1
    assert (tab.result.status_code, tab.result.json()["code"]) == (401, "token_invalid")
    assert not AuthSession.objects.filter(pk=opened.session.pk).exists()
    assert not RefreshToken.objects.filter(session_id=opened.session.pk).exists()


def test_AC_IDA_38_purge_skips_a_session_a_logout_holds(
    monkeypatch: pytest.MonkeyPatch, ana: User
) -> None:
    """The logout holds an idle session: the purge does not wait for it and does not expire it."""
    opened = open_session(ana, now=timezone.now() - timedelta(days=8))
    hold = Hold(monkeypatch, logout_service, "is_expired")
    tab = Worker(lambda: logout(refresh_token=opened.refresh_token, now=timezone.now()))
    hold.first = tab
    tab.start()
    try:
        assert hold.reached.wait(PATIENCE), "the logout never locked its session"
        purge = Worker(lambda: purge_auth_data(now=timezone.now()))
        purge.start()
        purge.join(PATIENCE)
        assert not purge.is_alive(), "the purge waited for the logout"
    finally:
        hold.go_on.set()
        tab.join(PATIENCE)

    assert (purge.error, tab.error) == (None, None)
    assert purge.result.expired_sessions == 0
    session = AuthSession.objects.get(pk=opened.session.pk)
    # The logout marked it itself, as it does with a session past its deadline.
    assert session.status == SessionStatus.EXPIRED
    assert purge_auth_data(now=timezone.now()).expired_sessions == 0
