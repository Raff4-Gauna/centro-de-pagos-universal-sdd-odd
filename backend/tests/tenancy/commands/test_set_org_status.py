"""``tenancy_set_org_status`` (RF-TEN-07, RN-TEN-18, Q-208, AC-TEN-28, AC-TEN-29; design.md §4.5).

The command runs as the operator would, through ``call_command``, with the one operator of the
test settings. What a suspension does to the members is checked through the real API, as they
would see it; everything else is read back with ``unscoped(PLATFORM)``.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from structlog.testing import capture_logs

from apps.common.audit.port import AuditActorKind
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy import locks
from apps.common.tenancy.context import OrgStatus
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.models import Organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.platform_org_status import set_org_status
from tests.tenancy.api.probe import PLATFORM, add_member, as_member, new_org, new_user
from tests.tenancy.commands.test_create_org import OPERATOR, recorded
from tests.tenancy.invitation_setup import issue, memberships, status_of
from tests.tenancy.locking import new_widget, user_ctx, widget_name
from tests.tenancy.test_AC_TEN_28_lock_races import Held, Second, blocks_behind, rename

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db

REASON = "falta de pago de la factura 2026-11"


def set_status(organization: Organization, status: str, **kw: str) -> str:
    out = StringIO()
    args = ["--org", kw.get("org", str(organization.pk)), "--status", status]
    args += ["--reason", kw.get("reason", REASON), "--operator", kw.get("operator", OPERATOR)]
    call_command("tenancy_set_org_status", *args, stdout=out)
    return out.getvalue()


def saved(org: Organization) -> tuple[Any, ...]:
    rows = Organization.objects.unscoped(PLATFORM).filter(pk=org.pk)
    return rows.values_list("status", "status_changed_at").get()


def trail(sink: RecordingSink) -> list[tuple[Any, ...]]:
    return [
        (e.action, e.organization_id, e.actor.kind, e.actor.name, e.reason, e.metadata)
        for e in sink.events
    ]


def by_operator(action: str, org: Organization, reason: str | None, **metadata: str) -> tuple:
    meta = {**metadata, "os_user": "deploy"}
    return (action, org.pk, AuditActorKind.PLATFORM_OPERATOR, OPERATOR, reason, meta)


def test_AC_TEN_29_status_changes_only_by_command(client: Client, recorded: RecordingSink) -> None:
    org = new_org("Acme")
    owner = new_user("ana")
    add_member(org, owner, Role.OWNER)
    response = client.patch(
        "/api/organizations/current/",
        data={"status": "suspended"},
        content_type="application/json",
        headers=as_member(owner, org.pk),
    )
    assert response.status_code == 400
    assert saved(org) == ("active", None)

    with capture_logs() as logs:
        output = set_status(org, "suspended")

    status, changed_at = saved(org)
    assert (status, changed_at is not None) == ("suspended", True)
    assert f"Organization {org.pk} is now suspended." in output
    set_status(org, "active")
    assert saved(org)[0] == "active"
    assert AUDIT_TRIGGERS[TenancyAuditAction.ORGANIZATION_SUSPENDED] is set_org_status
    assert AUDIT_TRIGGERS[TenancyAuditAction.ORGANIZATION_REACTIVATED] is set_org_status
    assert trail(recorded) == [
        by_operator(TenancyAuditAction.ORGANIZATION_SUSPENDED, org, REASON),
        by_operator(TenancyAuditAction.ORGANIZATION_REACTIVATED, org, REASON),
    ]
    assert [(entry["event"], entry["status"]) for entry in logs] == [
        ("tenancy.platform_org_status_changed", "suspended")
    ]
    assert REASON not in repr(logs)


def test_AC_TEN_28_suspended_blocks_writes_allows_reads(
    client: Client, recorded: RecordingSink
) -> None:
    org = new_org("Acme")
    owner, admin = new_user("ana"), new_user("beto")
    add_member(org, owner, Role.OWNER)
    admin_membership = add_member(org, admin, Role.ADMIN)
    invitation, _ = issue(org, "caro@hub.test")
    set_status(org, "suspended")
    headers = as_member(owner, org.pk)

    def send(method: str, url: str, body: dict[str, str] | None = None) -> Any:
        call = getattr(client, method)
        return call(url, data=body or {}, content_type="application/json", headers=headers)

    assert send("get", "/api/branches/").status_code == 200
    assert send("get", "/api/organizations/current/").json()["status"] == "suspended"
    writes = [
        send("post", "/api/branches/", {"name": "Centro"}),
        send("patch", "/api/organizations/current/", {"name": "Otra"}),
        send("post", "/api/invitations/", {"email": "dani@hub.test", "role": "viewer"}),
        send("patch", f"/api/memberships/{admin_membership.pk}/", {"role": "viewer"}),
    ]
    caro = new_user("caro")
    accept = f"/api/invitations/{invitation.pk}/accept/"
    writes.append(client.generic("POST", accept, headers=as_member(caro, None)))
    assert [(r.status_code, r.json()["code"]) for r in writes] == [
        (409, "organization_suspended")
    ] * 5
    assert memberships(caro) == []
    assert status_of(invitation) == "pending"

    set_status(org, "active")
    assert send("post", "/api/branches/", {"name": "Centro"}).status_code == 201


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_28_the_suspension_waits_for_a_write_in_flight(recorded: RecordingSink) -> None:
    org = new_org("Acme")
    ctx = user_ctx(add_member(org, new_user("ana"), Role.OWNER))
    widget = new_widget(org)
    writer = Held(lambda: locks.ensure_writable(ctx), then=rename(ctx, widget))
    suspension = Second(lambda: set_status(org, "suspended"))

    blocks_behind(writer, suspension)

    assert suspension.error is None
    assert (widget_name(widget), saved(org)[0]) == ("after", "suspended")


@pytest.mark.parametrize(
    ("initial", "asked", "event"),
    [(OrgStatus.SUSPENDED, "suspended", "suspend"), (OrgStatus.ACTIVE, "active", "reactivate")],
)
def test_AC_TEN_37_same_status_is_rejected_and_audited(
    recorded: RecordingSink, initial: OrgStatus, asked: str, event: str
) -> None:
    org = new_org("Acme", initial)

    with pytest.raises(CommandError) as raised:
        set_status(org, asked)

    assert raised.value.returncode == 1
    assert f"already {asked}" in str(raised.value)
    assert saved(org) == (initial.value, None)
    metadata = {"entity": "organization", "entity_id": str(org.pk), "state": initial.value}
    assert trail(recorded) == [
        by_operator(TenancyAuditAction.TRANSITION_REJECTED, org, None, **metadata, event=event)
    ]


def test_RF_TEN_07_unknown_organization_exits_1(recorded: RecordingSink) -> None:
    org = new_org("Acme")

    with pytest.raises(CommandError) as raised:
        set_status(org, "suspended", org="00000000-0000-4000-8000-000000000000")

    assert raised.value.returncode == 1
    assert saved(org) == ("active", None)
    assert [e.action for e in recorded.events] == [
        TenancyAuditAction.OPERATOR_COMMAND_REJECTED
    ]  # Q-237


@pytest.mark.parametrize(
    "args",
    [
        {"operator": "intruso@hub.test"},
        {"operator": " "},
        {"org": "acme"},
        {"reason": " "},
        {"reason": "r" * 201},
    ],
)
def test_RF_TEN_07_bad_arguments_exit_2_and_change_nothing(
    recorded: RecordingSink, args: dict[str, str]
) -> None:
    org = new_org("Acme")

    with pytest.raises(CommandError) as raised:
        set_status(org, "suspended", **args)

    assert raised.value.returncode == 2
    assert saved(org) == ("active", None)
    assert recorded.events == []
    assert "intruso" not in str(raised.value)


def test_RF_TEN_07_an_unknown_status_is_refused(recorded: RecordingSink) -> None:
    org = new_org("Acme")

    with pytest.raises(CommandError):
        set_status(org, "closed")

    assert saved(org) == ("active", None)
    assert recorded.events == []
