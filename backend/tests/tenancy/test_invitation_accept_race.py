"""The same token accepted twice at once: one membership (AC-TEN-17, design.md §4.4, Q-243).

Threads with their own connection and transaction (``transaction=True``), as in
``test_AC_TEN_28_lock_races.py``. In the forced order the first accept stops inside its transaction
after creating the membership; the second one starts, and the test waits until PostgreSQL shows it
blocked on a lock (the organization's mutex) before letting the first commit. Then the second reads
``accepted`` under the lock: by the same person, so it answers the same membership (Q-243); by
another account it is ``used``. The free-for-all variant only asserts what must hold in any order.
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
from apps.tenancy.models import Membership
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.probe import PLATFORM, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def accept(token: str, user: User, email: str | None = None) -> Callable[[], Any]:
    return lambda: accept_by_token(token, invitee(user, email))


def race(token: str, first_user: User, second_user: User, email: str) -> tuple[Held, Second]:
    first = Held(accept(token, first_user))
    second = Second(accept(token, second_user, email))
    first.start()
    try:
        assert first.reached.wait(PATIENCE), "the first accept never finished its writes"
        second.start()
        assert wait_for_a_blocked_backend(), "the second accept did not wait for the first"
    finally:
        first.go_on.set()
        first.join(PATIENCE)
    second.join(PATIENCE)
    return first, second


def test_Q_243_double_accept_in_parallel_by_the_same_person() -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")

    first, second = race(token, ana, ana, "ana@hub.test")

    assert (first.error, second.error) == (None, None)
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]
    assert status_of(invitation) == InvitationStatus.ACCEPTED


def test_AC_TEN_17_double_accept_in_parallel_by_another_account() -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana, beto = new_user("ana"), new_user("beto")

    first, second = race(token, ana, beto, "ana@hub.test")

    assert first.error is None
    assert isinstance(second.error, InvitationInvalid)
    assert second.error.problem_reason == "used"
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]
    assert memberships(beto) == []
    assert status_of(invitation) == InvitationStatus.ACCEPTED


def test_AC_TEN_17_many_accepts_at_once_give_one_membership() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    ana = new_user("ana")
    start = threading.Barrier(4)
    outcomes: list[object] = []

    def run() -> None:
        try:
            start.wait(PATIENCE)
            with transaction.atomic():
                outcomes.append(accept_by_token(token, invitee(ana)).membership_id)
        except InvitationInvalid as refused:
            outcomes.append(refused.problem_reason)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(PATIENCE)

    [membership] = Membership.objects.unscoped(PLATFORM).filter(user=ana)
    assert outcomes == [membership.pk] * 4  # the same person: every one answers it (Q-243)
