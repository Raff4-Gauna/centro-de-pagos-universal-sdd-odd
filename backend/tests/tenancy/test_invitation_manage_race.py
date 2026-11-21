"""Accepting and revoking or resending the same invitation at once (spec §12, design.md §4.2, §9).

One transition from ``pending`` and at most one membership (RN-TEN-07, RN-TEN-12): both take the
organization's mutex, so the second one waits and decides on what the first one left. Threads with
their own connection and transaction (``transaction=True``), as in
``test_invitation_accept_race.py``: the first one stops inside its transaction after its writes;
the second starts, and the test waits until PostgreSQL shows it blocked before releasing the first.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.membership_setup import member
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

JSON = "application/json"


class Post(threading.Thread):
    def __init__(self, path: str, headers: dict[str, str]) -> None:
        super().__init__(daemon=True)
        self.path, self.headers = path, headers
        self.response: Any = None

    def run(self) -> None:
        try:
            self.response = Client().post(self.path, content_type=JSON, headers=self.headers)
        finally:
            connection.close()


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_37_accept_first_then_manage_is_invalid_transition(action: str) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    accepting = Held(lambda: accept_by_token(token, invitee(ana)))
    managing = Post(f"/api/invitations/{invitation.pk}/{action}/", as_member(owner, org.id))

    accepting.start()
    try:
        assert accepting.reached.wait(PATIENCE), "the accept never finished its writes"
        managing.start()
        assert wait_for_a_blocked_backend(), "the second request did not wait for the accept"
    finally:
        accepting.go_on.set()
        accepting.join(PATIENCE)
    managing.join(PATIENCE)

    assert accepting.error is None
    response = managing.response
    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert Invitation.objects.unscoped(PLATFORM).filter(organization=org).count() == 1
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_26_manage_first_then_accept_is_revoked(action: str) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    headers = as_member(owner, org.id)
    path = f"/api/invitations/{invitation.pk}/{action}/"

    def manage() -> None:
        response = Client().post(path, content_type=JSON, headers=headers)
        assert response.status_code in (200, 201), response.content

    managing = Held(manage)
    accepting = Second(lambda: accept_by_token(token, invitee(ana)))

    managing.start()
    try:
        assert managing.reached.wait(PATIENCE), "the request never finished its writes"
        accepting.start()
        assert wait_for_a_blocked_backend(), "the accept did not wait for the request"
    finally:
        managing.go_on.set()
        managing.join(PATIENCE)
    accepting.join(PATIENCE)

    assert managing.error is None
    assert isinstance(accepting.error, InvitationInvalid)
    assert accepting.error.problem_reason == "revoked"
    assert status_of(invitation) == InvitationStatus.REVOKED
    assert memberships(ana) == []
