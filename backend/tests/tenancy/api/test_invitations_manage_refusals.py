"""What resending and revoking an invitation refuse (RF-TEN-05, design.md §4.3, §6).

AC-TEN-15 (Q-202): an admin never resends nor revokes an ``owner`` one; operator and viewer
neither (AC-TEN-16). RN-TEN-08: the actor is read again under the lock. AC-TEN-02 (RN-TEN-05):
another organization's is ``404`` and nothing changes there. AC-TEN-37 (C-05, Q-225): a state that
does not admit it is ``409 invalid_transition`` with ``transition.rejected``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from apps.common.audit.port import AuditActorKind
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services import invitation_manage as service
from tests.tenancy.api.invitation_api_setup import INVITATIONS, invitations_of, manage
from tests.tenancy.api.membership_setup import member, recorded
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, new_user, revoke
from tests.tenancy.invitation_setup import issue, make_due, set_status, status_of

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported for the tests below


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def problem(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


# --- AC-TEN-15 / AC-TEN-16 ---


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_15_admin_cannot_manage_owner_invitation(
    client: Client, org_a: Organization, recorded: RecordingSink, action: str
) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    invitation, _ = issue(org_a, "jefa@hub.test", Role.OWNER)
    recorded.clear()

    response = manage(client, admin, org_a, invitation.pk, action)

    assert problem(response) == (403, "forbidden")
    assert invitations_of(org_a) == [("jefa@hub.test", "owner", "pending")]
    assert recorded.events == []


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_15_owner_manages_owner_invitation(
    client: Client, org_a: Organization, action: str
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    invitation, _ = issue(org_a, "socia@hub.test", Role.OWNER)

    response = manage(client, owner, org_a, invitation.pk, action)

    assert response.status_code in (200, 201), response.content
    assert status_of(invitation) == InvitationStatus.REVOKED


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_16_operator_and_viewer_cannot_manage(
    client: Client, org_a: Organization, role: Role, action: str
) -> None:
    user, _ = member(org_a, role)
    invitation, _ = issue(org_a, "ana@hub.test", Role.VIEWER)

    response = manage(client, user, org_a, invitation.pk, action)

    assert problem(response) == (403, "forbidden")
    assert status_of(invitation) == InvitationStatus.PENDING


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_RN_TEN_08_revoked_actor_under_the_lock(
    client: Client, org_a: Organization, action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revoked after the request was resolved: what the next request would answer."""
    owner, membership = member(org_a, Role.OWNER)
    invitation, _ = issue(org_a, "ana@hub.test")
    real = service.lock_membership_mutex

    def revoked_meanwhile(*args: Any) -> Any:
        revoke(org_a, membership)
        return real(*args)

    monkeypatch.setattr(service, "lock_membership_mutex", revoked_meanwhile)

    response = manage(client, owner, org_a, invitation.pk, action)

    assert problem(response) == (404, "organization_not_found")
    assert status_of(invitation) == InvitationStatus.PENDING


# --- AC-TEN-02 ---


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_02_other_org_invitation_is_404(
    client: Client, org_a: Organization, recorded: RecordingSink, action: str
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    org_b = new_org("B")
    theirs, _ = issue(org_b, "ana@hub.test")
    before = invitations_of(org_b)
    recorded.clear()

    foreign = manage(client, owner, org_a, theirs.pk, action)
    missing = manage(client, owner, org_a, "00000000-0000-4000-8000-000000000000", action)
    not_uuid = manage(client, owner, org_a, "no-es-un-uuid", action)

    for response in (foreign, missing, not_uuid):
        assert problem(response) == (404, "not_found")
    body = foreign.json()
    assert body["detail"] == missing.json()["detail"] == not_uuid.json()["detail"]
    assert "ana@hub.test" not in foreign.content.decode()
    assert invitations_of(org_b) == before
    assert recorded.events == []


# --- AC-TEN-37 ---


@pytest.mark.parametrize(
    "state", [InvitationStatus.ACCEPTED, InvitationStatus.REVOKED, InvitationStatus.EXPIRED]
)
@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_37_revoke_accepted_is_invalid_transition(
    client: Client,
    org_a: Organization,
    recorded: RecordingSink,
    state: InvitationStatus,
    action: str,
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    accepted_by = new_user("ana") if state is InvitationStatus.ACCEPTED else None
    invitation, _ = issue(org_a, "ana@hub.test")
    rows = Invitation.objects.unscoped(PLATFORM).filter(pk=invitation.pk)
    if accepted_by is None:
        set_status(invitation, state)
    else:
        rows.update(status=state.value, accepted_by=accepted_by, accepted_at=timezone.now())
    recorded.clear()

    response = manage(client, owner, org_a, invitation.pk, action)

    assert problem(response) == (409, "invalid_transition")
    assert status_of(invitation) == state
    assert len(invitations_of(org_a)) == 1
    (event,) = recorded.events
    assert event.action == "transition.rejected"
    assert event.metadata == {
        "entity": "invitation",
        "entity_id": str(invitation.pk),
        "state": state.value,
        "event": action,
    }
    assert (event.actor.kind, event.actor.id) == (AuditActorKind.USER, owner.pk)


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_AC_TEN_37_past_expiry_is_expired_then_invalid_transition(
    client: Client, org_a: Organization, recorded: RecordingSink, action: str
) -> None:
    """Still ``pending`` past ``expires_at``: expired first (lazy expiry), then refused."""
    owner, _ = member(org_a, Role.OWNER)
    invitation, _ = issue(org_a, "ana@hub.test")
    make_due(invitation)
    recorded.clear()

    response = manage(client, owner, org_a, invitation.pk, action)

    assert problem(response) == (409, "invalid_transition")
    assert status_of(invitation) == InvitationStatus.EXPIRED
    expired, rejected = recorded.events
    assert (expired.action, expired.actor.kind) == ("invitation.expired", AuditActorKind.SYSTEM)
    assert expired.metadata == {"invitation_id": str(invitation.pk)}
    assert (rejected.action, rejected.metadata["state"]) == ("transition.rejected", "expired")


# --- Input and contract ---


@pytest.mark.parametrize("action", ["resend", "revoke"])
def test_RN_TEN_12_takes_no_body(client: Client, org_a: Organization, action: str) -> None:
    owner, _ = member(org_a, Role.OWNER)
    invitation, _ = issue(org_a, "ana@hub.test")

    response = client.post(
        f"{INVITATIONS}{invitation.pk}/{action}/",
        data=json.dumps({"role": "owner"}),
        content_type="application/json",
        headers=as_member(owner, org_a.id),
    )

    assert problem(response) == (400, "validation_error")
    assert response.json()["errors"][0]["code"] == "unknown_field"
    assert status_of(invitation) == InvitationStatus.PENDING
