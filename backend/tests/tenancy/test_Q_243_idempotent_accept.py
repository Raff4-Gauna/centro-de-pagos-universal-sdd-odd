"""The token of an invitation the same person already accepted answers ``200`` (Q-243, T-TEN-39).

The first login accepts every valid invitation of the email (RN-IDA-06), so back on
``/invitacion`` the screen sends a token already used by that very person. The token route answers
the membership it gave, as the first time: no new membership, no new audit event, only an ``info``
log line with ids. Anyone else (another account, or a membership already ended) still gets
``used``, and so does the session route (T-TEN-16), which Q-243 does not cover.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.test import Client

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.errors import OrganizationSuspended
from apps.tenancy.domain.invitations import InvalidReason, InvitationStatus
from apps.tenancy.models import Membership, Organization
from apps.tenancy.services.invitation_accept import (
    InvitationInvalid,
    accept_by_token,
    accept_from_session,
)
from tests.tenancy.api.probe import PLATFORM, bearer_of, new_org, new_user, revoke
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of

pytestmark = pytest.mark.django_db

ACCEPT = "/api/invitations/accept/"


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def used(call: Callable[[], object]) -> None:
    with pytest.raises(InvitationInvalid) as raised:
        call()
    assert raised.value.problem_reason == InvalidReason.USED.value


def test_Q_243_same_person_repeat_answers_the_same_membership(
    recorded: RecordingSink, capsys: pytest.CaptureFixture[str]
) -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    first = accept_by_token(token, invitee(ana))
    recorded.clear()
    capsys.readouterr()

    again = accept_by_token(token, invitee(ana))

    assert again == first
    assert len(memberships(ana)) == 1
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert recorded.events == []  # nothing changed: nothing to audit
    out = capsys.readouterr()
    logged = out.out + out.err
    assert "tenancy.invitation_accept_repeated" in logged
    assert "tenancy.invitation_refused" not in logged
    assert "tenancy.invitation_accepted" not in logged
    for secret in (token, "ana@hub.test"):
        assert secret not in logged


def test_Q_243_repeat_answers_the_current_role() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    first = accept_by_token(token, invitee(ana))
    Membership.objects.unscoped(PLATFORM).filter(pk=first.membership_id).update(role="admin")

    again = accept_by_token(token, invitee(ana))

    assert (again.membership_id, again.role) == (first.membership_id, Role.ADMIN)


def test_Q_243_another_account_with_the_same_email_is_used(recorded: RecordingSink) -> None:
    """The address passed to another account: the token is not theirs to repeat."""
    _, token = issue(new_org("A"), "ana@hub.test")
    ana, beto = new_user("ana"), new_user("beto")
    accept_by_token(token, invitee(ana))
    recorded.clear()

    used(lambda: accept_by_token(token, invitee(beto, "ana@hub.test")))

    assert memberships(beto) == []
    assert recorded.events == []


def test_Q_243_repeat_after_the_membership_ended_is_used() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    ana = new_user("ana")
    first = accept_by_token(token, invitee(ana))
    revoke(org, Membership.objects.unscoped(PLATFORM).get(pk=first.membership_id))

    used(lambda: accept_by_token(token, invitee(ana)))

    assert [row[2] for row in memberships(ana)] == ["revoked"]


def test_Q_243_repeat_with_the_organization_suspended_is_409() -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    ana = new_user("ana")
    accept_by_token(token, invitee(ana))
    Organization.objects.unscoped(PLATFORM).filter(pk=org.pk).update(
        status=OrgStatus.SUSPENDED.value
    )

    with pytest.raises(OrganizationSuspended):
        accept_by_token(token, invitee(ana))


def test_Q_243_the_session_route_still_answers_used() -> None:
    """Q-243 covers the token route only; the session one lists ``pending`` invitations."""
    invitation, token = issue(new_org("A"), "ana@hub.test")
    ana = new_user("ana")
    accept_by_token(token, invitee(ana))

    used(lambda: accept_from_session(invitation.id, invitee(ana)))

    assert len(memberships(ana)) == 1


def test_Q_243_route_repeat_is_200_with_the_same_body(client: Client) -> None:
    _, token = issue(new_org("A"), "ana@hub.test", Role.VIEWER)
    ana = new_user("ana")
    auth = bearer_of(ana)

    def post() -> Any:
        return client.post(ACCEPT, {"token": token}, content_type="application/json", headers=auth)

    first, again = post(), post()

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert again["Cache-Control"] == "no-store"
    assert token not in again.content.decode()
    assert len(memberships(ana)) == 1
