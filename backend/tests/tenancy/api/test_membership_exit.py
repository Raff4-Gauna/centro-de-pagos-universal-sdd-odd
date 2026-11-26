"""``DELETE /api/memberships/{id}/`` and ``POST /api/memberships/me/leave/`` (RF-TEN-04, §4.2).

AC-TEN-04 (RN-TEN-08): a revoked admin is rejected on the next request, with the same session.
AC-TEN-13: the last owner neither leaves nor revokes itself (``409 last_owner`` +
``owner_protection.rejected``). AC-TEN-15: an admin never revokes an owner. AC-TEN-31 (RN-TEN-21):
leaving keeps the membership as ``revoked``, and re-inviting creates a new one. Q-221: both reduce
access, so they go on with the organization suspended. The invitations revoked with the person are
``test_membership_exit_invitations.py``; the races, ``tests/tenancy/test_membership_exit_race.py``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Membership, Organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.membership_exit import leave_organization, revoke_membership
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.membership_setup import MEMBERSHIPS, member, recorded, roles_in
from tests.tenancy.api.probe import PLATFORM, as_member, bearer_of, new_org, revoke
from tests.tenancy.invitation_setup import memberships

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported so pytest finds it here

Action = TenancyAuditAction
LEAVE = f"{MEMBERSHIPS}me/leave/"
JSON = "application/json"


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def revoke_member(
    client: Client, user: User, organization: Organization, membership_id: Any, **extra: Any
) -> Any:
    return client.delete(
        f"{MEMBERSHIPS}{membership_id}/", headers=as_member(user, organization.id), **extra
    )


def leave(client: Client, user: User, organization: Organization, **extra: Any) -> Any:
    return client.post(
        LEAVE, content_type="application/json", headers=as_member(user, organization.id), **extra
    )


def ended(membership: Membership) -> tuple[Any, ...]:
    rows = Membership.objects.unscoped(PLATFORM).filter(pk=membership.pk)
    return rows.values_list("status", "ended_reason", "ended_by_id").get()


# --- AC-TEN-04 ---


def test_AC_TEN_04_revoked_admin_is_rejected(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    admin, target = member(org_a, Role.ADMIN)
    headers = as_member(admin, org_a.id)  # one session, kept across the revocation
    assert client.get(MEMBERSHIPS, headers=headers).status_code == 200

    response = revoke_member(client, owner, org_a, target.pk)

    assert response.status_code == 204
    assert response.content == b""
    assert ended(target) == ("revoked", "revoked", owner.pk)
    again = client.get(MEMBERSHIPS, headers=headers)
    assert again.status_code == 404
    assert again.json()["code"] == "organization_not_found"
    [event] = recorded.events
    assert event.action == Action.MEMBERSHIP_REVOKED
    assert (event.organization_id, event.actor.id, event.reason) == (org_a.id, owner.pk, "revoked")
    assert event.metadata == {
        "membership_id": str(target.pk),
        "user_id": str(admin.pk),
        "role": "admin",
    }


# --- AC-TEN-13 ---


@pytest.mark.parametrize("how", ["leave", "delete_own"])
def test_AC_TEN_13_last_owner_cannot_leave(
    client: Client, org_a: Organization, recorded: RecordingSink, how: str
) -> None:
    owner, mine = member(org_a, Role.OWNER)
    member(org_a, Role.ADMIN)

    if how == "leave":
        response = leave(client, owner, org_a)
    else:
        response = revoke_member(client, owner, org_a, mine.pk)

    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"
    assert ended(mine) == ("active", None, None)
    [event] = recorded.events
    assert event.action == Action.OWNER_PROTECTION_REJECTED
    assert (event.organization_id, event.actor.id) == (org_a.id, owner.pk)
    assert event.metadata == {"membership_id": str(mine.pk), "event": "leave"}


def test_AC_TEN_13_an_owner_leaves_when_another_one_stays(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, mine = member(org_a, Role.OWNER)
    _, other = member(org_a, Role.OWNER, "otra-owner")

    response = revoke_member(client, owner, org_a, mine.pk)  # one's own: leaving

    assert response.status_code == 204
    assert ended(mine) == ("revoked", "left", owner.pk)
    assert ended(other) == ("active", None, None)
    assert [str(event.action) for event in recorded.events] == [Action.MEMBERSHIP_LEFT]


def test_AC_TEN_13_an_owner_revokes_another_owner(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, other = member(org_a, Role.OWNER, "otra-owner")

    response = revoke_member(client, owner, org_a, other.pk)

    assert response.status_code == 204
    assert ended(other) == ("revoked", "revoked", owner.pk)


# --- AC-TEN-15 / AC-TEN-16 ---


def test_AC_TEN_15_admin_cannot_revoke_an_owner(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    _, owner = member(org_a, Role.OWNER)
    member(org_a, Role.OWNER, "otra-owner")  # not the last one: the role is what refuses

    response = revoke_member(client, admin, org_a, owner.pk)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert ended(owner) == ("active", None, None)
    assert recorded.events == []


@pytest.mark.parametrize("target_role", [Role.ADMIN, Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_15_admin_revokes_below_owner(
    client: Client, org_a: Organization, target_role: Role
) -> None:
    admin, _ = member(org_a, Role.ADMIN, "jefa")
    _, target = member(org_a, target_role)

    response = revoke_member(client, admin, org_a, target.pk)

    assert response.status_code == 204
    assert ended(target) == ("revoked", "revoked", admin.pk)


@pytest.mark.parametrize("actor_role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_16_operator_and_viewer_cannot_revoke(
    client: Client, org_a: Organization, actor_role: Role
) -> None:
    actor, mine = member(org_a, actor_role)
    _, target = member(org_a, Role.VIEWER, "otra")

    for membership_id in (target.pk, mine.pk):  # their own too: they leave by its route
        response = revoke_member(client, actor, org_a, membership_id)
        assert response.status_code == 403
    assert ended(target) == ended(mine) == ("active", None, None)


# --- AC-TEN-31 ---


def test_AC_TEN_31_leave_then_reinvite_is_new_membership(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    operator, left = member(org_a, Role.OPERATOR)
    headers = as_member(operator, org_a.id)

    response = client.post(LEAVE, content_type="application/json", headers=headers)

    assert response.status_code == 204
    assert ended(left) == ("revoked", "left", operator.pk)
    [event] = recorded.events
    assert (event.action, event.actor.id, event.reason) == (
        Action.MEMBERSHIP_LEFT,
        operator.pk,
        "left",
    )
    again = client.get("/api/branches/", headers=headers)
    assert (again.status_code, again.json()["code"]) == (404, "organization_not_found")

    invited = client.post(
        "/api/invitations/",
        data=json.dumps({"email": operator.email, "role": "viewer"}),
        content_type="application/json",
        headers=as_member(owner, org_a.id),
    )
    assert invited.status_code == 201
    token = invited.json()["accept_url"].split("#token=", 1)[1]
    accepted = client.post(
        "/api/invitations/accept/",
        data=json.dumps({"token": token}),
        content_type="application/json",
        headers=bearer_of(operator),
    )
    assert accepted.status_code == 200
    new_id = uuid.UUID(accepted.json()["membership_id"])
    assert new_id != left.pk
    rows = [(row[1], row[2]) for row in memberships(operator)]
    assert rows == [("operator", "revoked"), ("viewer", "active")]
    assert client.get("/api/branches/", headers=headers).status_code == 200


# --- Q-221 ---


@pytest.mark.parametrize("how", ["revoke", "leave"])
def test_Q_221_revoke_allowed_when_suspended(client: Client, how: str) -> None:
    suspended = new_org("S", OrgStatus.SUSPENDED)
    owner, _ = member(suspended, Role.OWNER)
    admin, target = member(suspended, Role.ADMIN)

    if how == "revoke":
        response = revoke_member(client, owner, suspended, target.pk)
    else:
        response = leave(client, admin, suspended)

    assert response.status_code == 204
    assert ended(target)[0] == "revoked"
    edit = client.patch(
        f"{MEMBERSHIPS}{target.pk}/",
        data=json.dumps({"role": "viewer"}),
        content_type="application/json",
        headers=as_member(owner, suspended.id),
    )
    assert (edit.status_code, edit.json()["code"]) == (409, "organization_suspended")


# --- the rest of §4.2 ---


def test_AC_TEN_02_other_org_membership_is_404(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    org_b = new_org("B")
    _, theirs = member(org_b, Role.ADMIN)

    foreign = revoke_member(client, owner, org_a, theirs.pk)
    missing = revoke_member(client, owner, org_a, uuid.uuid4())
    not_an_id = revoke_member(client, owner, org_a, "not-a-uuid")

    bodies = [
        {k: v for k, v in r.json().items() if k != "request_id"}
        for r in (foreign, missing, not_an_id)
    ]
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["code"] == "not_found"
    assert ended(theirs) == ("active", None, None)


def test_C_05_revoked_membership_is_invalid_transition(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, gone = member(org_a, Role.ADMIN)
    revoke(org_a, gone)

    response = revoke_member(client, owner, org_a, gone.pk)

    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")
    [event] = recorded.events
    assert event.action == Action.TRANSITION_REJECTED
    assert event.metadata == {
        "entity": "membership",
        "entity_id": str(gone.pk),
        "state": "revoked",
        "event": "revoke",
    }


@pytest.mark.parametrize("how", ["revoke", "leave"])
def test_RN_TEN_12_takes_no_body(client: Client, org_a: Organization, how: str) -> None:
    owner, _ = member(org_a, Role.OWNER)
    admin, target = member(org_a, Role.ADMIN)
    body = {"data": json.dumps({"reason": "x"}), "content_type": JSON}

    if how == "revoke":
        response = revoke_member(client, owner, org_a, target.pk, **body)
    else:
        response = client.post(
            LEAVE, data=body["data"], content_type=JSON, headers=as_member(admin, org_a.id)
        )

    assert response.status_code == 400
    assert [error["code"] for error in response.json()["errors"]] == ["unknown_field"]
    assert ended(target) == ("active", None, None)


def test_RN_TEN_21_put_is_not_allowed(client: Client, org_a: Organization) -> None:
    owner, mine = member(org_a, Role.OWNER)

    response = client.put(
        f"{MEMBERSHIPS}{mine.pk}/",
        data=json.dumps({"role": "admin"}),
        content_type="application/json",
        headers=as_member(owner, org_a.id),
    )

    assert response.status_code == 405
    assert roles_in(org_a) == [(owner.email, "owner", "active")]


def test_RNF_TEN_04_each_exit_has_its_trigger() -> None:
    assert AUDIT_TRIGGERS[Action.MEMBERSHIP_REVOKED] is revoke_membership
    assert AUDIT_TRIGGERS[Action.MEMBERSHIP_LEFT] is leave_organization


def test_RF_TEN_04_contract_of_revoke_and_leave() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    revoking = contract["paths"][f"{MEMBERSHIPS}{{id}}/"]["delete"]
    leaving = contract["paths"][LEAVE]["post"]

    assert contract["info"]["version"] == "0.19.0"
    assert "requestBody" not in revoking
    assert {"204", "403", "404", "409", "503"} <= set(revoking["responses"])
    assert {"204", "409", "503"} <= set(leaving["responses"])
    for operation in (revoking, leaving):
        assert "content" not in operation["responses"]["204"]
        assert "organization_busy" in operation["responses"]["503"]["description"]
        assert "last_owner" in json.dumps(operation["responses"]["409"])
