"""The refresh under load (RN-IDA-10, RN-IDA-15; AC-IDA-20, AC-IDA-28; design.md §4.5, §7.6).

``POST /api/auth/bff/refresh/``, the real route of the public URLconf, on the wall clock.

AC-IDA-28, the race: two tabs refresh with the same token at once. Two threads, each with its own
client, connection and transaction, as two requests have. The first one is held inside the rotation,
with the token and the session locked ``FOR UPDATE`` and the token marked used, until PostgreSQL
shows the second one waiting on a lock: the order is forced, not hoped for. Then the first commits
and the second reads what it left, a token used an instant ago whose successor is the live one: the
grace window. ``transaction=True`` because the rows have to be committed for the other connection
to see them.

AC-IDA-20, the 31st refresh of one session in a minute is ``429``, walking the real rotation chain.
Throttle history lives in LocMemCache, cleared around each test.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.utils import timezone
from pydantic import SecretStr
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.secrets_format import hash_secret
from apps.identity.models import AuthSession, RefreshToken, SessionStatus, User
from apps.identity.services import refresh as refresh_service
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import verify_access_token
from tests.identity.fakes import Ports, install_ports

REFRESH = "/api/auth/bff/refresh/"
CREDENTIAL = "bff-value-of-the-concurrency-test"
BFF = {"X-Hub-Bff-Credential": CREDENTIAL, "X-Hub-Client-IP": "203.0.113.1"}
PATIENCE = 20.0

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def ports(settings: SettingsWrapper) -> Iterator[Ports]:
    settings.IDENTITY_BFF_CREDENTIALS = (SecretStr(CREDENTIAL),)
    cache.clear()
    yield install_ports(settings)
    cache.clear()


@pytest.fixture
def opened() -> OpenedSession:
    user = User.objects.create_user(google_sub="sub-refresh-race", email="ana@example.com")
    return open_session(user, now=timezone.now())


def post(client: Client, refresh_token: str) -> Any:
    body = json.dumps({"refresh_token": refresh_token})
    return client.post(REFRESH, body, content_type="application/json", headers=BFF)


class Tab(threading.Thread):
    """One browser tab: one refresh by the real route, on its own connection."""

    def __init__(self, refresh_token: str) -> None:
        super().__init__(daemon=True)
        self.refresh_token = refresh_token
        self.status: int | None = None
        self.body: dict[str, Any] = {}
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            response = post(Client(), self.refresh_token)
            self.status = response.status_code
            self.body = json.loads(response.content)
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            connection.close()


def wait_for_a_blocked_backend() -> bool:
    """True once another backend of this database waits on a lock (the second ``FOR UPDATE``)."""
    deadline = time.monotonic() + PATIENCE
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0]:
                return True
        time.sleep(0.02)
    return False


def run_race(monkeypatch: pytest.MonkeyPatch, first: Tab, second: Tab) -> None:
    """``first`` rotates and stops before its commit; ``second`` starts and blocks; then go."""
    rotating = threading.Event()
    go_on = threading.Event()
    issue: Callable[..., str] = refresh_service.issue_refresh_token

    def issue_and_hold(*args: Any, **kwargs: Any) -> str:
        raw = issue(*args, **kwargs)
        if threading.current_thread() is first:
            rotating.set()
            assert go_on.wait(PATIENCE)
        return raw

    monkeypatch.setattr(refresh_service, "issue_refresh_token", issue_and_hold)
    first.start()
    try:
        assert rotating.wait(PATIENCE), "the first refresh never reached the rotation"
        second.start()
        assert wait_for_a_blocked_backend(), "the second refresh did not wait for the first"
    finally:
        go_on.set()
        first.join(PATIENCE)
        if second.ident is not None:
            second.join(PATIENCE)
    assert not first.is_alive()
    assert not second.is_alive()


def test_AC_IDA_28_two_concurrent_refreshes(
    monkeypatch: pytest.MonkeyPatch, ports: Ports, opened: OpenedSession
) -> None:
    first, second = Tab(opened.refresh_token), Tab(opened.refresh_token)

    run_race(monkeypatch, first, second)

    assert (first.error, second.error) == (None, None)
    assert (first.status, second.status) == (200, 200)
    # The first rotates: a new pair. The second falls in the grace window: access only.
    rotated = first.body["refresh_token"]
    assert rotated not in (None, opened.refresh_token)
    assert second.body["refresh_token"] is None
    expected = (opened.session.user_id, opened.session.pk)
    for tab in (first, second):
        identity = verify_access_token(tab.body["access_token"])
        assert (identity.user_id, identity.session_id) == expected
    # The session goes on with one live token, the first one's: no second refresh was issued.
    session = AuthSession.objects.get(pk=opened.session.pk)
    assert (session.status, session.revoke_reason) == (SessionStatus.ACTIVE, None)
    tokens = RefreshToken.objects.filter(session=session)
    assert tokens.count() == 2
    assert tokens.filter(used_at__isnull=True).count() == 1
    # No reuse was seen, so nothing was audited (AC-IDA-15 stays for a real reuse).
    assert ports.audit.events == []
    # Both tabs keep working: the cookie the first tab now holds rotates again.
    monkeypatch.undo()
    assert post(Client(), rotated).json()["refresh_token"] not in (None, rotated)


def test_AC_IDA_20_31st_refresh_is_429(opened: OpenedSession) -> None:
    client = Client()
    token = opened.refresh_token
    for _ in range(30):
        response = post(client, token)
        assert response.status_code == 200
        token = response.json()["refresh_token"]

    response = post(client, token)

    assert response.status_code == 429
    assert response["Content-Type"] == "application/problem+json"
    assert json.loads(response.content)["code"] == "rate_limited"
    assert int(response["Retry-After"]) > 0
    # Refused before the view: the token it carried was not spent and the session is intact.
    live = RefreshToken.objects.get(session=opened.session, used_at__isnull=True)
    assert live.token_hash == hash_secret(token)
    assert AuthSession.objects.get(pk=opened.session.pk).status == SessionStatus.ACTIVE
    cache.clear()
    assert post(client, token).status_code == 200
