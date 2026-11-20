"""``GET /api/invitations/mine/`` and ``POST /api/invitations/{id}/accept/`` (design.md §4.4, §6).

AC-TEN-39 (Q-121, Q-124), AC-TEN-28 for the accept from the session, RN-TEN-11. Both routes are
exempt from the active organization: no ``X-Organization-Id`` is needed and one is ignored. The
list carries no token and no inviter; accepting by id answers another person's invitation exactly
like a missing one. What needs committed transactions (the audit of a foreign attempt, the expiry,
the races) lives in ``tests/tenancy/test_my_invitations_commit.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
import yaml
from django.test import Client
from django.utils import timezone

from apps.common.audit.port import AuditActor, AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.models import User
from apps.tenancy.domain.invitations import InvitationStatus, hash_token
from apps.tenancy.models import Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import HEADER, PLATFORM, add_member, bearer_of, new_org, new_user
from tests.tenancy.invitation_setup import issue, make_due, memberships, set_status, status_of

pytestmark = pytest.mark.django_db

MINE = "/api/invitations/mine/"
# Fields of a problem that differ between two requests: the request and the URL it named.
VARYING = ("request_id", "instance")


def accept_url(invitation_id: uuid.UUID | str) -> str:
    return f"/api/invitations/{invitation_id}/accept/"


def accept(client: Client, user: User, invitation_id: uuid.UUID | str, **headers: str) -> Any:
    url, auth = accept_url(invitation_id), {**bearer_of(user), **headers}
    return client.post(url, content_type="application/json", headers=auth)


def mine(client: Client, user: User, **headers: str) -> Any:
    return client.get(MINE, headers={**bearer_of(user), **headers})


def suspend(organization: Organization) -> None:
    Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk).update(
        status=OrgStatus.SUSPENDED.value
    )


def problem(response: Any) -> dict[str, Any]:
    body = dict(response.json())
    for name in VARYING:
        body.pop(name, None)
    return body


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


# --- GET /api/invitations/mine/ ------------------------------------------------------------------


def test_AC_TEN_39_lists_only_my_email(client: Client) -> None:
    a, b = new_org("A"), new_org("B")
    ana = new_user("ana")
    add_member(a, ana, Role.OWNER)
    mine_b, _ = issue(b, " ANA@hub.test ", Role.ADMIN)  # stored normalized, read by the same rule
    issue(b, "beto@hub.test")
    issue(a, "ana+1@hub.test")

    response = mine(client, ana, **{HEADER: str(a.id)})  # the header is ignored

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    [row] = body["results"]
    assert (body["count"], body["next"], body["previous"]) == (1, None, None)
    assert datetime.fromisoformat(row.pop("expires_at")) == mine_b.expires_at
    assert row == {
        "id": str(mine_b.id),
        "organization": {"id": str(b.id), "name": "B"},
        "role": "admin",
    }


def test_AC_TEN_39_response_has_no_token(client: Client) -> None:
    org = new_org("A")
    invitation, token = issue(org, "ana@hub.test")

    response = mine(client, new_user("ana"))

    text = response.content.decode()
    assert str(invitation.id) in text
    for secret in (token, hash_token(token), "operator@hub.test"):  # nor who invited them
        assert secret not in text
    assert set(response.json()["results"][0]) == {"id", "organization", "role", "expires_at"}


def test_AC_TEN_39_expired_and_suspended_are_not_listed(client: Client) -> None:
    active, suspended = new_org("Activa"), new_org("Suspendida")
    valid, _ = issue(active, "ana@hub.test", expires_at=timezone.now() + timedelta(minutes=5))
    late, _ = issue(new_org("Vencida"), "ana@hub.test")
    # Due but still ``pending``: nobody has seen it past its expiry yet (RN-TEN-12).
    make_due(late)
    issue(suspended, "ana@hub.test")
    suspend(suspended)
    for name, status in (("Vencida2", InvitationStatus.EXPIRED), ("Revocada", "revoked")):
        closed, _ = issue(new_org(name), "ana@hub.test")
        set_status(closed, InvitationStatus(status))

    response = mine(client, new_user("ana"))

    assert [row["id"] for row in response.json()["results"]] == [str(valid.id)]
    assert status_of(late) == InvitationStatus.PENDING  # listing does not expire anything


def test_RN_TEN_11_mine_anonymous_is_401(client: Client) -> None:
    response = client.get(MINE)
    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")


# --- POST /api/invitations/{id}/accept/ ----------------------------------------------------------


def test_AC_TEN_39_accept_from_session(client: Client, recorded: RecordingSink) -> None:
    a, b = new_org("A"), new_org("B")
    ana = new_user("ana")
    add_member(a, ana, Role.OWNER)
    invitation, token = issue(b, "ana@hub.test", Role.VIEWER)

    response = accept(client, ana, invitation.id, **{HEADER: str(a.id)})  # header ignored

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert body == {
        "organization": {"id": str(b.id), "name": "B"},
        "role": "viewer",
        "membership_id": body["membership_id"],
    }
    [_, (organization_id, role, status, source)] = memberships(ana)
    assert (organization_id, role, status, source) == (b.id, "viewer", "active", invitation.id)
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert token not in response.content.decode()
    assert [e.action for e in recorded.events] == ["membership.created", "invitation.accepted"]
    assert mine(client, ana).json()["count"] == 0


def test_AC_TEN_39_other_email_is_invalid_and_stays_pending(
    client: Client, recorded: RecordingSink
) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    beto = new_user("beto")

    response = accept(client, beto, invitation.id)

    assert response.status_code == 400
    assert (response.json()["code"], response.json()["reason"]) == (
        "invitation_invalid",
        "not_found",
    )
    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(beto) == []
    [event] = recorded.events
    assert (event.action, event.reason, event.organization_id) == (
        "invitation.rejected",
        "email_mismatch",
        org.id,
    )
    assert event.actor == AuditActor(kind=AuditActorKind.USER, id=beto.pk)
    assert event.metadata == {"invitation_id": str(invitation.id)}  # no email of anyone


def test_AC_TEN_39_foreign_and_missing_same_body(client: Client) -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    set_status(invitation, InvitationStatus.REVOKED)  # even a closed one says nothing of itself
    other, _ = issue(new_org("B"), "ana@hub.test")
    beto = new_user("beto")

    foreign = accept(client, beto, invitation.id)
    pending_foreign = accept(client, beto, other.id)
    missing = accept(client, beto, uuid.uuid4())

    assert foreign.status_code == pending_foreign.status_code == missing.status_code == 400
    assert problem(foreign) == problem(pending_foreign) == problem(missing)
    assert problem(missing)["reason"] == "not_found"
    for response in (foreign, pending_foreign, missing):
        assert response["Cache-Control"] == "no-store"
        assert "ana@hub.test" not in response.content.decode()


def test_AC_TEN_28_accept_from_session_is_409(client: Client) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    suspend(org)
    ana = new_user("ana")

    response = accept(client, ana, invitation.id)

    assert (response.status_code, response.json()["code"]) == (409, "organization_suspended")
    assert memberships(ana) == []
    assert status_of(invitation) == InvitationStatus.PENDING


def test_AC_TEN_39_double_accept_one_membership(client: Client) -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    ana = new_user("ana")
    # The first one as a browser sends it: a POST with no body and no Content-Type.
    first = client.generic("POST", accept_url(invitation.id), headers=bearer_of(ana))

    assert first.status_code == 200
    second = accept(client, ana, invitation.id)

    assert (second.status_code, second.json()["reason"]) == (400, "used")
    assert len(memberships(ana)) == 1


@pytest.mark.parametrize(
    ("status", "reason"),
    [(InvitationStatus.REVOKED, "revoked"), (InvitationStatus.EXPIRED, "expired")],
)
def test_AC_TEN_39_holder_sees_the_closed_reason(
    client: Client, status: InvitationStatus, reason: str
) -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    set_status(invitation, status)
    response = accept(client, new_user("ana"), invitation.id)
    assert (response.status_code, response.json()["reason"]) == (400, reason)


def test_RN_TEN_07_accept_from_session_already_member_is_409(client: Client) -> None:
    org = new_org("A")
    ana = new_user("ana")
    add_member(org, ana, Role.VIEWER)
    invitation, _ = issue(org, "ana@hub.test", Role.ADMIN)

    response = accept(client, ana, invitation.id)

    assert (response.status_code, response.json()["code"]) == (409, "already_member")
    assert status_of(invitation) == InvitationStatus.PENDING


def test_RN_TEN_11_accept_from_session_anonymous_is_401(client: Client) -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    response = client.post(accept_url(invitation.id))
    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")
    assert status_of(invitation) == InvitationStatus.PENDING


@pytest.mark.parametrize("extra", ["role", "organization_id", "token"])
def test_RN_TEN_12_accept_from_session_takes_no_body(client: Client, extra: str) -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    ana = new_user("ana")

    response = client.post(
        accept_url(invitation.id),
        {extra: "owner"},
        content_type="application/json",
        headers=bearer_of(ana),
    )

    assert (response.status_code, response.json()["code"]) == (400, "validation_error")
    assert response.json()["errors"] == [
        {"field": extra, "code": "unknown_field", "message": "Este campo no se acepta."}
    ]
    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(ana) == []


def test_RN_TEN_11_id_that_is_not_a_uuid_is_404(client: Client) -> None:
    assert accept(client, new_user("ana"), "not-a-uuid").status_code == 404


def test_AC_TEN_39_contract_declares_both_routes_exempt_and_without_token() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    listing = contract["paths"][MINE]["get"]
    assert set(listing["responses"]) >= {"200", "401"}
    assert all(p["in"] != "header" for p in listing.get("parameters", []))  # exempt (§3.5)
    row = contract["components"]["schemas"]["MyInvitation"]
    assert set(row["properties"]) == {"id", "organization", "role", "expires_at"}
    operation = contract["paths"]["/api/invitations/{invitation_id}/accept/"]["post"]
    assert set(operation["responses"]) >= {"200", "400", "401", "409"}
    assert "requestBody" not in operation
    assert [p["in"] for p in operation["parameters"]] == ["path"]
    assert contract["info"]["version"] == "0.13.0"
