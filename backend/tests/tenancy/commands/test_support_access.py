"""``tenancy_support_access`` (RF-TEN-07, RN-TEN-20, Q-222, Q-225; design.md §4.5).

The organization is born as the operator creates it (``tenancy_create_org``) and gets its owner by
accepting the link; the support link comes from the command's stdout and is accepted through the
real service. Everything is read back with ``unscoped(PLATFORM)``, never through the code under
test.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.common.audit.port import AuditActorKind
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationSuspended
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import hash_token
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.selectors.invitations import list_pending, to_invitations
from apps.tenancy.selectors.memberships import get_member
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from apps.tenancy.services.invitation_manage import revoke_invitation
from apps.tenancy.services.memberships import change_role
from apps.tenancy.services.platform_access import SupportRoleError, grant_support_access
from apps.tenancy.services.platform_org import Operator
from tests.identity.api.login_flow import make_user
from tests.tenancy.api.probe import PLATFORM
from tests.tenancy.commands.test_create_org import (
    OPERATOR,
    create_org,
    organization,
    recorded,
    token_of,
)
from tests.tenancy.invitation_setup import invitee, make_due
from tests.tenancy.locking import set_status, user_ctx

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db

SUPPORT_EMAIL = "soporte@hub.test"
REASON = "Ticket 42: no ven sus sucursales"
OPS = Operator(email=OPERATOR, os_user="deploy")


def support_access(**kw: str) -> str:
    out = StringIO()
    args = [
        "--org",
        kw.get("org") or str(organization().pk),
        "--email",
        kw.get("email", SUPPORT_EMAIL),
        "--reason",
        kw.get("reason", REASON),
        "--operator",
        kw.get("operator", OPERATOR),
    ]
    if "role" in kw:
        args += ["--role", kw["role"]]
    call_command("tenancy_support_access", *args, stdout=out)
    return out.getvalue()


def refused(**kw: str) -> CommandError:
    with pytest.raises(CommandError) as raised:
        support_access(**kw)
    return raised.value


def with_owner() -> tuple[Organization, Membership]:
    """An organization as the operator creates it, with its first owner already in."""
    accepted = accept_by_token(token_of(create_org()), invitee(make_user()))
    owner = Membership.objects.unscoped(PLATFORM).get(pk=accepted.membership_id)
    return organization(), owner


def support_rows(org: Organization) -> list[tuple[Any, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=org, purpose="support")
    fields = ("email", "role", "status", "reason", "invited_by_user", "invited_by_operator")
    return list(rows.order_by("created_at").values_list(*fields))


def snapshot(org: Organization) -> tuple[list[Any], list[Any]]:
    invitations = Invitation.objects.unscoped(PLATFORM).filter(organization=org)
    members = Membership.objects.unscoped(PLATFORM).filter(organization=org)
    return (
        sorted(invitations.values_list("pk", "status")),
        sorted(members.values_list("pk", "role", "status")),
    )


def support_user() -> User:
    return make_user(sub="sub-soporte", email=SUPPORT_EMAIL)


def test_Q_222_support_is_invitation_never_owner(recorded: RecordingSink) -> None:
    org, owner = with_owner()
    members_before = snapshot(org)[1]

    output = support_access()

    assert snapshot(org)[1] == members_before  # RN-TEN-20: no membership, only an invitation
    assert support_rows(org) == [(SUPPORT_EMAIL, "viewer", "pending", REASON, None, OPERATOR)]
    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="support")
    token = token_of(output)
    assert stored.token_hash == hash_token(token)
    assert output.count(token) == 1
    assert f"Support invitation {stored.pk} to organization {org.pk} issued" in output
    # argparse refuses it (exit 2 in a shell; call_command turns it into a CommandError)
    with pytest.raises(CommandError, match="invalid choice: 'owner'"):
        support_access(role="owner")
    with pytest.raises(SupportRoleError):  # the service refuses it too, whoever calls it
        grant_support_access(org.pk, "otra@hub.test", REASON, OPS, role=Role.OWNER)
    assert len(support_rows(org)) == 1

    accepted = accept_by_token(token, invitee(support_user()))

    assert accepted.role is Role.VIEWER
    owner_ctx = user_ctx(owner)
    with tenant_scope(owner_ctx):  # a normal membership: the owners see and manage it
        assert get_member(owner_ctx, accepted.membership_id) is not None
        assert change_role(owner_ctx, accepted.membership_id, Role.OPERATOR).changed


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_Q_222_support_takes_any_role_but_owner(recorded: RecordingSink, role: str) -> None:
    org, _ = with_owner()

    support_access(role=role)

    assert [row[1] for row in support_rows(org)] == [role]


@pytest.mark.parametrize("reason", ["", "   ", "x" * 201])
def test_Q_222_reason_is_required(recorded: RecordingSink, reason: str) -> None:
    org, _ = with_owner()
    before = snapshot(org)
    recorded.clear()

    error = refused(reason=reason)

    assert error.returncode == 2
    assert snapshot(org) == before
    assert recorded.events == []


def test_AC_TEN_23_purpose_in_events(recorded: RecordingSink) -> None:
    org, _ = with_owner()
    recorded.clear()

    with capture_logs() as logs:
        output = support_access(role="admin")

    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="support")
    [event] = recorded.events
    assert event.action == TenancyAuditAction.INVITATION_CREATED
    assert (event.actor.kind, event.actor.name) == (AuditActorKind.PLATFORM_OPERATOR, OPERATOR)
    assert (event.organization_id, event.reason) == (org.pk, REASON)
    assert event.occurred_at is not None
    assert event.metadata == {
        "invitation_id": str(stored.pk),
        "role": "admin",
        "purpose": "support",
        "os_user": "deploy",
    }
    leaked = repr(recorded.events) + repr(logs)
    assert token_of(output) not in leaked
    assert SUPPORT_EMAIL not in leaked + output
    assert REASON not in repr(logs) + output
    assert [entry["event"] for entry in logs] == ["tenancy.platform_support_access_issued"]


def test_Q_222_owners_can_revoke_a_pending_support_invitation(recorded: RecordingSink) -> None:
    org, owner = with_owner()
    token = token_of(support_access())
    owner_ctx = user_ctx(owner)
    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="support")

    with tenant_scope(owner_ctx):
        listed = to_invitations(list_pending(owner_ctx, now=stored.created_at))
        assert [(row.id, row.purpose) for row in listed] == [(stored.pk, "support")]
        revoke_invitation(owner_ctx, stored.pk)

    assert support_rows(org)[0][2] == "revoked"
    with pytest.raises(InvitationInvalid):
        accept_by_token(token, invitee(support_user()))


def test_Q_238_support_refused_without_owner(recorded: RecordingSink) -> None:
    create_org()  # born without members: only the first owner's invitation
    org = organization()
    before = snapshot(org)
    recorded.clear()

    error = refused()

    assert error.returncode == 1
    assert "no active owner" in str(error)
    assert "tenancy_owner_invite" in str(error)
    assert snapshot(org) == before
    assert support_rows(org) == []
    assert [e.action for e in recorded.events] == [
        TenancyAuditAction.OPERATOR_COMMAND_REJECTED
    ]  # Q-237


def test_Q_222_refusals_write_nothing(recorded: RecordingSink, settings: SettingsWrapper) -> None:
    org, _ = with_owner()
    support_access()
    before = snapshot(org)
    recorded.clear()

    pending = refused()
    member = refused(email="  Ana@Example.com ")  # the owner, normalized
    unknown = refused(org="00000000-0000-4000-8000-000000000000")
    settings.FRONTEND_BASE_URL = ""
    no_base = refused(email="otra@hub.test")

    assert [e.returncode for e in (pending, member, unknown, no_base)] == [1, 1, 1, 1]
    assert "pending invitation" in str(pending)
    assert "active member" in str(member)
    assert "does not exist" in str(unknown)
    assert snapshot(org) == before
    assert [e.action for e in recorded.events] == [
        TenancyAuditAction.OPERATOR_COMMAND_REJECTED
    ] * 4  # Q-237


def test_Q_222_an_expired_pending_one_is_expired_first(recorded: RecordingSink) -> None:
    org, _ = with_owner()
    support_access()
    make_due(Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="support"))
    recorded.clear()

    support_access()

    assert [row[2] for row in support_rows(org)] == ["expired", "pending"]
    assert [(e.action, e.actor.kind) for e in recorded.events] == [
        (TenancyAuditAction.INVITATION_EXPIRED, AuditActorKind.SYSTEM),
        (TenancyAuditAction.INVITATION_CREATED, AuditActorKind.PLATFORM_OPERATOR),
    ]


def test_RN_TEN_18_support_on_a_suspended_org_waits_for_reactivation(
    recorded: RecordingSink,
) -> None:
    org, _ = with_owner()
    set_status(org, OrgStatus.SUSPENDED)

    token = token_of(support_access())
    person = invitee(support_user())

    with pytest.raises(OrganizationSuspended):
        accept_by_token(token, person)
    set_status(org, OrgStatus.ACTIVE)
    assert accept_by_token(token, person).role is Role.VIEWER


@pytest.mark.parametrize(
    "args",
    [{"operator": "intruso@hub.test"}, {"org": "acme"}, {"email": "no-es-un-email"}],
)
def test_RF_TEN_07_support_bad_arguments_exit_2(
    recorded: RecordingSink, args: dict[str, str]
) -> None:
    org, _ = with_owner()
    before = snapshot(org)
    recorded.clear()

    error = refused(**args)

    assert error.returncode == 2
    assert snapshot(org) == before
    assert recorded.events == []
    assert "intruso" not in str(error)
    assert "no-es-un-email" not in str(error)
