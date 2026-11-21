"""``tenancy_owner_recovery`` (RF-TEN-07, RN-TEN-20, Q-224, Q-225; design.md §4.5).

Same setup as ``test_support_access``: the organization as the operator creates it, its first owner
in by accepting the link, the recovery link from the command's stdout. Read back with
``unscoped(PLATFORM)``.
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
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import hash_token
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services.invitation_accept import accept_by_token
from tests.identity.api.login_flow import make_user
from tests.tenancy.api.probe import PLATFORM
from tests.tenancy.commands.test_create_org import (
    OPERATOR,
    create_org,
    organization,
    recorded,
    token_of,
)
from tests.tenancy.commands.test_support_access import snapshot, support_access, with_owner
from tests.tenancy.invitation_setup import invitee

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db

NEW_OWNER = "beto@example.com"
REASON = "La dueña perdió su cuenta de Google"


def owner_recovery(**kw: str) -> str:
    out = StringIO()
    args = [
        "--org",
        kw.get("org") or str(organization().pk),
        "--email",
        kw.get("email", NEW_OWNER),
        "--reason",
        kw.get("reason", REASON),
        "--operator",
        kw.get("operator", OPERATOR),
    ]
    call_command("tenancy_owner_recovery", *args, stdout=out)
    return out.getvalue()


def refused(**kw: str) -> CommandError:
    with pytest.raises(CommandError) as raised:
        owner_recovery(**kw)
    return raised.value


def recovery_rows(org: Organization) -> list[tuple[Any, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=org, purpose="owner_recovery")
    fields = ("email", "role", "status", "reason", "invited_by_user", "invited_by_operator")
    return list(rows.order_by("created_at").values_list(*fields))


def owners_of(org: Organization) -> list[Any]:
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=org, role="owner")
    return sorted(rows.filter(status="active").values_list("pk", flat=True))


def new_owner() -> User:
    return make_user(sub="sub-beto", email=NEW_OWNER)


def test_Q_224_recovery_revokes_nobody(recorded: RecordingSink) -> None:
    org, owner = with_owner()
    support_access()  # another pending invitation, which stays as it is
    invitations_before, members_before = snapshot(org)

    output = owner_recovery()

    invitations_after, members_after = snapshot(org)
    assert members_after == members_before
    assert set(invitations_before) <= set(invitations_after)
    assert recovery_rows(org) == [(NEW_OWNER, "owner", "pending", REASON, None, OPERATOR)]
    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="owner_recovery")
    token = token_of(output)
    assert stored.token_hash == hash_token(token)
    assert output.count(token) == 1
    assert "Nobody was revoked: its 1 current owner(s) stay" in output

    accepted = accept_by_token(token, invitee(new_owner()))

    assert accepted.role is Role.OWNER
    assert owners_of(org) == sorted([owner.pk, accepted.membership_id])


def test_Q_224_needs_an_org_with_owner(recorded: RecordingSink) -> None:
    create_org()
    org = organization()
    before = snapshot(org)
    recorded.clear()

    error = refused()

    assert error.returncode == 1
    assert "tenancy_owner_invite" in str(error)
    assert snapshot(org) == before
    assert recorded.events == []


@pytest.mark.parametrize("reason", ["", "   ", "x" * 201])
def test_Q_224_reason_is_required(recorded: RecordingSink, reason: str) -> None:
    org, _ = with_owner()
    before = snapshot(org)
    recorded.clear()

    error = refused(reason=reason)

    assert error.returncode == 2
    assert snapshot(org) == before
    assert recorded.events == []


def test_AC_TEN_23_purpose_in_events_owner_recovery(recorded: RecordingSink) -> None:
    org, _ = with_owner()
    recorded.clear()

    with capture_logs() as logs:
        output = owner_recovery(email="  Beto@Example.com ")

    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org, purpose="owner_recovery")
    assert stored.email == NEW_OWNER
    [event] = recorded.events
    assert event.action == TenancyAuditAction.INVITATION_CREATED
    assert (event.actor.kind, event.actor.name) == (AuditActorKind.PLATFORM_OPERATOR, OPERATOR)
    assert (event.organization_id, event.reason) == (org.pk, REASON)
    assert event.metadata == {
        "invitation_id": str(stored.pk),
        "role": "owner",
        "purpose": "owner_recovery",
        "os_user": "deploy",
    }
    leaked = repr(recorded.events) + repr(logs)
    assert token_of(output) not in leaked
    assert NEW_OWNER not in leaked + output
    assert REASON not in repr(logs) + output
    assert [entry["event"] for entry in logs] == ["tenancy.platform_owner_recovery_issued"]


def test_Q_224_refusals_write_nothing(recorded: RecordingSink, settings: SettingsWrapper) -> None:
    org, _ = with_owner()
    owner_recovery()
    before = snapshot(org)
    recorded.clear()

    pending = refused()
    member = refused(email="ana@example.com")  # the current owner
    unknown = refused(org="00000000-0000-4000-8000-000000000000")
    settings.FRONTEND_BASE_URL = ""
    no_base = refused(email="otra@hub.test")

    assert [e.returncode for e in (pending, member, unknown, no_base)] == [1, 1, 1, 1]
    assert snapshot(org) == before
    assert recorded.events == []


@pytest.mark.parametrize(
    "args",
    [{"operator": "intruso@hub.test"}, {"org": "acme"}, {"email": "no-es-un-email"}],
)
def test_RF_TEN_07_recovery_bad_arguments_exit_2(
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
