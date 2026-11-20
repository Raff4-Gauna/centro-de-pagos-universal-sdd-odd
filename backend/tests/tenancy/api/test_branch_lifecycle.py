"""``POST /api/branches/{id}/deactivate/`` and ``.../reactivate/`` (RF-TEN-06, RN-TEN-19, §6).

AC-TEN-30: a deactivated branch still exists, is listed as inactive and leaves
``branch.deactivated``; reactivating one whose name another active branch uses is
``400 validation_error`` and it stays inactive (Q-210). AC-TEN-37 (Q-225, C-05): deactivating an
inactive branch or reactivating an active one is ``409 invalid_transition`` and leaves
``transition.rejected``, with nothing changed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Branch, Organization
from tests.tenancy.api.probe import PLATFORM, as_member, new_org
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


def transition(client: Client, headers: dict[str, str], branch: Branch, action: str) -> Any:
    return client.post(f"/api/branches/{branch.pk}/{action}/", headers=headers)


def stored(branch: Branch) -> Branch:
    return Branch.objects.unscoped(PLATFORM).get(pk=branch.pk)


# --- AC-TEN-30 ---


def test_AC_TEN_30_deactivate_keeps_the_branch(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro", "C01")
    admin = member(org_a, Role.ADMIN)
    headers = as_member(admin, org_a.id)

    response = transition(client, headers, branch, "deactivate")

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["is_active"]) == (str(branch.pk), False)
    row = stored(branch)
    assert row.is_active is False
    assert row.deactivated_at is not None
    assert body["deactivated_at"] is not None
    listed = client.get("/api/branches/", headers=headers).json()["results"]
    assert [(b["name"], b["is_active"]) for b in listed] == [("Centro", False)]
    [event] = recorded.events
    assert event.action == TenancyAuditAction.BRANCH_DEACTIVATED
    assert (event.organization_id, event.actor.id) == (org_a.id, admin.pk)
    assert event.metadata == {"branch_id": str(branch.pk)}


def test_RF_TEN_06_reactivate_clears_deactivated_at(
    client: Client, org_a: Organization, recorded: RecordingSink
) -> None:
    branch = seed(org_a, "Centro", "C01", active=False)

    response = transition(
        client, as_member(member(org_a, Role.OWNER), org_a.id), branch, "reactivate"
    )

    assert response.status_code == 200
    assert (response.json()["is_active"], response.json()["deactivated_at"]) == (True, None)
    row = stored(branch)
    assert (row.is_active, row.deactivated_at) == (True, None)
    [event] = recorded.events
    assert event.action == TenancyAuditAction.BRANCH_REACTIVATED
    assert event.metadata == {"branch_id": str(branch.pk)}


@pytest.mark.parametrize(
    ("taken", "field"),
    [(("CENTRO", ""), "name"), (("Norte", "C01"), "code")],
)
def test_AC_TEN_30_reactivate_with_taken_name(
    client: Client,
    org_a: Organization,
    taken: tuple[str, str],
    field: str,
    recorded: RecordingSink,
) -> None:
    branch = seed(org_a, "Centro", "C01", active=False)
    seed(org_a, *taken)

    response = transition(
        client, as_member(member(org_a, Role.ADMIN), org_a.id), branch, "reactivate"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert set(codes_of(response)) == {field}
    row = stored(branch)
    assert (row.is_active, row.deactivated_at is not None) == (False, True)
    assert recorded.events == []


def test_AC_TEN_30_reactivate_with_a_name_of_another_org(
    client: Client, org_a: Organization
) -> None:
    branch = seed(org_a, "Centro", "C01", active=False)
    seed(new_org("B"), "Centro", "C01")

    response = transition(
        client, as_member(member(org_a, Role.ADMIN), org_a.id), branch, "reactivate"
    )

    assert response.status_code == 200
    assert names_in(org_a) == [("Centro", "C01", True)]


# --- AC-TEN-37 ---


@pytest.mark.parametrize(
    ("active", "action", "state"),
    [(True, "reactivate", "active"), (False, "deactivate", "inactive")],
)
def test_AC_TEN_37_reactivate_active_is_invalid_transition(
    client: Client,
    org_a: Organization,
    active: bool,
    action: str,
    state: str,
    recorded: RecordingSink,
) -> None:
    branch = seed(org_a, "Centro", active=active)
    before = stored(branch)
    owner = member(org_a, Role.OWNER)

    response = transition(client, as_member(owner, org_a.id), branch, action)

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_transition"
    assert response.json()["title"] == "Transición inválida"
    row = stored(branch)
    assert (row.is_active, row.deactivated_at, row.updated_at) == (
        before.is_active,
        before.deactivated_at,
        before.updated_at,
    )
    [event] = recorded.events
    assert event.action == TenancyAuditAction.TRANSITION_REJECTED
    assert (event.organization_id, event.actor.id) == (org_a.id, owner.pk)
    assert event.metadata == {
        "entity": "branch",
        "entity_id": str(branch.pk),
        "state": state,
        "event": action,
    }
