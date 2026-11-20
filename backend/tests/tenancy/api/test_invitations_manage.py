"""Resend and revoke an invitation of the active organization (RF-TEN-05, design.md §4.3, §6).

AC-TEN-26 (RN-TEN-12): resending revokes the old one (``resent``) and issues a new one with a new
token and seven days from now. AC-TEN-24 (RNF-TEN-03): the new token is only in the resend's
``201`` and the old one is no longer accepted. Revoking is allowed with the organization
suspended, resending is not (Q-221). The refusals are in ``test_invitations_manage_refusals.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
import yaml
from django.test import Client
from django.utils import timezone

from apps.common.audit.port import AuditActorKind
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus, hash_token
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.invitation_api_setup import (
    INVITATIONS,
    invitations_of,
    invite,
    manage,
    token_of,
)
from tests.tenancy.api.membership_setup import member, recorded
from tests.tenancy.api.probe import PLATFORM, as_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, status_of

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported for the tests below


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def problem(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def row(invitation_id: Any) -> Invitation:
    return Invitation.objects.unscoped(PLATFORM).get(pk=invitation_id)


# --- AC-TEN-26 ---


def test_AC_TEN_26_resend_revokes_old_and_renews(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    soon = timezone.now() + timedelta(days=1)
    old, _ = issue(org_a, "x@dominio.com", Role.ADMIN, expires_at=soon)
    recorded.clear()

    response = manage(client, owner, org_a, old.pk, "resend")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["id"] != str(old.pk)
    assert (body["email"], body["role"], body["status"]) == ("x@dominio.com", "admin", "pending")
    assert body["invited_by"] == {"id": str(owner.pk), "email": owner.email, "name": ""}
    assert body["allowed_actions"] == ["invitation.resend", "invitation.revoke"]
    assert response["Cache-Control"] == "no-store"
    previous, renewed = row(old.pk), row(body["id"])
    assert (previous.status, previous.revoked_reason) == ("revoked", "resent")
    assert (previous.revoked_by_id, previous.revoked_at is not None) == (owner.pk, True)
    assert renewed.replaces_id == old.pk
    assert renewed.token_hash != previous.token_hash
    assert renewed.expires_at - timezone.now() == pytest.approx(
        timedelta(days=7), abs=timedelta(seconds=5)
    )
    assert invitations_of(org_a) == [
        ("x@dominio.com", "admin", "pending"),
        ("x@dominio.com", "admin", "revoked"),
    ]
    events = {event.action: event for event in recorded.events}
    assert set(events) == {"invitation.revoked", "invitation.resent"}
    assert (events["invitation.revoked"].reason, events["invitation.revoked"].metadata) == (
        "resent",
        {"invitation_id": str(old.pk), "role": "admin"},
    )
    assert events["invitation.resent"].metadata == {
        "invitation_id": body["id"],
        "replaces": str(old.pk),
        "role": "admin",
        "purpose": "standard",
    }
    for event in events.values():
        assert (event.actor.kind, event.actor.id) == (AuditActorKind.USER, owner.pk)
        assert event.organization_id == org_a.id


def test_AC_TEN_26_new_token_is_accepted_for_seven_days(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    old, _ = issue(org_a, "ana@hub.test", Role.VIEWER)
    resent = manage(client, owner, org_a, old.pk, "resend")
    ana = new_user("ana")

    accepted = accept_by_token(token_of(resent), invitee(ana))

    assert (accepted.organization_id, accepted.role) == (org_a.id, Role.VIEWER)
    assert status_of(row(resent.json()["id"])) == InvitationStatus.ACCEPTED


def test_AC_TEN_26_resend_keeps_one_pending_per_email(client: Client, org_a: Organization) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    old, _ = issue(org_a, "x@dominio.com")

    first = manage(client, admin, org_a, old.pk, "resend")
    again = manage(client, admin, org_a, old.pk, "resend")

    assert first.status_code == 201, first.content
    assert problem(again) == (409, "invalid_transition")
    pending = [r for r in invitations_of(org_a) if r[2] == "pending"]
    assert pending == [("x@dominio.com", "operator", "pending")]


# --- AC-TEN-24 ---


def test_AC_TEN_24_old_token_is_invalid(
    client: Client,
    org_a: Organization,
    recorded: RecordingSink,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    old, old_token = issue(org_a, "ana@hub.test")
    capsys.readouterr()

    resent = manage(client, owner, org_a, old.pk, "resend")
    listed = client.get(INVITATIONS, headers=as_member(owner, org_a.id))

    assert resent.status_code == 201, resent.content
    token = token_of(resent)
    secrets = (token, hash_token(token), old_token, hash_token(old_token))
    out = capsys.readouterr()
    assert "tenancy.invitation_resent" in out.out + out.err
    for text in (listed.content.decode(), out.out + out.err, repr(row(resent.json()["id"]))):
        assert not [secret for secret in secrets if secret in text]
    for event in recorded.events:
        assert not [secret for secret in secrets if secret in repr(event)]
        assert "ana@hub.test" not in repr(event)
    assert "ana@hub.test" not in out.out + out.err
    ana = new_user("ana")
    with pytest.raises(InvitationInvalid) as refused:
        accept_by_token(old_token, invitee(ana))
    assert refused.value.problem_reason == "revoked"
    assert token not in str(refused.value.detail)


def test_AC_TEN_24_revoke_answers_no_token(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    invitation, token = issue(org_a, "ana@hub.test")

    response = manage(client, owner, org_a, invitation.pk, "revoke")

    assert response.status_code == 200, response.content
    assert "accept_url" not in response.json()
    assert token not in response.content.decode()
    assert hash_token(token) not in response.content.decode()


# --- Revoke (design.md §4.3) ---


def test_RF_TEN_05_revoke_pending(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    admin, _ = member(org_a, Role.ADMIN)
    invitation, token = issue(org_a, "ana@hub.test", Role.VIEWER)
    recorded.clear()

    response = manage(client, admin, org_a, invitation.pk, "revoke")

    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["id"], body["status"], body["allowed_actions"]) == (
        str(invitation.pk),
        "revoked",
        [],
    )
    assert response["Cache-Control"] == "no-store"
    stored = row(invitation.pk)
    assert (stored.status, stored.revoked_reason, stored.revoked_by_id) == (
        "revoked",
        "revoked",
        admin.pk,
    )
    (event,) = recorded.events
    assert (event.action, event.reason, event.metadata) == (
        "invitation.revoked",
        "revoked",
        {"invitation_id": str(invitation.pk), "role": "viewer"},
    )
    assert (event.actor.kind, event.actor.id) == (AuditActorKind.USER, admin.pk)
    with pytest.raises(InvitationInvalid) as refused:
        accept_by_token(token, invitee(new_user("ana")))
    assert refused.value.problem_reason == "revoked"


def test_Q_221_revoke_allowed_when_suspended_resend_is_not(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    first, _ = issue(org_a, "ana@hub.test")
    second, _ = issue(org_a, "beto@hub.test")
    Organization.objects.unscoped(PLATFORM).filter(pk=org_a.pk).update(status="suspended")

    resent = manage(client, owner, org_a, first.pk, "resend")
    revoked = manage(client, owner, org_a, second.pk, "revoke")

    assert problem(resent) == (409, "organization_suspended")
    assert status_of(first) == InvitationStatus.PENDING
    assert revoked.status_code == 200, revoked.content
    assert status_of(second) == InvitationStatus.REVOKED


def test_RF_TEN_05_list_after_resend_has_only_the_new_one(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    created = invite(client, owner, org_a, {"email": "ana@hub.test", "role": "viewer"})

    resent = manage(client, owner, org_a, created.json()["id"], "resend")
    listed = client.get(INVITATIONS, headers=as_member(owner, org_a.id)).json()

    assert [r["id"] for r in listed["results"]] == [resent.json()["id"]]


def test_RNF_TEN_03_contract_of_resend_and_revoke() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    resend = contract["paths"]["/api/invitations/{id}/resend/"]["post"]
    revoke_ = contract["paths"]["/api/invitations/{id}/revoke/"]["post"]
    assert set(resend["responses"]) >= {"201", "400", "403", "404", "409", "503"}
    assert set(revoke_["responses"]) >= {"200", "400", "403", "404", "409", "503"}
    created = "#/components/schemas/CreatedInvitation"
    row_ = "#/components/schemas/OrganizationInvitation"
    assert resend["responses"]["201"]["content"]["application/json"]["schema"]["$ref"] == created
    assert revoke_["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == row_
    for operation in (resend, revoke_):
        assert "requestBody" not in operation
        assert {p["name"] for p in operation["parameters"]} == {"id", "X-Organization-Id"}
    assert contract["info"]["version"] == "0.17.0"
