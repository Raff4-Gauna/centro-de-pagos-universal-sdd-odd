"""The invitations a person issued, when the person loses the permission (Q-223, AC-TEN-36).

Demoted, revoked or leaving: in the same transaction, every ``pending`` invitation that person
issued and the new role no longer allows (all of them, when it is gone) becomes ``revoked`` with
``inviter_lost_permission``, with one ``invitation.auto_revoked`` each, and accepting it is
``invitation_invalid`` (``revoked``). The operator's invitations are never touched. A resent
invitation belongs to whoever resent it (Q-234 a): auto-revocation follows the resender.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client

from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.tenancy.api.membership_setup import MEMBERSHIPS, member, recorded, set_role
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, status_of

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported so pytest finds it here

Action = TenancyAuditAction


def issued_by(
    organization: Organization, user: User, email: str, role: Role = Role.VIEWER
) -> tuple[Invitation, str]:
    invitation, token = issue(organization, email, role)
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    rows.update(invited_by_user=user, invited_by_operator="")
    return invitation, token


def revoked_reason(invitation_id: Any) -> tuple[str, str | None, Any]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation_id)
    return rows.values_list("status", "revoked_reason", "revoked_by_id").get()


def demote(client: Client, owner: User, org: Organization, target: Membership) -> Any:
    return set_role(client, owner, org, target, Role.OPERATOR)


def revoke(client: Client, owner: User, org: Organization, target: Membership) -> Any:
    return client.delete(f"{MEMBERSHIPS}{target.pk}/", headers=as_member(owner, org.id))


def leave(client: Client, user: User, org: Organization) -> Any:
    return client.post(
        f"{MEMBERSHIPS}me/leave/", content_type="application/json", headers=as_member(user, org.id)
    )


@pytest.mark.parametrize("how", ["demotion", "revoke", "leave"])
def test_AC_TEN_36_auto_revoked_on_demotion_revoke_and_leave(
    client: Client, recorded: RecordingSink, how: str
) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    admin, target = member(org, Role.ADMIN)
    lost, token = issued_by(org, admin, "a@x.com", Role.ADMIN)
    operators, _ = issue(org, "b@x.com", Role.ADMIN)  # the operator's: never touched
    owners, _ = issued_by(org, owner, "c@x.com", Role.VIEWER)  # someone else's: never touched

    if how == "demotion":
        response = demote(client, owner, org, target)
    elif how == "revoke":
        response = revoke(client, owner, org, target)
    else:
        response = leave(client, admin, org)

    assert response.status_code in (200, 204)
    by = admin.pk if how == "leave" else owner.pk
    assert revoked_reason(lost.pk) == ("revoked", "inviter_lost_permission", by)
    assert status_of(operators) == status_of(owners) == "pending"
    auto = [event for event in recorded.events if event.action == Action.INVITATION_AUTO_REVOKED]
    [event] = auto
    assert (event.reason, event.actor.id) == ("inviter_lost_permission", by)
    assert event.metadata == {"invitation_id": str(lost.pk), "membership_id": str(target.pk)}
    assert recorded.events[-1] is event  # after the membership's own event, in the transaction
    with pytest.raises(InvitationInvalid) as refused:
        accept_by_token(token, invitee(new_user("a"), "a@x.com"))
    assert refused.value.problem_reason == "revoked"


@pytest.mark.parametrize("how", ["revoke", "leave"])
def test_AC_TEN_36_a_member_gone_loses_every_pending_one(client: Client, how: str) -> None:
    """Gone, it may issue nothing: every role of its pending invitations goes, even a viewer's."""
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    other, target = member(org, Role.OWNER, "otra-owner")
    issued = [issued_by(org, other, f"{role.value}@x.com", role)[0] for role in Role]

    response = revoke(client, owner, org, target) if how == "revoke" else leave(client, other, org)

    assert response.status_code == 204
    reasons = {revoked_reason(invitation.pk)[1] for invitation in issued}
    assert reasons == {"inviter_lost_permission"}


def test_AC_TEN_36_a_refused_exit_revokes_nothing(client: Client, recorded: RecordingSink) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    invitation, _ = issued_by(org, owner, "a@x.com", Role.OWNER)

    response = leave(client, owner, org)  # the last owner

    assert response.status_code == 409
    assert status_of(invitation) == "pending"
    assert [str(event.action) for event in recorded.events] == [Action.OWNER_PROTECTION_REJECTED]


def _resend(client: Client, user: User, org: Organization, invitation: Invitation) -> str:
    response = client.post(
        f"/api/invitations/{invitation.pk}/resend/",
        content_type="application/json",
        headers=as_member(user, org.id),
    )
    assert response.status_code == 201, response.content
    return str(response.json()["id"])


def test_Q_234_auto_revocation_follows_the_resender(client: Client) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    admin, target = member(org, Role.ADMIN)
    by_owner, _ = issued_by(org, owner, "a@x.com")
    by_admin, _ = issued_by(org, admin, "b@x.com")
    resent_by_admin = _resend(client, admin, org, by_owner)  # now the admin's (Q-234 a)
    resent_by_owner = _resend(client, owner, org, by_admin)  # now the owner's

    response = client.delete(f"{MEMBERSHIPS}{target.pk}/", headers=as_member(owner, org.id))

    assert response.status_code == 204
    assert revoked_reason(resent_by_admin)[:2] == ("revoked", "inviter_lost_permission")
    assert revoked_reason(resent_by_owner)[:2] == ("pending", None)
    assert revoked_reason(by_owner.pk)[1] == revoked_reason(by_admin.pk)[1] == "resent"


def test_AC_TEN_36_the_invitation_list_drops_them(client: Client) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    admin, target = member(org, Role.ADMIN)
    issued_by(org, admin, "a@x.com")
    kept, _ = issue(org, "b@x.com")

    assert revoke(client, owner, org, target).status_code == 204

    listed = client.get("/api/invitations/", headers=as_member(owner, org.id))
    assert [row["id"] for row in listed.json()["results"]] == [str(kept.pk)]
    assert "a@x.com" not in json.dumps(listed.json())
