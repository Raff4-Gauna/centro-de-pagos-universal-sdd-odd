"""``POST /api/invitations/accept/`` (design.md §3.5, §4.4, §6): AC-TEN-17/18/19, RNF-TEN-03.

The route is exempt from the active organization: it needs no ``X-Organization-Id`` and ignores
one, because the organization is the invitation's. The token never shows up in a response, an
error or a log (C-06); the refusals carry ``reason`` in the problem envelope.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.tenancy.domain.invitations import InvitationStatus, hash_token
from apps.tenancy.models import Organization
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import HEADER, PLATFORM, add_member, bearer_of, new_org, new_user
from tests.tenancy.invitation_setup import issue, memberships, set_status, status_of

pytestmark = pytest.mark.django_db

ACCEPT = "/api/invitations/accept/"


def post(client: Client, body: Any, **headers: str) -> Any:
    return client.post(ACCEPT, body, content_type="application/json", headers=headers)


def assert_invalid(response: Any, reason: str) -> None:
    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert (body["code"], body["reason"]) == ("invitation_invalid", reason)
    assert body["title"] == "Invitación inválida"


def test_AC_TEN_17_accept_through_the_route_ignores_the_header(client: Client) -> None:
    a, b = new_org("A"), new_org("B")
    ana = new_user("ana")
    add_member(a, ana, Role.OWNER)
    invitation, token = issue(b, "ana@hub.test", Role.VIEWER)

    response = post(client, {"token": token}, **bearer_of(ana), **{HEADER: str(a.id)})

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    [_, (organization_id, role, _, source)] = memberships(ana)
    assert body == {
        "organization": {"id": str(b.id), "name": "B"},
        "role": "viewer",
        "membership_id": body["membership_id"],
    }
    assert (organization_id, role, source) == (b.id, "viewer", invitation.id)
    assert token not in response.content.decode()


def test_AC_TEN_17_second_use_is_used(client: Client) -> None:
    _, token = issue(new_org("A"), "ana@hub.test")
    ana = new_user("ana")
    assert post(client, {"token": token}, **bearer_of(ana)).status_code == 200
    assert_invalid(post(client, {"token": token}, **bearer_of(ana)), "used")
    assert len(memberships(ana)) == 1


def test_AC_TEN_18_other_email_through_the_route(client: Client) -> None:
    invitation, token = issue(new_org("A"), "x@dominio.com")
    beto = new_user("beto")
    assert_invalid(post(client, {"token": token}, **bearer_of(beto)), "email_mismatch")
    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(beto) == []


def test_AC_TEN_19_revoked_through_the_route(client: Client) -> None:
    invitation, token = issue(new_org("A"), "ana@hub.test")
    set_status(invitation, InvitationStatus.REVOKED)
    assert_invalid(post(client, {"token": token}, **bearer_of(new_user("ana"))), "revoked")


def test_AC_TEN_17_unknown_token_is_not_found(client: Client) -> None:
    assert_invalid(post(client, {"token": "nope"}, **bearer_of(new_user("ana"))), "not_found")


def test_RN_TEN_07_already_member_is_409(client: Client) -> None:
    org = new_org("A")
    ana = new_user("ana")
    add_member(org, ana, Role.VIEWER)
    _, token = issue(org, "ana@hub.test")
    response = post(client, {"token": token}, **bearer_of(ana))
    assert (response.status_code, response.json()["code"]) == (409, "already_member")
    assert "reason" not in response.json()


def test_RN_TEN_18_suspended_is_409(client: Client) -> None:
    org = new_org("A")
    _, token = issue(org, "ana@hub.test")
    Organization.objects.unscoped(PLATFORM).filter(pk=org.pk).update(
        status=OrgStatus.SUSPENDED.value
    )
    response = post(client, {"token": token}, **bearer_of(new_user("ana")))
    assert (response.status_code, response.json()["code"]) == (409, "organization_suspended")


def test_RN_TEN_11_anonymous_is_401(client: Client) -> None:
    invitation, token = issue(new_org("A"), "ana@hub.test")
    response = post(client, {"token": token})
    assert (response.status_code, response.json()["code"]) == (401, "unauthenticated")
    assert status_of(invitation) == InvitationStatus.PENDING


@pytest.mark.parametrize(
    "body", [{}, {"token": ""}, {"token": "a" * 129}], ids=["missing", "empty", "too-long"]
)
def test_RNF_TEN_03_bad_body_is_a_validation_error_without_the_input(
    client: Client, body: dict[str, str]
) -> None:
    response = post(client, body, **bearer_of(new_user("ana")))
    assert (response.status_code, response.json()["code"]) == (400, "validation_error")
    assert "a" * 129 not in response.content.decode()


@pytest.mark.parametrize("extra", ["organization_id", "status", "role"])
def test_RN_TEN_12_unknown_field_is_refused_and_nothing_is_accepted(
    client: Client, extra: str
) -> None:
    """Strict body (design.md §6): a smuggled key is ``unknown_field``, never ignored."""
    invitation, token = issue(new_org("A"), "ana@hub.test")
    ana = new_user("ana")
    response = post(client, {"token": token, extra: "owner"}, **bearer_of(ana))
    assert (response.status_code, response.json()["code"]) == (400, "validation_error")
    assert response.json()["errors"] == [
        {"field": extra, "code": "unknown_field", "message": "Este campo no se acepta."}
    ]
    assert token not in response.content.decode()
    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(ana) == []


def test_RNF_TEN_03_token_and_email_never_reach_the_logs(
    client: Client, capsys: pytest.CaptureFixture[str]
) -> None:
    _, token = issue(new_org("A"), "x@dominio.com")
    beto = new_user("beto")
    capsys.readouterr()
    post(client, {"token": token}, **bearer_of(beto))  # refused: email_mismatch
    _, other = issue(new_org("B"), "beto@hub.test")
    post(client, {"token": other}, **bearer_of(beto))  # accepted
    out = capsys.readouterr()
    logged = out.out + out.err
    assert "tenancy.invitation_refused" in logged
    assert "tenancy.invitation_accepted" in logged
    for secret in (token, other, hash_token(token), hash_token(other)):
        assert secret not in logged
    assert "x@dominio.com" not in logged
    assert "beto@hub.test" not in logged


def test_RNF_TEN_03_contract_declares_token_write_only_and_the_refusals() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operation = contract["paths"][ACCEPT]["post"]
    assert set(operation["responses"]) >= {"200", "400", "401", "409"}
    assert "parameters" not in operation  # no X-Organization-Id: exempt (design.md §3.5)
    request = contract["components"]["schemas"]["InvitationAcceptRequest"]
    assert set(request["properties"]) == {"token"}
    assert "InvitationAccept" not in contract["components"]["schemas"]  # never a response
    accepted = contract["components"]["schemas"]["AcceptedInvitation"]
    assert set(accepted["properties"]) == {"organization", "role", "membership_id"}
    assert contract["info"]["version"] == "0.17.0"
