"""``POST /api/invitations/``: invite somebody to the active organization (RF-TEN-05, §4.3, §6).

AC-TEN-15 (RN-TEN-13): an admin never invites an ``owner``. AC-TEN-20: an active member is
``already_member``. AC-TEN-24 (RNF-TEN-03): the token in clear is only in this ``201``, in the
fragment of ``accept_url``, and never in a log, an error, the audit or the listing. AC-TEN-26
(RN-TEN-12): a second ``pending`` one for the same email is ``invitation_pending``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
import yaml
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.audit.port import AuditActorKind
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus, hash_token
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services import invitations as service
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.invitation_api_setup import (
    INVITATIONS,
    invitations_of,
    invite,
    token_of,
)
from tests.tenancy.api.membership_setup import member, recorded
from tests.tenancy.api.probe import PLATFORM, as_member, bearer_of, new_org, new_user, revoke
from tests.tenancy.invitation_setup import issue, make_due, status_of

pytestmark = pytest.mark.django_db

__all__ = ["recorded"]  # the fixture, imported for the tests below

OPERATOR = {"email": "nueva@hub.test", "role": "operator"}


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


def problem(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


# --- AC-TEN-15 / AC-TEN-16 ---


def test_AC_TEN_15_admin_cannot_invite_owner(client: Client, org_a: Organization) -> None:
    admin, _ = member(org_a, Role.ADMIN)

    response = invite(client, admin, org_a, {"email": "jefa@hub.test", "role": "owner"})

    assert problem(response) == (403, "forbidden")
    assert invitations_of(org_a) == []


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_15_admin_invites_any_role_but_owner(
    client: Client, org_a: Organization, role: Role
) -> None:
    admin, _ = member(org_a, Role.ADMIN)

    response = invite(client, admin, org_a, {"email": "x@hub.test", "role": role.value})

    assert response.status_code == 201, response.content
    assert invitations_of(org_a) == [("x@hub.test", role.value, "pending")]


def test_AC_TEN_15_owner_invites_owner(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = invite(client, owner, org_a, {"email": "socia@hub.test", "role": "owner"})

    assert response.status_code == 201, response.content
    assert response.json()["role"] == "owner"


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_16_operator_and_viewer_cannot_invite(
    client: Client, org_a: Organization, role: Role
) -> None:
    user, _ = member(org_a, role)

    response = invite(client, user, org_a, OPERATOR)

    assert problem(response) == (403, "forbidden")
    assert invitations_of(org_a) == []


# --- AC-TEN-20 ---


def test_AC_TEN_20_already_member(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)
    member(org_a, Role.VIEWER, "ana")

    response = invite(client, owner, org_a, {"email": "  ANA@hub.test ", "role": "operator"})

    assert problem(response) == (409, "already_member")
    assert "ana@hub.test" not in response.content.decode().lower()
    assert invitations_of(org_a) == []


def test_AC_TEN_20_member_of_another_org_or_revoked_is_invited(
    client: Client, org_a: Organization
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    member(new_org("B"), Role.ADMIN, "beto")
    _, gone = member(org_a, Role.OPERATOR, "caro")
    revoke(org_a, gone)

    for email in ("beto@hub.test", "caro@hub.test"):
        response = invite(client, owner, org_a, {"email": email, "role": "viewer"})
        assert response.status_code == 201, response.content

    assert [row[0] for row in invitations_of(org_a)] == ["beto@hub.test", "caro@hub.test"]


# --- AC-TEN-24 ---


def test_AC_TEN_24_token_only_in_create_response(
    client: Client,
    org_a: Organization,
    recorded: RecordingSink,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    capsys.readouterr()

    created = invite(client, owner, org_a, {"email": "ana@hub.test", "role": "operator"})
    again = invite(client, owner, org_a, {"email": "ana@hub.test", "role": "operator"})
    listed = client.get(INVITATIONS, headers=as_member(owner, org_a.id))

    assert created.status_code == 201, created.content
    token = token_of(created)
    secrets = (token, hash_token(token))
    stored = Invitation.objects.unscoped(PLATFORM).get(pk=created.json()["id"])
    assert stored.token_hash == hash_token(token)  # only its hash is kept (RNF-TEN-03)
    assert problem(again) == (409, "invitation_pending")
    assert listed.status_code == 200
    out = capsys.readouterr()
    for text in (again.content.decode(), listed.content.decode(), out.out + out.err, repr(stored)):
        assert not [secret for secret in secrets if secret in text]
    assert "tenancy.invitation_created" in out.out + out.err
    assert "ana@hub.test" not in out.out + out.err
    for event in recorded.events:
        assert not [secret for secret in secrets if secret in repr(event)]
        assert "ana@hub.test" not in repr(event)
    assert created["Cache-Control"] == "no-store"
    # The link is real: its token accepts the invitation (the fragment is all the app sends back).
    ana = new_user("ana")
    accepted = client.post(
        "/api/invitations/accept/",
        data={"token": token},
        content_type="application/json",
        headers=bearer_of(ana),
    )
    assert accepted.status_code == 200, accepted.content


def test_AC_TEN_24_created_event_and_response(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = invite(client, owner, org_a, {"email": " X@Dominio.com ", "role": "admin"})

    body = response.json()
    assert set(body) == {
        "id",
        "email",
        "role",
        "status",
        "purpose",
        "expires_at",
        "invited_by",
        "created_at",
        "allowed_actions",
        "accept_url",
    }
    assert (body["email"], body["role"], body["status"], body["purpose"]) == (
        "x@dominio.com",
        "admin",
        "pending",
        "standard",
    )
    assert body["invited_by"] == {"id": str(owner.pk), "email": owner.email, "name": ""}
    assert body["allowed_actions"] == ["invitation.resend", "invitation.revoke"]
    stored = Invitation.objects.unscoped(PLATFORM).get(pk=body["id"])
    assert stored.expires_at - stored.created_at == pytest.approx(
        timedelta(days=7), abs=timedelta(seconds=5)
    )
    (event,) = [e for e in recorded.events if e.action == "invitation.created"]
    assert (event.actor.kind, event.actor.id) == (AuditActorKind.USER, owner.pk)
    assert event.organization_id == org_a.id
    assert event.metadata == {"invitation_id": body["id"], "role": "admin", "purpose": "standard"}


# --- AC-TEN-26 ---


def test_AC_TEN_26_second_pending_rejected(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    first = invite(client, owner, org_a, {"email": "x@dominio.com", "role": "operator"})
    recorded.clear()

    second = invite(client, owner, org_a, {"email": "X@DOMINIO.COM ", "role": "viewer"})

    assert first.status_code == 201
    assert problem(second) == (409, "invitation_pending")
    assert invitations_of(org_a) == [("x@dominio.com", "operator", "pending")]
    assert recorded.events == []


def test_AC_TEN_26_expired_pending_is_closed_and_replaced(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    old, _ = issue(org_a, "x@dominio.com")
    make_due(old)

    response = invite(client, owner, org_a, {"email": "x@dominio.com", "role": "viewer"})

    assert response.status_code == 201, response.content
    assert status_of(old) == InvitationStatus.EXPIRED
    assert invitations_of(org_a) == [
        ("x@dominio.com", "operator", "expired"),
        ("x@dominio.com", "viewer", "pending"),
    ]
    expired = [e for e in recorded.events if e.action == "invitation.expired"]
    assert [(e.actor.kind, e.metadata) for e in expired] == [
        (AuditActorKind.SYSTEM, {"invitation_id": str(old.pk)})
    ]


def test_AC_TEN_26_the_unique_constraint_is_invitation_pending(
    client: Client, org_a: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``pending`` one the check did not see (written without the lock): the database's net."""
    owner, _ = member(org_a, Role.OWNER)
    issue(org_a, "x@dominio.com")
    monkeypatch.setattr(service, "_expire_or_refuse_pending", lambda *args: None)

    response = invite(client, owner, org_a, {"email": "x@dominio.com", "role": "viewer"})

    assert problem(response) == (409, "invitation_pending")
    assert invitations_of(org_a) == [("x@dominio.com", "operator", "pending")]


# --- Input (design.md §5, §6) ---


@pytest.mark.parametrize(
    "email", ["no-es-un-email", "", "   ", "a@b@c.com", f"{'a' * 250}@hub.test", 5, None]
)
def test_RN_TEN_12_invalid_email_is_a_validation_error(
    client: Client, org_a: Organization, email: Any
) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = invite(client, owner, org_a, {"email": email, "role": "viewer"})

    assert problem(response) == (400, "validation_error")
    assert [error["field"] for error in response.json()["errors"]] == ["email"]
    if isinstance(email, str) and email.strip():
        assert email not in response.content.decode()
    assert invitations_of(org_a) == []


@pytest.mark.parametrize("extra", ["organization_id", "status", "token", "purpose"])
def test_RN_TEN_12_body_is_strict(client: Client, org_a: Organization, extra: str) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = invite(client, owner, org_a, {**OPERATOR, extra: "x"})

    assert problem(response) == (400, "validation_error")
    assert response.json()["errors"] == [
        {"field": extra, "code": "unknown_field", "message": "Este campo no se acepta."}
    ]
    assert invitations_of(org_a) == []


def test_RN_TEN_12_unknown_role_is_a_validation_error(client: Client, org_a: Organization) -> None:
    owner, _ = member(org_a, Role.OWNER)

    response = invite(client, owner, org_a, {"email": "x@hub.test", "role": "superadmin"})

    assert problem(response) == (400, "validation_error")
    assert invitations_of(org_a) == []


def test_AC_TEN_28_suspended_organization_cannot_invite(client: Client) -> None:
    org = new_org("A")
    owner, _ = member(org, Role.OWNER)
    Organization.objects.unscoped(PLATFORM).filter(pk=org.pk).update(status="suspended")

    response = invite(client, owner, org, OPERATOR)

    assert problem(response) == (409, "organization_suspended")
    assert invitations_of(org) == []


def test_RNF_TEN_03_without_frontend_base_url_nothing_is_written(
    org_a: Organization, settings: SettingsWrapper
) -> None:
    owner, _ = member(org_a, Role.OWNER)
    settings.FRONTEND_BASE_URL = ""

    with pytest.raises(ImproperlyConfigured):
        service.accept_base_url()
    response = invite(Client(raise_request_exception=False), owner, org_a, OPERATOR)

    assert problem(response) == (500, "internal_error")
    assert invitations_of(org_a) == []


def test_RNF_TEN_03_contract_publishes_accept_url_only_on_create() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operation = contract["paths"][INVITATIONS]["post"]
    assert set(operation["responses"]) >= {"201", "400", "403", "409", "503"}
    assert [p["name"] for p in operation["parameters"]] == ["X-Organization-Id"]
    schemas = contract["components"]["schemas"]
    assert set(schemas["InvitationCreateRequest"]["properties"]) == {"email", "role"}
    assert "accept_url" in schemas["CreatedInvitation"]["properties"]
    row = schemas["OrganizationInvitation"]["properties"]
    assert "accept_url" not in row
    assert not {"token", "token_hash"} & set(row)
    assert schemas["InvitationStatusEnum"]["enum"] == ["pending", "accepted", "revoked", "expired"]
    assert contract["info"]["version"] == "0.16.0"
