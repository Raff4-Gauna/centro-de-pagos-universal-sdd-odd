"""Two membership changes at once, and an accept against an exit (RN-TEN-14, design.md §4.2, §9).

AC-TEN-14: the only two owners demote, revoke or leave at the same time; at most one succeeds and
the organization keeps one owner. Every change takes the organization's mutex, so the second one
waits and decides on what the first one left: the actor revoked (``404 organization_not_found``),
demoted (``403``) or the last owner (``409 last_owner``). Threads with their own connection and
transaction (``transaction=True``), as in ``test_invitation_manage_race.py``: the first request
runs inside a transaction that stays open after its writes; the second starts, and the test waits
until PostgreSQL shows it blocked before releasing the first. Without the mutex both would see two
owners and both would succeed.

The accept against revoking the person who issued the invitation (Q-223): the real revocation, not
a stand-in. Whichever goes first, one transition from ``pending`` and at most one membership.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from apps.common.authz.roles import Role
from apps.identity.models import User
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.membership_setup import member
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

MEMBERSHIPS = "/api/memberships/"


class Request(threading.Thread):
    """One HTTP request in its own thread and connection; the response is kept."""

    def __init__(self, send: Callable[[], Any]) -> None:
        super().__init__(daemon=True)
        self.send = send
        self.response: Any = None

    def run(self) -> None:
        try:
            self.response = self.send()
        finally:
            connection.close()


def _call(method: str, path: str, user: User, org: Organization, body: Any = None) -> Any:
    headers = as_member(user, org.id)  # built here: the session of the thread's own connection
    data = None if body is None else json.dumps(body)
    return Client().generic(
        method, path, data=data or "", content_type="application/json", headers=headers
    )


Move = Callable[[User, Organization, Membership, Membership], Callable[[], Any]]


def _demote_other(user: User, org: Organization, mine: Membership, other: Membership) -> Any:
    return lambda: _call("PATCH", f"{MEMBERSHIPS}{other.pk}/", user, org, {"role": "admin"})


def _revoke_other(user: User, org: Organization, mine: Membership, other: Membership) -> Any:
    return lambda: _call("DELETE", f"{MEMBERSHIPS}{other.pk}/", user, org)


def _demote_self(user: User, org: Organization, mine: Membership, other: Membership) -> Any:
    return lambda: _call("PATCH", f"{MEMBERSHIPS}{mine.pk}/", user, org, {"role": "admin"})


def _leave(user: User, org: Organization, mine: Membership, other: Membership) -> Any:
    return lambda: _call("POST", f"{MEMBERSHIPS}me/leave/", user, org)


def _owners(org: Organization) -> int:
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=org)
    return rows.filter(role="owner", status="active").count()


@pytest.mark.parametrize(
    ("move", "refused"),
    [
        pytest.param(_demote_other, (403, "forbidden"), id="patch-vs-patch"),
        pytest.param(_revoke_other, (404, "organization_not_found"), id="revoke-vs-revoke"),
        pytest.param(_demote_self, (409, "last_owner"), id="both-demote-themselves"),
        pytest.param(_leave, (409, "last_owner"), id="both-leave"),
    ],
)
def test_AC_TEN_14_mutual_demotion_keeps_one_owner(move: Move, refused: tuple[int, str]) -> None:
    org = new_org("A")
    ana, ana_membership = member(org, Role.OWNER, "ana")
    bea, bea_membership = member(org, Role.OWNER, "bea")
    first_response: list[Any] = []
    first = Held(lambda: first_response.append(move(ana, org, ana_membership, bea_membership)()))
    second = Request(move(bea, org, bea_membership, ana_membership))

    first.start()
    try:
        assert first.reached.wait(PATIENCE), "the first request never finished its writes"
        second.start()
        assert wait_for_a_blocked_backend(), "the second request did not wait for the first"
    finally:
        first.go_on.set()
        first.join(PATIENCE)
    second.join(PATIENCE)

    assert first.error is None
    assert first_response[0].status_code in (200, 204), first_response[0].content
    response = second.response
    assert (response.status_code, response.json()["code"]) == refused
    assert _owners(org) == 1


def _revoke_the_inviter(owner: User, org: Organization, admin: Membership) -> Callable[[], None]:
    def send() -> None:
        response = _call("DELETE", f"{MEMBERSHIPS}{admin.pk}/", owner, org)
        assert response.status_code == 204, response.content

    return send


def _issued_by_admin(org: Organization) -> tuple[User, Membership, Invitation, str]:
    owner, _ = member(org, Role.OWNER)
    admin, admin_membership = member(org, Role.ADMIN)
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    rows.update(invited_by_user=admin, invited_by_operator="")
    return owner, admin_membership, invitation, token


def test_AC_TEN_36_revoking_the_inviter_first_then_accept_is_revoked() -> None:
    org = new_org("A")
    owner, admin, invitation, token = _issued_by_admin(org)
    ana = new_user("ana")
    revoking = Held(_revoke_the_inviter(owner, org, admin))
    accepting = Second(lambda: accept_by_token(token, invitee(ana)))

    revoking.start()
    try:
        assert revoking.reached.wait(PATIENCE), "the revocation never finished its writes"
        accepting.start()
        assert wait_for_a_blocked_backend(), "the accept did not wait for the revocation"
    finally:
        revoking.go_on.set()
        revoking.join(PATIENCE)
    accepting.join(PATIENCE)

    assert revoking.error is None
    assert isinstance(accepting.error, InvitationInvalid)
    assert accepting.error.problem_reason == "revoked"
    assert status_of(invitation) == InvitationStatus.REVOKED
    assert memberships(ana) == []


def test_AC_TEN_36_accept_first_then_revoking_the_inviter_keeps_it() -> None:
    org = new_org("A")
    owner, admin, invitation, token = _issued_by_admin(org)
    ana = new_user("ana")
    accepting = Held(lambda: accept_by_token(token, invitee(ana)))
    revoking = Second(_revoke_the_inviter(owner, org, admin))

    accepting.start()
    try:
        assert accepting.reached.wait(PATIENCE), "the accept never finished its writes"
        revoking.start()
        assert wait_for_a_blocked_backend(), "the revocation did not wait for the accept"
    finally:
        accepting.go_on.set()
        accepting.join(PATIENCE)
    revoking.join(PATIENCE)

    assert (accepting.error, revoking.error) == (None, None)
    assert status_of(invitation) == InvitationStatus.ACCEPTED  # no longer pending: not touched
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]
