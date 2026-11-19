"""``GET/PATCH /api/organizations/current/``: the data of the active organization (RF-TEN-03).

Q-209: ``name`` (required), ``legal_name``, ``tax_id`` (CUIT) and ``timezone``; owner and admin
edit, every role reads. AC-TEN-29: nobody of the organization, not even its owner, changes its
status through the API (only the operator's command does, RN-TEN-18). AC-TEN-28: a suspended one is
still read, and not edited. The route is a ``TenantViewSet``: the cross-tenant suite attacks it from
another organization (``tests/cross_tenant/cases/tenancy.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.audit.port import AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.identity.models import User
from apps.tenancy.domain.permissions import TenancyAction
from apps.tenancy.models import Membership, Organization
from apps.tenancy.models.organization import DEFAULT_TIMEZONE
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import PLATFORM, add_member, as_member, new_org, new_user

pytestmark = pytest.mark.django_db

CURRENT = "/api/organizations/current/"
CUIT = "20123456786"
EVERY_ACTION = [action.value for action in TenancyAction]
MANAGER_ACTIONS = EVERY_ACTION
READER_ACTIONS = ["org.read", "member.leave", "branch.read"]
SUSPENDED_MANAGER_ACTIONS = [
    "org.read",
    "member.list",
    "member.revoke",
    "member.leave",
    "invitation.list",
    "invitation.revoke",
    "branch.read",
]


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


@pytest.fixture
def acme() -> Organization:
    return new_org("Acme")


def member(organization: Organization, role: Role) -> tuple[User, Membership]:
    user = new_user(f"{role.value}-{organization.name}")
    return user, add_member(organization, user, role)


def saved(organization: Organization) -> dict[str, Any]:
    fields = ("name", "legal_name", "tax_id", "timezone", "status")
    row = Organization.objects.unscoped(PLATFORM).values(*fields).get(pk=organization.pk)
    return dict(row)


def patch(client: Client, user: User, organization: Organization, body: object) -> Any:
    return client.patch(
        CURRENT,
        data=body,
        content_type="application/json",
        headers=as_member(user, organization.id),
    )


def field_codes(response: Any) -> dict[str, str]:
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    return {error["field"]: error["code"] for error in response.json()["errors"]}


@pytest.mark.parametrize("role", list(Role))
def test_RF_TEN_03_every_role_reads(client: Client, acme: Organization, role: Role) -> None:
    user, membership = member(acme, role)
    response = client.get(CURRENT, headers=as_member(user, acme.id))

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    manager = role in (Role.OWNER, Role.ADMIN)
    invitable = {
        Role.OWNER: ["owner", "admin", "operator", "viewer"],
        Role.ADMIN: ["admin", "operator", "viewer"],
    }.get(role, [])
    assert response.json() == {
        "id": str(acme.id),
        "name": "Acme",
        "legal_name": "",
        "tax_id": "",
        "timezone": DEFAULT_TIMEZONE,
        "status": "active",
        "my_role": role.value,
        "my_membership_id": str(membership.id),
        "allowed_actions": MANAGER_ACTIONS if manager else READER_ACTIONS,
        "invitable_roles": invitable,
    }


def test_AC_TEN_28_suspended_is_read_without_writes(client: Client) -> None:
    suspended = new_org("Pausada", OrgStatus.SUSPENDED)
    owner, _ = member(suspended, Role.OWNER)
    body = client.get(CURRENT, headers=as_member(owner, suspended.id)).json()

    assert body["status"] == "suspended"
    assert body["allowed_actions"] == SUSPENDED_MANAGER_ACTIONS
    assert body["invitable_roles"] == []


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_RF_TEN_03_owner_and_admin_edit(
    client: Client, acme: Organization, recorded: RecordingSink, role: Role
) -> None:
    user, membership = member(acme, role)
    body = {
        "name": "  Acme SRL  ",
        "legal_name": " Acme Sociedad de Responsabilidad Limitada ",
        "tax_id": "20-12345678-6",
        "timezone": "America/Argentina/Cordoba",
    }
    response = patch(client, user, acme, body)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    expected = {
        "name": "Acme SRL",
        "legal_name": "Acme Sociedad de Responsabilidad Limitada",
        "tax_id": CUIT,
        "timezone": "America/Argentina/Cordoba",
        "status": "active",
    }
    assert saved(acme) == expected
    assert {key: response.json()[key] for key in expected} == expected
    assert response.json()["my_membership_id"] == str(membership.id)
    [event] = recorded.events
    assert (event.action, event.organization_id) == ("organization.updated", acme.id)
    assert (event.actor.kind, event.actor.id) == (AuditActorKind.USER, user.pk)
    assert event.metadata == {"changed_fields": ["name", "legal_name", "tax_id", "timezone"]}


def test_RF_TEN_03_only_the_fields_sent_change(
    client: Client, acme: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(acme, Role.OWNER)
    assert patch(client, owner, acme, {"tax_id": CUIT}).status_code == 200
    assert patch(client, owner, acme, {"legal_name": "Acme SA"}).status_code == 200

    assert saved(acme) == {
        "name": "Acme",
        "legal_name": "Acme SA",
        "tax_id": CUIT,
        "timezone": DEFAULT_TIMEZONE,
        "status": "active",
    }
    changed = [event.metadata["changed_fields"] for event in recorded.events]
    assert changed == [["tax_id"], ["legal_name"]]


def test_RF_TEN_03_empty_clears_the_optional_fields(client: Client, acme: Organization) -> None:
    owner, _ = member(acme, Role.OWNER)
    patch(client, owner, acme, {"legal_name": "Acme SA", "tax_id": CUIT})
    response = patch(client, owner, acme, {"legal_name": "", "tax_id": "  "})

    assert response.status_code == 200
    assert (saved(acme)["legal_name"], saved(acme)["tax_id"]) == ("", "")


def test_RF_TEN_03_same_values_change_nothing(
    client: Client, acme: Organization, recorded: RecordingSink
) -> None:
    owner, _ = member(acme, Role.OWNER)
    before = Organization.objects.unscoped(PLATFORM).get(pk=acme.pk).updated_at
    for body in ({"name": " Acme "}, {}, {"timezone": DEFAULT_TIMEZONE}):
        assert patch(client, owner, acme, body).status_code == 200

    assert Organization.objects.unscoped(PLATFORM).get(pk=acme.pk).updated_at == before
    assert recorded.events == []


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_RF_TEN_03_operator_and_viewer_do_not_edit(
    client: Client, acme: Organization, recorded: RecordingSink, role: Role
) -> None:
    user, _ = member(acme, role)
    before = saved(acme)
    response = patch(client, user, acme, {"name": "Otra"})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert saved(acme) == before
    assert recorded.events == []


@pytest.mark.parametrize(
    ("body", "codes"),
    [
        ({"name": ""}, {"name": "blank"}),
        ({"name": "   "}, {"name": "blank"}),
        ({"name": None}, {"name": "null"}),
        ({"name": "x" * 121}, {"name": "max_length"}),
        ({"legal_name": "x" * 201}, {"legal_name": "max_length"}),
        ({"tax_id": "20123456785"}, {"tax_id": "invalid"}),
        ({"tax_id": "20.12345678.6"}, {"tax_id": "invalid"}),
        ({"timezone": "America/Gotham"}, {"timezone": "invalid"}),
        ({"timezone": ""}, {"timezone": "blank"}),
        ({"name": ["Acme"]}, {"name": "invalid"}),
        (
            {"name": "Bien", "tax_id": "1", "timezone": "Mars/Base"},
            {"tax_id": "invalid", "timezone": "invalid"},
        ),
    ],
)
def test_RF_TEN_03_invalid_values_are_rejected(
    client: Client,
    acme: Organization,
    recorded: RecordingSink,
    body: dict[str, Any],
    codes: dict[str, str],
) -> None:
    owner, _ = member(acme, Role.OWNER)
    before = saved(acme)
    response = patch(client, owner, acme, body)

    assert field_codes(response) == codes
    assert saved(acme) == before
    assert recorded.events == []


def test_RF_TEN_03_errors_do_not_echo_the_tax_id(client: Client, acme: Organization) -> None:
    owner, _ = member(acme, Role.OWNER)
    response = patch(client, owner, acme, {"tax_id": "27999999990"})

    assert field_codes(response) == {"tax_id": "invalid"}
    assert "27999999990" not in response.content.decode()


@pytest.mark.parametrize(
    "body",
    [
        {"status": "suspended"},
        {"status": "suspended", "name": "Acme"},
        {"id": "00000000-0000-0000-0000-000000000000"},
        {"organization_id": "00000000-0000-0000-0000-000000000000"},
        {"status_changed_at": None},
        {"platform_creation_key": "otra"},
    ],
)
def test_AC_TEN_29_status_is_not_writable(
    client: Client, acme: Organization, recorded: RecordingSink, body: dict[str, Any]
) -> None:
    owner, _ = member(acme, Role.OWNER)
    before = saved(acme)
    response = patch(client, owner, acme, body)

    unknown = sorted(key for key in body if key != "name")
    assert field_codes(response) == dict.fromkeys(unknown, "unknown_field")
    assert saved(acme) == before
    assert recorded.events == []


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_AC_TEN_29_no_other_method_changes_the_status(
    client: Client, acme: Organization, method: str
) -> None:
    owner, _ = member(acme, Role.OWNER)
    send = getattr(client, method)
    response = send(
        CURRENT,
        data={"status": "suspended"},
        content_type="application/json",
        headers=as_member(owner, acme.id),
    )

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert saved(acme)["status"] == "active"


def test_AC_TEN_29_owner_of_a_suspended_one_cannot_reactivate_it(
    client: Client, recorded: RecordingSink
) -> None:
    suspended = new_org("Pausada", OrgStatus.SUSPENDED)
    owner, _ = member(suspended, Role.OWNER)
    for body in ({"status": "active"}, {"name": "Otra"}):
        response = patch(client, owner, suspended, body)
        assert response.status_code == 409
        assert response.json()["code"] == "organization_suspended"

    assert (saved(suspended)["name"], saved(suspended)["status"]) == ("Pausada", "suspended")
    assert recorded.events == []


def test_RF_TEN_03_needs_the_active_organization(client: Client, acme: Organization) -> None:
    owner, _ = member(acme, Role.OWNER)
    response = client.get(CURRENT, headers=as_member(owner, None))

    assert response.status_code == 400
    assert response.json()["code"] == "organization_required"


def test_RF_TEN_03_contract_reads_and_patches_the_active_organization() -> None:
    contract = yaml.safe_load(CONTRACT.read_bytes())
    operations = contract["paths"][CURRENT]
    schemas = contract["components"]["schemas"]

    assert sorted(operations) == ["get", "patch"]
    for operation in operations.values():
        [header] = [p for p in operation["parameters"] if p["in"] == "header"]
        assert (header["name"], header["required"]) == ("X-Organization-Id", True)
    request = operations["patch"]["requestBody"]["content"]["application/json"]["schema"]
    update = schemas[request["$ref"].rsplit("/", 1)[1]]
    assert set(update["properties"]) == {"name", "legal_name", "tax_id", "timezone"}
    assert "required" not in update
    response = operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    current = schemas[response["$ref"].rsplit("/", 1)[1]]
    assert set(current["required"]) == {
        "id",
        "name",
        "legal_name",
        "tax_id",
        "timezone",
        "status",
        "my_role",
        "my_membership_id",
        "allowed_actions",
        "invitable_roles",
    }
    [actions] = current["properties"]["allowed_actions"]["items"].values()
    assert actions == "#/components/schemas/TenancyActionEnum"
    assert schemas["TenancyActionEnum"]["enum"] == EVERY_ACTION
    assert contract["info"]["version"] == "0.10.0"
