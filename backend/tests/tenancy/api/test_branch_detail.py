"""``GET``/``PATCH /api/branches/{id}/``: see and edit one branch of the active organization.

RF-TEN-06, design.md §6. AC-TEN-01: a branch of another organization is ``404 not_found`` by id,
the same body as one that does not exist, and nothing of it changes. AC-TEN-05: the role is read on
every request, so an admin demoted to viewer cannot edit in the next one. AC-TEN-16: operator and
viewer see but do not edit. AC-TEN-38: a name (without case) or a code another active branch uses is
``409 conflict``. The body is strict, as in the creation (AC-TEN-07). AC-TEN-30: no route deletes.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import yaml
from django.test import Client

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import tenant_scope
from apps.tenancy.api.serializers.branches import BranchUpdateSerializer
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Branch, Membership, Organization
from apps.tenancy.services.branches import CREATE_FIELDS
from tests.contract.test_AC_PLT_23_openapi_up_to_date import CONTRACT
from tests.tenancy.api.probe import add_member, as_member, new_org, new_user, platform_ctx
from tests.tenancy.api.test_branches import codes_of, member, names_in, seed

pytestmark = pytest.mark.django_db


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


@pytest.fixture
def org_a() -> Organization:
    return new_org("A")


@pytest.fixture
def org_b() -> Organization:
    return new_org("B")


def detail(branch: Branch | uuid.UUID) -> str:
    return f"/api/branches/{branch.pk if isinstance(branch, Branch) else branch}/"


def patch(client: Client, headers: dict[str, str], branch: Branch | uuid.UUID, body: Any) -> Any:
    return client.patch(
        detail(branch), data=json.dumps(body), content_type="application/json", headers=headers
    )


def without_request_id(response: Any) -> dict[str, Any]:
    body = dict(response.json())
    body.pop("request_id")
    return body


# --- AC-TEN-01 ---


def test_AC_TEN_01_other_org_branch_is_404(
    client: Client, org_a: Organization, org_b: Organization, recorded: RecordingSink
) -> None:
    seed(org_a, "Centro de A")
    foreign = seed(org_b, "Centro", "C01")
    headers = as_member(member(org_a, Role.OWNER), org_a.id)
    before = names_in(org_b)

    answers = [
        client.get(detail(foreign), headers=headers),
        patch(client, headers, foreign, {"name": "Tomada"}),
        client.post(f"{detail(foreign)}deactivate/", headers=headers),
        client.post(f"{detail(foreign)}reactivate/", headers=headers),
    ]
    unknown = client.get(detail(uuid.uuid4()), headers=headers)

    assert [answer.status_code for answer in answers] == [404, 404, 404, 404]
    assert {answer.json()["code"] for answer in answers} == {"not_found"}
    assert without_request_id(answers[0]) == without_request_id(unknown)
    assert all(str(foreign.pk) not in answer.content.decode() for answer in answers)
    assert names_in(org_b) == before
    assert recorded.events == []
    listed = client.get("/api/branches/", headers=headers).json()["results"]
    assert [b["name"] for b in listed] == ["Centro de A"]


def test_AC_TEN_01_malformed_id_is_404(client: Client, org_a: Organization) -> None:
    headers = as_member(member(org_a, Role.OWNER), org_a.id)

    assert client.get("/api/branches/not-a-uuid/", headers=headers).status_code == 404
    assert client.get(f"/api/branches/{'-' * 36}/", headers=headers).status_code == 404


def test_RF_TEN_06_any_role_sees_one_branch(client: Client, org_a: Organization) -> None:
    branch = seed(org_a, "Centro", "C01")

    response = client.get(detail(branch), headers=as_member(member(org_a, Role.VIEWER), org_a.id))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(branch.pk),
        "name": "Centro",
        "code": "C01",
        "address": "",
        "is_active": True,
        "deactivated_at": None,
    }


# --- AC-TEN-05 / AC-TEN-16 ---


def test_AC_TEN_05_demoted_admin_cannot_edit_branch(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro")
    admin = new_user("admin-a")
    membership = add_member(org_a, admin, Role.ADMIN)
    headers = as_member(admin, org_a.id)  # one session for both requests
    assert patch(client, headers, branch, {"name": "Centro 1"}).status_code == 200
    ctx = platform_ctx(org_a)
    with tenant_scope(ctx):
        Membership.objects.for_tenant(ctx).filter(pk=membership.pk).update(role=Role.VIEWER.value)
    recorded.clear()

    response = patch(client, headers, branch, {"name": "Centro 2"})

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert names_in(org_a) == [("Centro 1", "", True)]
    assert recorded.events == []


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_16_viewer_cannot_edit_branch(
    client: Client, org_a: Organization, role: Role
) -> None:
    branch = seed(org_a, "Centro")
    headers = as_member(member(org_a, role), org_a.id)

    assert patch(client, headers, branch, {"name": "Otro"}).status_code == 403
    assert client.post(f"{detail(branch)}deactivate/", headers=headers).status_code == 403
    assert client.post(f"{detail(branch)}reactivate/", headers=headers).status_code == 403
    assert names_in(org_a) == [("Centro", "", True)]


# --- RF-TEN-06: the edit ---


def test_RF_TEN_06_patch_edits_and_audits_the_changed_fields(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro", "C01")
    owner = member(org_a, Role.OWNER)

    response = patch(
        client, as_member(owner, org_a.id), branch, {"name": " Centro ", "address": " Calle 1 "}
    )

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["address"]) == ("Centro", "Calle 1")
    assert names_in(org_a) == [("Centro", "C01", True)]
    [event] = recorded.events
    assert event.action == TenancyAuditAction.BRANCH_UPDATED
    assert (event.organization_id, event.actor.id) == (org_a.id, owner.pk)
    assert event.metadata == {"branch_id": str(branch.pk), "changed_fields": ["address"]}


def test_RF_TEN_06_patch_without_changes_writes_nothing(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro", "C01")
    headers = as_member(member(org_a, Role.ADMIN), org_a.id)

    assert patch(client, headers, branch, {"name": "Centro", "code": "C01"}).status_code == 200
    assert patch(client, headers, branch, {}).status_code == 200
    assert recorded.events == []


@pytest.mark.parametrize(
    ("body", "codes"),
    [
        ({"name": "  "}, {"name": "blank"}),
        ({"name": None}, {"name": "invalid"}),
        ({"code": "x" * 33}, {"code": "max_length"}),
        ({"address": "x" * 256}, {"address": "max_length"}),
        ({"is_active": False}, {"is_active": "unknown_field"}),
        (
            {"organization_id": "x", "id": "y"},
            {"organization_id": "unknown_field", "id": "unknown_field"},
        ),
    ],
)
def test_RF_TEN_06_patch_validates_the_body(
    client: Client, org_a: Organization, body: dict[str, Any], codes: dict[str, str]
) -> None:
    branch = seed(org_a, "Centro")

    response = patch(client, as_member(member(org_a, Role.OWNER), org_a.id), branch, body)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert codes_of(response) == codes
    assert names_in(org_a) == [("Centro", "", True)]


def test_AC_TEN_07_patch_cannot_move_a_branch_to_b(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    branch = seed(org_a, "Centro")
    headers = as_member(member(org_a, Role.OWNER), org_a.id)

    response = patch(client, headers, branch, {"organization_id": str(org_b.id)})

    assert codes_of(response) == {"organization_id": "unknown_field"}
    assert names_in(org_a) == [("Centro", "", True)]
    assert names_in(org_b) == []


def test_AC_TEN_28_suspended_reads_but_does_not_edit(client: Client) -> None:
    suspended = new_org("S", OrgStatus.SUSPENDED)
    branch = seed(suspended, "Centro")
    headers = as_member(member(suspended, Role.OWNER), suspended.id)

    assert client.get(detail(branch), headers=headers).status_code == 200
    for response in (
        patch(client, headers, branch, {"name": "Otro"}),
        client.post(f"{detail(branch)}deactivate/", headers=headers),
    ):
        assert response.status_code == 409
        assert response.json()["code"] == "organization_suspended"
    assert names_in(suspended) == [("Centro", "", True)]


# --- AC-TEN-38 ---


@pytest.mark.parametrize(
    ("body", "detail_word"),
    [({"name": "NORTE"}, "nombre"), ({"name": "Centro", "code": "N01"}, "código")],
)
def test_AC_TEN_38_patch_to_taken_name(
    client: Client,
    org_a: Organization,
    body: dict[str, str],
    detail_word: str,
    recorded: RecordingSink,
) -> None:
    branch = seed(org_a, "Centro", "C01")
    seed(org_a, "Norte", "N01")

    response = patch(client, as_member(member(org_a, Role.ADMIN), org_a.id), branch, body)

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert detail_word in response.json()["detail"]
    assert names_in(org_a) == [("Centro", "C01", True), ("Norte", "N01", True)]
    assert recorded.events == []


def test_AC_TEN_38_patch_to_a_name_only_inactive_or_foreign_uses(
    client: Client, org_a: Organization, org_b: Organization
) -> None:
    branch = seed(org_a, "Centro")
    seed(org_a, "Norte", "N01", active=False)
    seed(org_b, "Sur", "S01")
    headers = as_member(member(org_a, Role.ADMIN), org_a.id)

    assert patch(client, headers, branch, {"name": "norte", "code": "N01"}).status_code == 200
    assert patch(client, headers, branch, {"name": "Sur", "code": "S01"}).status_code == 200


# --- AC-TEN-30 ---


@pytest.mark.parametrize("method", ["delete", "put"])
def test_AC_TEN_30_no_physical_delete(
    client: Client, org_a: Organization, method: str, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro")
    headers = as_member(member(org_a, Role.OWNER), org_a.id)

    response = getattr(client, method)(detail(branch), headers=headers)

    assert response.status_code == 405
    assert names_in(org_a) == [("Centro", "", True)]
    assert recorded.events == []


def test_RF_TEN_06_contract_declares_the_detail_routes() -> None:
    paths = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"]

    one = paths["/api/branches/{id}/"]
    assert set(one) - {"parameters"} == {"get", "patch"}
    assert (one["get"]["operationId"], one["patch"]["operationId"]) == (
        "branches_retrieve",
        "branches_partial_update",
    )
    for action in ("deactivate", "reactivate"):
        route = paths[f"/api/branches/{{id}}/{action}/"]
        assert set(route) - {"parameters"} == {"post"}
        assert route["post"]["operationId"] == f"branches_{action}"
        assert "requestBody" not in route["post"]


def test_RF_TEN_06_update_schema_follows_the_service() -> None:
    fields = BranchUpdateSerializer().fields

    assert set(fields) == set(CREATE_FIELDS)
    limits = {name: getattr(field, "max_length", None) for name, field in fields.items()}
    assert limits == dict(CREATE_FIELDS)
    assert [name for name, field in fields.items() if field.required] == []
