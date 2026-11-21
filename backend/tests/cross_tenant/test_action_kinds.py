"""Every route by the ``ActionKind`` it declares: suspended and audited (AC-TEN-23, AC-TEN-28).

The parameters are the endpoints the walker finds (``test_routes.ENDPOINTS``), never a list: a
route a module adds is suspended and, if it is SPEC-02's and writes, audited, with no line to add.

- AC-TEN-28 (RN-TEN-18, Q-208, Q-221): with A ``suspended`` a ``WRITE`` answers ``409
  organization_suspended`` with nothing written and no event; a ``READ`` and a ``REDUCE_ACCESS``
  (revoke a membership, leave, revoke an invitation) go through. Accepting an invitation is a
  ``WRITE`` of an exempt route, with no ``TenantViewSet``: its ``409`` lives in
  ``tests/tenancy/api/test_my_invitations_api.py`` and ``test_invitation_accept_api.py``.
- AC-TEN-23 (RN-TEN-17, RF-TEN-09): every write of SPEC-02's API emits its event of RNF-TEN-04,
  on A, by A's member. ``EXPECTED_EVENT`` pairs each write action of the matrix with that event, so
  a write action added without its event fails here.
"""

from __future__ import annotations

import pytest
from django.test import Client

from apps.common.audit.port import AuditActor, AuditActorKind
from apps.common.authz import checks
from apps.common.authz.actions import ActionKind
from apps.tenancy.domain.audit_events import TenancyAuditAction as Event
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from tests.cross_tenant.cases import tenant_probe
from tests.cross_tenant.classifier import Endpoint
from tests.cross_tenant.harness import World, check_suspended, own_request, spec_of
from tests.cross_tenant.test_routes import ENDPOINTS, by_label, case_of
from tests.cross_tenant.urls import SUITE_URLCONF

pytestmark = pytest.mark.urls(SUITE_URLCONF)

EXPECTED_EVENT: dict[TenancyAction, Event] = {
    TenancyAction.ORG_UPDATE: Event.ORGANIZATION_UPDATED,
    TenancyAction.MEMBER_CHANGE_ROLE: Event.MEMBERSHIP_ROLE_CHANGED,
    TenancyAction.MEMBER_REVOKE: Event.MEMBERSHIP_REVOKED,
    TenancyAction.MEMBER_LEAVE: Event.MEMBERSHIP_LEFT,
    TenancyAction.INVITATION_CREATE: Event.INVITATION_CREATED,
    TenancyAction.INVITATION_RESEND: Event.INVITATION_RESENT,
    TenancyAction.INVITATION_REVOKE: Event.INVITATION_REVOKED,
    TenancyAction.BRANCH_CREATE: Event.BRANCH_CREATED,
    TenancyAction.BRANCH_UPDATE: Event.BRANCH_UPDATED,
    TenancyAction.BRANCH_DEACTIVATE: Event.BRANCH_DEACTIVATED,
    TenancyAction.BRANCH_REACTIVATE: Event.BRANCH_REACTIVATED,
}


def of_kind(kind: ActionKind) -> list[Endpoint]:
    return [endpoint for endpoint in ENDPOINTS if (spec := spec_of(endpoint)) and spec.kind is kind]


def is_tenancy(endpoint: Endpoint) -> bool:
    """SPEC-02's views; the suite's ``tenant_probe`` borrows the ``branch.*`` specs, not audit."""
    return endpoint.view_class.__module__.startswith("apps.tenancy.")


TENANCY_WRITES = [
    endpoint
    for endpoint in ENDPOINTS
    if is_tenancy(endpoint) and (spec := spec_of(endpoint)) and spec.kind is not ActionKind.READ
]


# --- AC-TEN-28 -----------------------------------------------------------------------------------


def test_AC_TEN_28_every_route_declares_its_kind() -> None:
    """No action is skipped for lacking a spec, and each kind is exercised by a real route."""
    assert [endpoint.label for endpoint in ENDPOINTS if spec_of(endpoint) is None] == []
    for kind in ActionKind:
        assert of_kind(kind), f"no route of kind {kind}: the suspended check is not running"


@pytest.mark.parametrize("endpoint", by_label(of_kind(ActionKind.WRITE)))
def test_AC_TEN_28_every_write_case_is_409_when_suspended(
    xt_client: Client, world: World, endpoint: Endpoint
) -> None:
    assert check_suspended(xt_client, world, endpoint, case_of(endpoint)) == []


@pytest.mark.parametrize("endpoint", by_label(of_kind(ActionKind.READ)))
def test_AC_TEN_28_reads_pass_when_suspended(
    xt_client: Client, world: World, endpoint: Endpoint
) -> None:
    assert check_suspended(xt_client, world, endpoint, case_of(endpoint)) == []


@pytest.mark.parametrize("endpoint", by_label(of_kind(ActionKind.REDUCE_ACCESS)))
def test_AC_TEN_28_reduce_access_passes_when_suspended(
    xt_client: Client, world: World, endpoint: Endpoint
) -> None:
    """Q-221: a person removed during a suspension must not keep access."""
    assert check_suspended(xt_client, world, endpoint, case_of(endpoint)) == []


def test_AC_TEN_28_a_guard_that_forgets_the_suspension_is_caught(
    xt_client: Client, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The net itself: the central guard lets every kind through and the harness says so."""
    monkeypatch.setattr(checks, "SUSPENDED_ALLOWED_KINDS", frozenset(ActionKind))
    (endpoint,) = [e for e in of_kind(ActionKind.WRITE) if e.route == tenant_probe.LIST]

    failures = check_suspended(xt_client, world, endpoint, case_of(endpoint))

    assert failures == [
        f"{endpoint.label} [suspended]: answered 201, not 409 organization_suspended",
        f"{endpoint.label} [suspended]: A's rows changed",
    ]


# --- AC-TEN-23 -----------------------------------------------------------------------------------


def test_AC_TEN_23_every_write_action_names_its_event() -> None:
    writes = {name for name, spec in TENANCY_ACTIONS.items() if spec.kind is not ActionKind.READ}

    assert set(EXPECTED_EVENT) == writes
    assert {TenancyAction(spec.name) for e in TENANCY_WRITES if (spec := spec_of(e))} == writes


@pytest.mark.parametrize("endpoint", by_label(TENANCY_WRITES))
def test_AC_TEN_23_every_write_route_emits_its_event(
    xt_client: Client, world: World, endpoint: Endpoint
) -> None:
    spec = spec_of(endpoint)
    assert spec is not None
    expected = EXPECTED_EVENT[TenancyAction(spec.name)]

    response, events, leaks = own_request(xt_client, world, endpoint, case_of(endpoint))

    assert leaks == []
    assert 200 <= response.status_code < 300, response.content
    member = AuditActor(kind=AuditActorKind.USER, id=world.member.pk)
    emitted = [(e.action, e.organization_id, e.actor) for e in events if e.action == expected]
    assert emitted, f"{endpoint.label} emitted {[e.action for e in events]}, not {expected}"
    assert set(emitted) == {(expected.value, world.org_a.id, member)}
