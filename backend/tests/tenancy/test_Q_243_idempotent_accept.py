"""The token of an invitation the same person already accepted answers ``200`` (Q-243, T-TEN-39).

The first login accepts every valid invitation of the email (RN-IDA-06), so back on
``/invitacion`` the screen sends a token already used by that very person. The token route answers
the membership it gave, as the first time: no new membership, no new audit event, only an ``info``
log line with ids. Anyone else (another account, or a membership already ended) still gets
``used``, and so does the session route (T-TEN-16), which Q-243 does not cover.

The repeat is answered even past ``expires_at`` (AC-TEN-17, T-TEN-40): a closed state is decided
before the expiry, so an accepted invitation never turns ``expired``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.db import transaction
from django.test import Client
from django.utils import timezone

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
from apps.tenancy.services.invitation_port import TenancyInvitationPort
from tests.tenancy.api.probe import PLATFORM, bearer_of, new_org, new_user, revoke
from tests.tenancy.invitation_setup import invitee, issue, make_due, memberships, status_of

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


# --- AC-TEN-17: the repeat past ``expires_at`` (T-TEN-40) ----------------------------------------


@pytest.mark.parametrize(
    "late", [timedelta(0), timedelta(days=30)], ids=["at-expiry", "long-after"]
)
def test_AC_TEN_17_same_person_repeat_after_expiry_answers_the_membership(
    recorded: RecordingSink, late: timedelta
) -> None:
    """``now >= expires_at``: still the membership it gave, never ``expired``."""
    invitation, token = issue(new_org("A"), "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    first = accept_by_token(token, invitee(ana))
    recorded.clear()

    again = accept_by_token(token, invitee(ana), now=invitation.expires_at + late)

    assert again == first
    assert len(memberships(ana)) == 1
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert recorded.events == []


def test_AC_TEN_17_same_person_repeat_after_expiry_is_success(
    client: Client, recorded: RecordingSink, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through the route, once the invitation is past due: ``200`` with the current role."""
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.VIEWER)
    ana = new_user("ana")
    auth = bearer_of(ana)

    def post() -> Any:
        return client.post(ACCEPT, {"token": token}, content_type="application/json", headers=auth)

    first = post()
    membership_id = first.json()["membership_id"]
    Membership.objects.unscoped(PLATFORM).filter(pk=membership_id).update(role="operator")
    make_due(invitation)
    recorded.clear()
    capsys.readouterr()

    again = post()

    assert (first.status_code, again.status_code) == (200, 200)
    assert again["Cache-Control"] == "no-store"
    assert again.json() == {
        "organization": {"id": str(org.id), "name": "A"},
        "role": "operator",
        "membership_id": membership_id,
    }
    assert [(row[1], row[2]) for row in memberships(ana)] == [("operator", "active")]
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert recorded.events == []
    out = capsys.readouterr()
    logged = out.out + out.err + again.content.decode()
    assert "tenancy.invitation_refused" not in logged
    for secret in (token, "ana@hub.test"):
        assert secret not in logged


def test_Q_243_first_login_accepted_it_then_the_token_is_200(
    client: Client, recorded: RecordingSink
) -> None:
    """The real path: the login accepts through the SPEC-01 port, then ``/invitacion`` sends it."""
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test", Role.OPERATOR)
    ana = new_user("ana")
    now = timezone.now()
    with transaction.atomic():
        port = TenancyInvitationPort()
        port.accept_invitations(
            port.find_valid_invitations("ana@hub.test", now=now), ana.pk, now=now
        )
    [(_, _, _, source)] = memberships(ana)
    recorded.clear()

    response = client.post(
        ACCEPT, {"token": token}, content_type="application/json", headers=bearer_of(ana)
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["organization"]["id"], body["role"]) == (str(org.id), "operator")
    assert source == invitation.id
    assert len(memberships(ana)) == 1
    assert recorded.events == []
