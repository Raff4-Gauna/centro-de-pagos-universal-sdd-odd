"""``PATCH /api/memberships/{id}/``: change the role of a member (RF-TEN-04, design.md §4.2).

AC-TEN-05 (RN-TEN-08): a demotion rules from the next request, with the same session. AC-TEN-13:
the last owner is not demoted (``409 last_owner`` + ``owner_protection.rejected``). AC-TEN-15: an
admin never assigns or takes away ``owner``. AC-TEN-16: operator and viewer change nobody, and
nobody raises their own role. AC-TEN-27: transferring the ownership. AC-TEN-02: another
organization's membership is ``404``. AC-TEN-36 (Q-223): a demoted admin's ``owner`` invitations
are revoked in the same transaction (revoking and leaving are T-TEN-23's).
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
from apps.tenancy.models import Invitation, Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.membership_setup import (
    MEMBERSHIPS,
    member,
    patch_role,
    recorded,
    role_of,
    roles_in,
    set_role,
)
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, revoke
from tests.tenancy.invitation_setup import issue

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported so pytest finds it here

Action = TenancyAuditAction


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def actions(sink: RecordingSink) -> list[str]:
    return [str(event.action) for event in sink.events]


def create_branch(client: Client, headers: dict[str, str], name: str) -> Any:
    body = json.dumps({"name": name})
    return client.post(
        "/api/branches/", data=body, content_type="application/json", headers=headers
    )


# --- AC-TEN-05 ---


def test_AC_TEN_05_demoted_admin_next_request_403(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    admin, demoted = member(org_a, Role.ADMIN)
    headers = as_member(admin, org_a.id)  # one session, kept across the demotion
    assert create_branch(client, headers, "Centro").status_code == 201

    response = set_role(client, owner, org_a, demoted, Role.VIEWER)

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    again = create_branch(client, headers, "Norte")
    assert again.status_code == 403
    assert again.json()["code"] == "forbidden"
    edit = client.patch(
        "/api/organizations/current/",
        data=json.dumps({"name": "Otra"}),
        content_type="application/json",
        headers=headers,
    )
    assert edit.status_code == 403


# --- AC-TEN-13 ---


def test_AC_TEN_13_last_owner_demotion(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, mine = member(org_a, Role.OWNER)

    response = set_role(client, owner, org_a, mine, Role.ADMIN)

    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"
    assert response.json()["title"] == "Último owner"
    assert role_of(mine) == "owner"
    [event] = recorded.events
    assert event.action == Action.OWNER_PROTECTION_REJECTED
    assert (event.organization_id, event.actor.id) == (org_a.id, owner.pk)
    assert event.metadata == {"membership_id": str(mine.pk), "event": "change_role"}


# --- AC-TEN-15 ---


@pytest.mark.parametrize("target_role", [Role.ADMIN, Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_15_admin_cannot_assign_owner(
    client: Client, org_a: Organization, recorded: RecordingSink, target_role: Role
) -> None:
    admin, _ = member(org_a, Role.ADMIN, "jefa")
    _, target = member(org_a, target_role)

    response = set_role(client, admin, org_a, target, Role.OWNER)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert role_of(target) == target_role.value
    assert recorded.events == []


@pytest.mark.parametrize("new_role", [Role.ADMIN, Role.OPERATOR, Role.VIEWER, Role.OWNER])
def test_AC_TEN_15_admin_cannot_take_owner_away(
    client: Client, org_a: Organization, new_role: Role
) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    _, owner = member(org_a, Role.OWNER)

    response = set_role(client, admin, org_a, owner, new_role)

    assert response.status_code == 403
    assert role_of(owner) == "owner"


def test_AC_TEN_15_admin_manages_another_admin(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    admin, _ = member(org_a, Role.ADMIN, "jefa")
    other, target = member(org_a, Role.ADMIN, "colega")

    response = set_role(client, admin, org_a, target, Role.OPERATOR)

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["role"], body["user"]["email"]) == (
        str(target.pk),
        "operator",
        other.email,
    )
    assert body["allowed_actions"] == ["member.change_role", "member.revoke"]
    assert role_of(target) == "operator"
    [event] = recorded.events
    assert event.action == Action.MEMBERSHIP_ROLE_CHANGED
    assert event.metadata == {
        "membership_id": str(target.pk),
        "user_id": str(other.pk),
        "from_role": "admin",
        "to_role": "operator",
    }
    assert response["Cache-Control"] == "no-store"


# --- AC-TEN-16 ---


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_16_operator_cannot_change_role(
    client: Client, org_a: Organization, role: Role, recorded: RecordingSink
) -> None:
    user, mine = member(org_a, role)
    _, other = member(org_a, Role.VIEWER, "otro")

    for target, new in ((other, Role.OPERATOR), (mine, Role.ADMIN), (mine, Role.VIEWER)):
        response = set_role(client, user, org_a, target, new)
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"
    assert (role_of(mine), role_of(other)) == (role.value, "viewer")
    assert recorded.events == []


def test_AC_TEN_16_admin_cannot_raise_itself(client: Client, org_a: Organization) -> None:
    member(org_a, Role.OWNER)
    admin, mine = member(org_a, Role.ADMIN)

    response = set_role(client, admin, org_a, mine, Role.OWNER)

    assert response.status_code == 403
    assert role_of(mine) == "admin"


def test_AC_TEN_16_admin_demotes_itself(client: Client, org_a: Organization) -> None:
    member(org_a, Role.OWNER)
    admin, mine = member(org_a, Role.ADMIN)

    response = set_role(client, admin, org_a, mine, Role.VIEWER)

    assert response.status_code == 200
    assert response.json()["allowed_actions"] == ["member.leave"]  # as the viewer it now is
    assert role_of(mine) == "viewer"


# --- AC-TEN-27 ---


def test_AC_TEN_27_transfer_ownership(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, mine = member(org_a, Role.OWNER, "u")
    heir, theirs = member(org_a, Role.ADMIN, "v")

    promoted = set_role(client, owner, org_a, theirs, Role.OWNER)
    stepped_down = set_role(client, owner, org_a, mine, Role.ADMIN)

    assert (promoted.status_code, stepped_down.status_code) == (200, 200)
    assert roles_in(org_a) == [(owner.email, "admin", "active"), (heir.email, "owner", "active")]
    assert actions(recorded) == [Action.MEMBERSHIP_ROLE_CHANGED] * 2
    assert stepped_down.json()["assignable_roles"] == ["operator", "viewer"]  # now an admin
    blocked = set_role(client, heir, org_a, theirs, Role.ADMIN)  # the only owner left
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "last_owner"


# --- AC-TEN-02 ---


def test_AC_TEN_02_other_org_membership_is_404(client: Client, org_a: Organization) -> None:
    org_b = new_org("B")
    owner, _ = member(org_a, Role.OWNER)
    _, theirs = member(org_b, Role.ADMIN)

    foreign = set_role(client, owner, org_a, theirs, Role.VIEWER)
    missing = patch_role(client, owner, org_a, uuid.uuid4(), {"role": "viewer"})
    not_an_id = patch_role(client, owner, org_a, "not-a-uuid", {"role": "viewer"})

    assert (foreign.status_code, missing.status_code, not_an_id.status_code) == (404, 404, 404)
    bodies = [{k: v for k, v in r.json().items() if k != "request_id"} for r in (foreign, missing)]
    assert bodies[0] == bodies[1]
    assert bodies[0]["code"] == "not_found"
    assert role_of(theirs) == "admin"


# --- the rest of §4.2 ---


def test_C_05_revoked_membership_is_invalid_transition(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, gone = member(org_a, Role.ADMIN)
    revoke(org_a, gone)

    response = set_role(client, owner, org_a, gone, Role.VIEWER)

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"
    assert role_of(gone) == "admin"
    [event] = recorded.events
    assert event.action == Action.TRANSITION_REJECTED
    assert event.metadata == {
        "entity": "membership",
        "entity_id": str(gone.pk),
        "state": "revoked",
        "event": "change_role",
    }


def test_RF_TEN_04_same_role_is_a_noop(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, target = member(org_a, Role.OPERATOR)

    response = set_role(client, owner, org_a, target, Role.OPERATOR)

    assert response.status_code == 200
    assert response.json()["role"] == "operator"
    assert recorded.events == []


@pytest.mark.parametrize(
    "body", [{"role": "viewer", "status": "revoked"}, {"role": "viewer", "organization_id": "x"}]
)
def test_AC_TEN_07_body_is_strict(
    client: Client, org_a: Organization, body: dict[str, str]
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, target = member(org_a, Role.OPERATOR)

    response = patch_role(client, owner, org_a, target.pk, body)

    assert response.status_code == 400
    codes = {error["field"]: error["code"] for error in response.json()["errors"]}
    assert set(codes.values()) == {"unknown_field"}
    assert role_of(target) == "operator"


@pytest.mark.parametrize("body", [{}, {"role": "superadmin"}, {"role": None}])
def test_RF_TEN_04_role_is_required_and_known(
    client: Client, org_a: Organization, body: dict[str, object]
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, target = member(org_a, Role.OPERATOR)

    response = patch_role(client, owner, org_a, target.pk, body)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_AC_TEN_28_suspended_does_not_change_roles(client: Client) -> None:
    suspended = new_org("S", OrgStatus.SUSPENDED)
    owner, _ = member(suspended, Role.OWNER)
    _, target = member(suspended, Role.ADMIN)

    response = set_role(client, owner, suspended, target, Role.VIEWER)

    assert response.status_code == 409
    assert response.json()["code"] == "organization_suspended"
    assert role_of(target) == "admin"


# --- AC-TEN-36 (demotion only; revoking and leaving are T-TEN-23's) ---


def issued_by(organization: Organization, user: User, email: str, role: Role) -> Invitation:
    invitation, _ = issue(organization, email, role)
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    rows.update(invited_by_user=user, invited_by_operator="")
    return invitation


def invitations_in(organization: Organization) -> list[tuple[object, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=organization)
    return list(rows.order_by("email").values_list("email", "status", "revoked_reason"))


def test_AC_TEN_36_auto_revoked_on_demotion(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    admin, demoted = member(org_a, Role.ADMIN)
    lost = issued_by(org_a, admin, "a@x.com", Role.VIEWER)
    issue(org_a, "b@x.com", Role.ADMIN)  # the operator's: never touched

    response = set_role(client, owner, org_a, demoted, Role.OPERATOR)

    assert response.status_code == 200
    assert invitations_in(org_a) == [
        ("a@x.com", "revoked", "inviter_lost_permission"),
        ("b@x.com", "pending", None),
    ]
    revoked_by = Invitation.objects.unscoped(PLATFORM).values_list("revoked_by_id", flat=True)
    assert revoked_by.get(pk=lost.pk) == owner.pk
    assert actions(recorded) == [Action.MEMBERSHIP_ROLE_CHANGED, Action.INVITATION_AUTO_REVOKED]
    auto = recorded.events[1]
    assert auto.reason == "inviter_lost_permission"
    assert auto.metadata == {"invitation_id": str(lost.pk), "membership_id": str(demoted.pk)}


def test_AC_TEN_36_a_demoted_owner_keeps_what_an_admin_may_issue(
    client: Client, org_a: Organization
) -> None:
    owner, mine = member(org_a, Role.OWNER)
    member(org_a, Role.OWNER, "otra-owner")
    issued_by(org_a, owner, "a@x.com", Role.OWNER)
    issued_by(org_a, owner, "b@x.com", Role.VIEWER)

    response = set_role(client, owner, org_a, mine, Role.ADMIN)

    assert response.status_code == 200
    assert invitations_in(org_a) == [
        ("a@x.com", "revoked", "inviter_lost_permission"),
        ("b@x.com", "pending", None),
    ]


def test_RF_TEN_04_contract_changes_a_role() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operation = contract["paths"][f"{MEMBERSHIPS}{{id}}/"]["patch"]
    schemas = contract["components"]["schemas"]

    request = operation["requestBody"]["content"]["application/json"]["schema"]
    body = schemas[request["$ref"].rsplit("/", 1)[1]]
    assert set(body["properties"]) == {"role"}
    assert {"403", "404", "409", "503"} <= set(operation["responses"])
    assert "organization_busy" in operation["responses"]["503"]["description"]
