"""``tenancy_owner_invite reissue|revoke`` (RF-TEN-07, Q-213, RN-TEN-14; design.md §4.5).

The organization is born as the operator creates it (``tenancy_create_org``); the links come from
the commands' stdout and are accepted through the real service. Everything is read back with
``unscoped(PLATFORM)``, never through the code under test.
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
from apps.common.tenancy.context import OrgStatus
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import hash_token
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from tests.identity.api.login_flow import EMAIL, make_user
from tests.tenancy.api.probe import PLATFORM
from tests.tenancy.commands.test_create_org import (
    OPERATOR,
    create_org,
    members_of,
    organization,
    recorded,
    token_of,
)
from tests.tenancy.invitation_setup import invitee, make_due
from tests.tenancy.locking import set_status

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db


def owner_invite(action: str, **kw: str) -> str:
    out = StringIO()
    target = kw.get("org") or str(organization().pk)
    args = [action, "--org", target, "--operator", kw.get("operator", OPERATOR)]
    if "email" in kw:
        args += ["--email", kw["email"]]
    call_command("tenancy_owner_invite", *args, stdout=out)
    return out.getvalue()


def chain(org: Organization) -> list[tuple[Any, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=org).order_by("created_at")
    fields = ("email", "role", "purpose", "status", "revoked_reason", "revoked_by", "replaces")
    return list(rows.values_list("pk", *fields))


def actions(sink: RecordingSink) -> list[tuple[Any, ...]]:
    return [(e.action, e.actor.kind, e.actor.name, e.reason) for e in sink.events]


def by_operator(action: str, reason: str | None = None) -> tuple[Any, ...]:
    return (action, AuditActorKind.PLATFORM_OPERATOR, OPERATOR, reason)


def refused(action: str, **kw: str) -> CommandError:
    with pytest.raises(CommandError) as raised:
        owner_invite(action, **kw)
    return raised.value


def test_Q_213_reissue_only_without_owner(recorded: RecordingSink) -> None:
    accept_by_token(token_of(create_org()), invitee(make_user()))
    org = organization()
    before, events = chain(org), len(recorded.events)

    for action in ("reissue", "revoke"):
        error = refused(action)
        assert error.returncode == 1
        assert "already has an owner" in str(error)

    assert chain(org) == before
    assert [e.action for e in recorded.events[events:]] == [
        TenancyAuditAction.OPERATOR_COMMAND_REJECTED
    ] * 2  # Q-237


def test_Q_213_reissue_replaces_the_pending_one(recorded: RecordingSink) -> None:
    old_token = token_of(create_org())
    org = organization()
    recorded.clear()

    with capture_logs() as logs:
        output = owner_invite("reissue")

    [(old_id, *old), (new_id, *new)] = chain(org)
    assert old == [EMAIL, "owner", "first_owner", "revoked", "resent", None, None]
    assert new == [EMAIL, "owner", "first_owner", "pending", None, None, old_id]
    stored = Invitation.objects.unscoped(PLATFORM).get(pk=new_id)
    assert stored.invited_by_operator == OPERATOR
    new_token = token_of(output)
    assert stored.token_hash == hash_token(new_token)
    assert output.count(new_token) == 1
    assert actions(recorded) == [
        by_operator(TenancyAuditAction.INVITATION_REVOKED, "resent"),
        by_operator(TenancyAuditAction.INVITATION_RESENT),
    ]
    assert recorded.events[1].metadata == {
        "invitation_id": str(new_id),
        "replaces": str(old_id),
        "role": "owner",
        "purpose": "first_owner",
        "email_changed": False,
        "os_user": "deploy",
    }
    assert new_token not in repr(recorded.events) + repr(logs)
    assert EMAIL not in repr(recorded.events) + repr(logs)
    ana = make_user()
    with pytest.raises(InvitationInvalid):
        accept_by_token(old_token, invitee(ana))
    accepted = accept_by_token(new_token, invitee(ana))
    assert (accepted.organization_id, members_of(org)[0][1]) == (org.pk, "owner")


def test_Q_213_reissue_an_expired_one(recorded: RecordingSink) -> None:
    create_org()
    org = organization()
    make_due(Invitation.objects.unscoped(PLATFORM).get(organization=org))
    recorded.clear()

    token = token_of(owner_invite("reissue"))

    [(old_id, *old), (_, *new)] = chain(org)
    assert old[3:5] == ["expired", None]
    assert new[3:] == ["pending", None, None, old_id]
    assert [e.action for e in recorded.events] == [
        TenancyAuditAction.INVITATION_EXPIRED,
        TenancyAuditAction.INVITATION_RESENT,
    ]
    assert recorded.events[0].actor.kind == AuditActorKind.SYSTEM
    assert accept_by_token(token, invitee(make_user())).organization_id == org.pk


def test_Q_213_revoke_the_pending_one(recorded: RecordingSink) -> None:
    token = token_of(create_org())
    org = organization()
    recorded.clear()

    output = owner_invite("revoke")

    [(invitation_id, *row)] = chain(org)
    assert row == [EMAIL, "owner", "first_owner", "revoked", "operator", None, None]
    assert f"Owner invitation {invitation_id} of organization {org.pk} revoked." in output
    assert actions(recorded) == [by_operator(TenancyAuditAction.INVITATION_REVOKED, "operator")]
    with pytest.raises(InvitationInvalid):
        accept_by_token(token, invitee(make_user()))
    assert members_of(org) == []


@pytest.mark.parametrize(
    ("action", "prepare", "state"),
    [
        ("revoke", "due", "expired"),
        ("revoke", "revoked", "revoked"),
    ],
)
def test_AC_TEN_37_owner_invite_rejected_by_state(
    recorded: RecordingSink, action: str, prepare: str, state: str
) -> None:
    create_org()
    org = organization()
    if prepare == "due":
        make_due(Invitation.objects.unscoped(PLATFORM).get(organization=org))
    else:
        owner_invite("revoke")
    recorded.clear()

    error = refused(action)

    assert error.returncode == 1
    [(invitation_id, *row)] = chain(org)  # nothing new issued
    assert row[3] == state
    assert actions(recorded)[-1] == by_operator(TenancyAuditAction.TRANSITION_REJECTED)
    assert recorded.events[-1].metadata == {
        "entity": "invitation",
        "entity_id": str(invitation_id),
        "state": state,
        "event": action,
        "os_user": "deploy",
    }


def test_RN_TEN_18_the_operator_reissues_on_a_suspended_org(recorded: RecordingSink) -> None:
    create_org()
    org = organization()
    set_status(org, OrgStatus.SUSPENDED)

    owner_invite("reissue")

    assert [row[4] for row in chain(org)] == ["revoked", "pending"]


def test_Q_123_create_org_still_knows_its_values_after_a_reissue(recorded: RecordingSink) -> None:
    create_org()
    owner_invite("reissue")

    again = create_org()

    assert "already exists" in again
    assert len(chain(organization())) == 2


def test_RF_TEN_07_owner_invite_refusals_exit_1(
    recorded: RecordingSink, settings: SettingsWrapper
) -> None:
    create_org()
    unknown = refused("revoke", org="00000000-0000-4000-8000-000000000000")
    settings.FRONTEND_BASE_URL = ""
    no_base = refused("reissue")

    assert (unknown.returncode, no_base.returncode) == (1, 1)
    assert [row[4] for row in chain(organization())] == ["pending"]


@pytest.mark.parametrize("args", [{"operator": "intruso@hub.test"}, {"org": "acme"}])
def test_RF_TEN_07_owner_invite_bad_arguments_exit_2(
    recorded: RecordingSink, args: dict[str, str]
) -> None:
    create_org()
    recorded.clear()

    error = refused("reissue", **args)

    assert error.returncode == 2
    assert [row[4] for row in chain(organization())] == ["pending"]
    assert recorded.events == []
    assert "intruso" not in str(error)


# --- Q-236 (dueño, 2026-11-21): reissue --email, also from a revoked one ---

NEW_EMAIL = "beto@example.com"


def test_Q_236_reissue_after_revoke(recorded: RecordingSink) -> None:
    create_org()
    owner_invite("revoke")
    org = organization()
    recorded.clear()

    token = token_of(owner_invite("reissue"))

    [(old_id, *old), (_, *new)] = chain(org)
    assert old[3:5] == ["revoked", "operator"]  # left as it was
    assert new == [EMAIL, "owner", "first_owner", "pending", None, None, old_id]
    assert actions(recorded) == [by_operator(TenancyAuditAction.INVITATION_RESENT)]
    assert recorded.events[0].metadata["email_changed"] is False
    accepted = accept_by_token(token, invitee(make_user()))
    assert accepted.organization_id == org.pk


def test_Q_236_reissue_with_another_email(recorded: RecordingSink) -> None:
    old_token = token_of(create_org())
    org = organization()
    recorded.clear()

    with capture_logs() as logs:
        output = owner_invite("reissue", email="  Beto@Example.com ")

    [(old_id, *old), (_, *new)] = chain(org)
    assert old[:5] == [EMAIL, "owner", "first_owner", "revoked", "resent"]
    assert new == [NEW_EMAIL, "owner", "first_owner", "pending", None, None, old_id]
    assert recorded.events[-1].action == TenancyAuditAction.INVITATION_RESENT
    assert recorded.events[-1].metadata["email_changed"] is True
    assert NEW_EMAIL not in repr(recorded.events) + repr(logs) + output
    beto = make_user(sub="sub-beto", email=NEW_EMAIL)
    with pytest.raises(InvitationInvalid):
        accept_by_token(old_token, invitee(make_user()))
    assert accept_by_token(token_of(output), invitee(beto)).role.value == "owner"
    assert "already exists" in create_org()  # Q-123 still compares with the first one


def test_Q_236_reissue_defaults_to_the_latest_email(recorded: RecordingSink) -> None:
    create_org()
    owner_invite("reissue", email=NEW_EMAIL)
    owner_invite("revoke")

    owner_invite("reissue")

    assert [(row[1], row[4]) for row in chain(organization())] == [
        (EMAIL, "revoked"),
        (NEW_EMAIL, "revoked"),
        (NEW_EMAIL, "pending"),
    ]


@pytest.mark.parametrize(
    ("action", "email"),
    [
        ("reissue", "not-an-email"),
        ("reissue", " "),
        ("reissue", "a" * 250 + "@x.com"),
        ("revoke", NEW_EMAIL),
    ],
)
def test_Q_236_invalid_email_exits_2(recorded: RecordingSink, action: str, email: str) -> None:
    create_org()
    recorded.clear()

    error = refused(action, email=email)

    assert error.returncode == 2
    assert [row[4] for row in chain(organization())] == ["pending"]
    assert recorded.events == []
    assert "not-an-email" not in str(error)


def test_Q_236_still_refused_with_an_active_owner(recorded: RecordingSink) -> None:
    accept_by_token(token_of(create_org()), invitee(make_user()))
    org = organization()
    before, events = chain(org), len(recorded.events)

    error = refused("reissue", email=NEW_EMAIL)

    assert error.returncode == 1
    assert "already has an owner" in str(error)
    assert chain(org) == before
    assert [e.action for e in recorded.events[events:]] == [
        TenancyAuditAction.OPERATOR_COMMAND_REJECTED
    ]  # Q-237
