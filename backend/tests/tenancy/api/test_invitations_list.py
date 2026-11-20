"""``GET /api/invitations/``: the pending invitations of the active organization (RF-TEN-05, §6).

AC-TEN-34 (Q-218): operator and viewer get ``403`` and no email. Only the ``pending`` ones still
valid, of this organization only (RN-TEN-05), never a token (AC-TEN-24); each row carries what the
UI may offer on it (``allowed_actions``), consistent with the matrix and
``decide_manage_invitation``.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus, hash_token
from apps.tenancy.models import Organization
from tests.tenancy.api.invitation_api_setup import INVITATIONS, invite, token_of
from tests.tenancy.api.membership_setup import member
from tests.tenancy.api.probe import PLATFORM, as_member, new_org
from tests.tenancy.invitation_setup import issue, make_due, set_status

pytestmark = pytest.mark.django_db

RESEND, REVOKE = "invitation.resend", "invitation.revoke"


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def listed(client: Client, user: Any, organization: Organization) -> dict[str, Any]:
    response = client.get(INVITATIONS, headers=as_member(user, organization.id))
    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "no-store"
    return dict(response.json())


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_34_operator_cannot_list(client: Client, org_a: Organization, role: Role) -> None:
    issue(org_a, "invitada@hub.test")
    user, _ = member(org_a, role)

    response = client.get(INVITATIONS, headers=as_member(user, org_a.id))

    assert (response.status_code, response.json()["code"]) == (403, "forbidden")
    assert "@" not in response.content.decode()


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_AC_TEN_34_owner_and_admin_list(client: Client, org_a: Organization, role: Role) -> None:
    user, _ = member(org_a, role)
    by_operator, _ = issue(org_a, "primera@hub.test", Role.VIEWER)
    created = invite(client, user, org_a, {"email": "segunda@hub.test", "role": "operator"})

    body = listed(client, user, org_a)

    assert body["count"] == 2
    rows = {row["id"]: row for row in body["results"]}
    first, second = rows[str(by_operator.pk)], rows[created.json()["id"]]
    assert first["invited_by"] is None  # the platform operator's: not the organization's to see
    assert second["invited_by"] == {"id": str(user.pk), "email": user.email, "name": ""}
    assert set(second) == {
        "id",
        "email",
        "role",
        "status",
        "purpose",
        "expires_at",
        "invited_by",
        "created_at",
        "allowed_actions",
    }


def test_AC_TEN_24_list_has_no_token(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    _, issued = issue(org_a, "a@hub.test")
    token = token_of(invite(client, owner, org_a, {"email": "b@hub.test", "role": "viewer"}))

    text = client.get(INVITATIONS, headers=as_member(owner, org_a.id)).content.decode()

    for secret in (issued, token, hash_token(issued), hash_token(token)):
        assert secret not in text
    assert "accept_url" not in text


def test_RF_TEN_05_lists_only_valid_pending_ones(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    pending, _ = issue(org_a, "vigente@hub.test")
    for email, status in (
        ("usada@hub.test", InvitationStatus.REVOKED),
        ("vencida@hub.test", InvitationStatus.EXPIRED),
    ):
        closed, _ = issue(org_a, email)
        set_status(closed, status)
    due, _ = issue(org_a, "por-vencer@hub.test")
    make_due(due)  # still pending in the table, but past its expiry (RN-TEN-12)

    body = listed(client, owner, org_a)

    assert [row["id"] for row in body["results"]] == [str(pending.pk)]


def test_AC_TEN_02_other_org_invitations_are_not_listed(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    theirs, _ = issue(new_org("B"), "de-b@hub.test")

    response = client.get(INVITATIONS, headers=as_member(owner, org_a.id))

    assert response.json()["count"] == 0
    assert str(theirs.pk) not in response.content.decode()
    assert "de-b@hub.test" not in response.content.decode()


def test_RN_TEN_13_allowed_actions_follow_the_invitation_role(
    client: Client, org_a: Organization
) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    owner, _ = member(org_a, Role.OWNER)
    for_owner, _ = issue(org_a, "jefa@hub.test", Role.OWNER)
    for_operator, _ = issue(org_a, "op@hub.test", Role.OPERATOR)

    as_admin = {row["id"]: row for row in listed(client, admin, org_a)["results"]}
    as_owner = {row["id"]: row for row in listed(client, owner, org_a)["results"]}

    assert as_admin[str(for_owner.pk)]["allowed_actions"] == []  # Q-202: never an owner one
    assert as_admin[str(for_operator.pk)]["allowed_actions"] == [RESEND, REVOKE]
    assert as_owner[str(for_owner.pk)]["allowed_actions"] == [RESEND, REVOKE]


def test_AC_TEN_28_suspended_lists_and_only_revoke_is_offered(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    issue(org_a, "op@hub.test", Role.OPERATOR)
    Organization.objects.unscoped(PLATFORM).filter(pk=org_a.pk).update(status="suspended")

    (row,) = listed(client, owner, org_a)["results"]

    assert row["allowed_actions"] == [REVOKE]  # resending is a WRITE; revoking reduces (Q-221)
