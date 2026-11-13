"""AC-IDA-02, the race (design.md §4.3): two valid callbacks of the same invited person at once.

Two threads, each with its own connection and its own transaction, as two requests have. The first
one is held inside ``find_valid_invitations``, after its ``INSERT``, until PostgreSQL shows the
second one waiting on a lock: the order is forced, not hoped for. ``transaction=True`` because the
rows have to be committed for the other connection to see them.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from uuid import UUID

import pytest
from django.db import connection, transaction
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.audit_events import IdentityAuditAction
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.login_rules import LoginRejectedError, evaluate_identity
from apps.identity.models import AuthSession, SessionStatus, User
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.user_provisioning import provision_user
from tests.identity.fakes import InvitationStatus, Ports, install_ports

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SUB = "1000000000000000000001"
OTHER_SUB = "1000000000000000000002"
PATIENCE = 20.0

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


class Callback(threading.Thread):
    """Step 7 of one callback: provision the user and open its session in one transaction."""

    def __init__(self, sub: str) -> None:
        super().__init__(daemon=True)
        self.sub = sub
        self.user_id: UUID | None = None
        self.error: BaseException | None = None

    def run(self) -> None:
        identity = evaluate_identity(
            sub=self.sub, email="ana@x.com", email_verified=True, name="Ana", picture=""
        )
        try:
            with transaction.atomic():
                user = provision_user(identity, now=NOW)
                open_session(user, now=NOW)
            self.user_id = user.pk
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            connection.close()


def wait_for_a_blocked_backend() -> bool:
    """True once another backend of this database waits on a lock (the second ``INSERT``)."""
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


def run_race(ports: Ports, first: Callback, second: Callback) -> None:
    """``first`` inserts and stops before its commit; ``second`` starts and blocks; then go."""
    first_inserted = threading.Event()
    go_on = threading.Event()

    def hold() -> None:
        first_inserted.set()
        assert go_on.wait(PATIENCE)

    ports.invitations.on_find = hold
    first.start()
    try:
        assert first_inserted.wait(PATIENCE), "the first callback never reached the invitations"
        second.start()
        assert wait_for_a_blocked_backend(), "the second INSERT did not wait for the first"
    finally:
        go_on.set()
        first.join(PATIENCE)
        if second.ident is not None:
            second.join(PATIENCE)
    assert not first.is_alive()
    assert not second.is_alive()


def test_AC_IDA_02_concurrent_callbacks_one_user(ports: Ports) -> None:
    invitation = ports.invitations.invite("ana@x.com", now=NOW)
    first, second = Callback(SUB), Callback(SUB)

    run_race(ports, first, second)

    # Neither answers 500: both end with the same user and a session each.
    assert (first.error, second.error) == (None, None)
    [user] = User.objects.all()
    assert first.user_id == second.user_id == user.pk
    assert AuthSession.objects.filter(user=user, status=SessionStatus.ACTIVE).count() == 2
    # The loser went through case (a): it never asked for invitations (Q-121).
    assert ports.invitations.calls == ["find_valid_invitations", "accept_invitations"]
    assert (invitation.status, invitation.accepted_by) == (InvitationStatus.ACCEPTED, user.pk)
    assert [event.action for event in ports.audit.events] == [
        IdentityAuditAction.USER_CREATED_BY_INVITATION
    ]


def test_AC_IDA_02_concurrent_callbacks_of_two_subs_with_one_email_is_conflict(
    ports: Ports,
) -> None:
    # §4.3, last line: the unique index that refuses is the email's, with another ``sub``.
    ports.invitations.invite("ana@x.com", now=NOW)
    first, second = Callback(SUB), Callback(OTHER_SUB)

    run_race(ports, first, second)

    assert first.error is None
    assert isinstance(second.error, LoginRejectedError)
    assert second.error.code == IdentityErrorCode.IDENTITY_CONFLICT
    assert list(User.objects.values_list("google_sub", flat=True)) == [SUB]
    assert AuthSession.objects.count() == 1
    assert ports.invitations.calls == ["find_valid_invitations", "accept_invitations"]
