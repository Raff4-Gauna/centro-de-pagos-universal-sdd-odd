"""The same token accepted twice at once: one membership, one ``used`` (AC-TEN-17, design.md §4.4).

Threads with their own connection and transaction (``transaction=True``), as in
``test_AC_TEN_28_lock_races.py``. In the forced order the first accept stops inside its transaction
after creating the membership; the second one starts, and the test waits until PostgreSQL shows it
blocked on a lock (the organization's mutex) before letting the first commit. Then the second reads
``accepted`` under the lock. The free-for-all variant only asserts what must hold in any order.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection, transaction

from apps.common.authz.roles import Role
from apps.identity.models import User
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.probe import new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def accept(token: str, user: User) -> Callable[[], Any]:
    return lambda: accept_by_token(token, invitee(user))


def test_AC_TEN_17_double_accept_in_parallel() -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    first, second = Held(accept(token, ana)), Second(accept(token, ana))

    first.start()
    try:
        assert first.reached.wait(PATIENCE), "the first accept never finished its writes"
        second.start()
        assert wait_for_a_blocked_backend(), "the second accept did not wait for the first"
    finally:
        first.go_on.set()
        first.join(PATIENCE)
    second.join(PATIENCE)

    assert first.error is None
    assert isinstance(second.error, InvitationInvalid)
    assert second.error.problem_reason == "used"
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]
    assert status_of(invitation) == InvitationStatus.ACCEPTED


def test_AC_TEN_17_many_accepts_at_once_give_one_membership() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    ana = new_user("ana")
    start = threading.Barrier(4)
    outcomes: list[str] = []

    def run() -> None:
        try:
            start.wait(PATIENCE)
            with transaction.atomic():
                accept_by_token(token, invitee(ana))
            outcomes.append("accepted")
        except InvitationInvalid as refused:
            outcomes.append(refused.problem_reason)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(PATIENCE)

    assert sorted(outcomes) == ["accepted", "used", "used", "used"]
    assert len(memberships(ana)) == 1
