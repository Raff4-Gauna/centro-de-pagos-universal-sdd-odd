"""Q-237 (dueño, 2026-11-21): every refusal of an operator command is audited (RNF-TEN-04).

RN-IDA-23 and Q-123 audit every run of an operator command. Q-237 extends Q-235
(``organization.create_repeated``) to ``tenancy_owner_invite``, ``tenancy_set_org_status``,
``tenancy_support_access`` and ``tenancy_owner_recovery``: a refusal
that changes nothing (exit ``1``) leaves exactly one ``operator_command.rejected``, the operator as
its actor with ``os_user``, the code of the refusal as its reason and no PII (no email, no free
reason). The refusals by state keep their ``transition.rejected`` (C-05) and are not audited twice.
A bad argument (exit ``2``) is not a run: it audits nothing, as in Q-235. Everything is read back
with ``unscoped(PLATFORM)``, never through the code under test.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping
from typing import Any

import pytest
from django.core.management.base import CommandError
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.common.audit.port import AuditActorKind, AuditEvent
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.tenancy.domain.audit_events import OperatorRefusal, TenancyAuditAction
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.platform_owner_invite import revoke_owner_invitation
from tests.identity.api.login_flow import EMAIL, make_user
from tests.tenancy.api.probe import add_member, new_org
from tests.tenancy.commands.test_create_org import OPERATOR, create_org, organization, recorded
from tests.tenancy.commands.test_owner_invite import owner_invite
from tests.tenancy.commands.test_owner_recovery import owner_recovery
from tests.tenancy.commands.test_set_org_status import REASON as STATUS_REASON
from tests.tenancy.commands.test_set_org_status import saved, set_status
from tests.tenancy.commands.test_support_access import (
    REASON,
    SUPPORT_EMAIL,
    snapshot,
    support_access,
    with_owner,
)

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db

UNKNOWN = "00000000-0000-4000-8000-000000000000"
REJECTED = TenancyAuditAction.OPERATOR_COMMAND_REJECTED
RECOVERY_REASON = "La dueña perdió su cuenta de Google"


def run_refused(run: Callable[[], object]) -> tuple[CommandError, list[MutableMapping[str, Any]]]:
    with capture_logs() as logs, pytest.raises(CommandError) as raised:
        run()
    return raised.value, logs


def the_rejection(
    recorded: RecordingSink, organization_id: uuid.UUID | str, code: OperatorRefusal
) -> AuditEvent:
    """The one event of the run: ``operator_command.rejected`` by the operator, with ``code``."""
    [event] = recorded.events
    assert event.action == REJECTED
    assert (event.actor.kind, event.actor.name) == (AuditActorKind.PLATFORM_OPERATOR, OPERATOR)
    assert event.organization_id == uuid.UUID(str(organization_id))
    assert event.reason == code.value
    assert event.metadata["os_user"] == "deploy"
    return event


def assert_no_pii(
    recorded: RecordingSink, logs: list[MutableMapping[str, Any]], *values: str
) -> None:
    leaked = repr(recorded.events) + repr(logs)
    for value in (EMAIL, SUPPORT_EMAIL, REASON, RECOVERY_REASON, *values):
        assert value not in leaked


# --- tenancy_owner_invite ------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["reissue", "revoke"])
def test_Q_237_owner_invite_with_an_owner_is_audited(recorded: RecordingSink, action: str) -> None:
    org, _ = with_owner()
    before = snapshot(org)
    recorded.clear()

    error, logs = run_refused(lambda: owner_invite(action))

    assert error.returncode == 1
    assert snapshot(org) == before
    event = the_rejection(recorded, org.pk, OperatorRefusal.ORGANIZATION_HAS_OWNER)
    assert event.metadata == {
        "command": "tenancy_owner_invite",
        "operation": action,
        "os_user": "deploy",
    }
    assert_no_pii(recorded, logs)
    assert [entry["event"] for entry in logs] == ["tenancy.platform_command_rejected"]


def test_Q_237_owner_invite_without_its_invitation_is_audited(recorded: RecordingSink) -> None:
    org = new_org("Sin invitación")  # not born by tenancy_create_org: no first owner invitation
    recorded.clear()

    error, logs = run_refused(lambda: owner_invite("revoke", org=str(org.pk)))

    assert error.returncode == 1
    the_rejection(recorded, org.pk, OperatorRefusal.NO_OWNER_INVITATION)
    assert_no_pii(recorded, logs)


def test_Q_237_owner_invite_to_an_active_member_is_audited(recorded: RecordingSink) -> None:
    create_org()
    org = organization()
    member = make_user(sub="sub-beto", email="beto@example.com")
    add_member(org, member, Role.ADMIN)
    before = snapshot(org)
    recorded.clear()

    error, logs = run_refused(lambda: owner_invite("reissue", email="beto@example.com"))

    assert error.returncode == 1
    assert snapshot(org) == before
    the_rejection(recorded, org.pk, OperatorRefusal.ALREADY_MEMBER)
    assert_no_pii(recorded, logs, "beto@example.com")


def test_Q_237_owner_invite_unknown_org_and_no_base_url_are_audited(
    recorded: RecordingSink, settings: SettingsWrapper
) -> None:
    create_org()
    recorded.clear()

    unknown, _ = run_refused(lambda: owner_invite("revoke", org=UNKNOWN))
    the_rejection(recorded, UNKNOWN, OperatorRefusal.ORGANIZATION_NOT_FOUND)
    recorded.clear()
    settings.FRONTEND_BASE_URL = ""
    no_base, _ = run_refused(lambda: owner_invite("reissue"))

    assert (unknown.returncode, no_base.returncode) == (1, 1)
    the_rejection(recorded, organization().pk, OperatorRefusal.NOT_CONFIGURED)


def test_Q_237_owner_invite_state_refusal_is_audited_once(recorded: RecordingSink) -> None:
    create_org()
    owner_invite("revoke")
    recorded.clear()

    error, _ = run_refused(lambda: owner_invite("revoke"))

    assert error.returncode == 1
    assert [event.action for event in recorded.events] == [TenancyAuditAction.TRANSITION_REJECTED]


# --- tenancy_set_org_status ----------------------------------------------------------------------


def test_Q_237_set_status_unknown_org_is_audited(recorded: RecordingSink) -> None:
    org = new_org("Acme")

    error, logs = run_refused(lambda: set_status(org, "suspended", org=UNKNOWN))

    assert error.returncode == 1
    event = the_rejection(recorded, UNKNOWN, OperatorRefusal.ORGANIZATION_NOT_FOUND)
    assert event.metadata == {
        "command": "tenancy_set_org_status",
        "operation": "suspend",
        "os_user": "deploy",
    }
    assert saved(org) == ("active", None)
    assert STATUS_REASON not in repr(recorded.events) + repr(logs)


def test_Q_237_set_status_same_status_is_audited_once(recorded: RecordingSink) -> None:
    org = new_org("Acme")

    error, _ = run_refused(lambda: set_status(org, "active"))

    assert error.returncode == 1
    assert [event.action for event in recorded.events] == [TenancyAuditAction.TRANSITION_REJECTED]
    assert saved(org) == ("active", None)


# --- tenancy_support_access and tenancy_owner_recovery -------------------------------------------

COMMANDS = {
    "tenancy_support_access": support_access,
    "tenancy_owner_recovery": owner_recovery,
}


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_237_access_without_owner_is_audited(recorded: RecordingSink, command: str) -> None:
    create_org()  # born without members (Q-238, Q-224)
    org = organization()
    before = snapshot(org)
    recorded.clear()

    error, logs = run_refused(COMMANDS[command])

    assert error.returncode == 1
    assert snapshot(org) == before
    event = the_rejection(recorded, org.pk, OperatorRefusal.ORGANIZATION_WITHOUT_OWNER)
    assert event.metadata == {"command": command, "os_user": "deploy"}
    assert_no_pii(recorded, logs, "beto@example.com")


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_237_access_refusals_are_audited(
    recorded: RecordingSink, settings: SettingsWrapper, command: str
) -> None:
    run = COMMANDS[command]
    org, _ = with_owner()
    run()
    before = snapshot(org)
    cases: list[tuple[Callable[[], object], str, OperatorRefusal]] = [
        (run, str(org.pk), OperatorRefusal.INVITATION_PENDING),
        (lambda: run(email="  Ana@Example.com "), str(org.pk), OperatorRefusal.ALREADY_MEMBER),
        (lambda: run(org=UNKNOWN), UNKNOWN, OperatorRefusal.ORGANIZATION_NOT_FOUND),
    ]
    for attempt, organization_id, code in cases:
        recorded.clear()
        error, logs = run_refused(attempt)
        assert error.returncode == 1
        the_rejection(recorded, organization_id, code)
        assert_no_pii(recorded, logs, "beto@example.com")
    recorded.clear()
    settings.FRONTEND_BASE_URL = ""

    no_base, _ = run_refused(lambda: run(email="otra@hub.test"))

    assert no_base.returncode == 1
    the_rejection(recorded, org.pk, OperatorRefusal.NOT_CONFIGURED)
    assert snapshot(org) == before


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(
    "args", [{"operator": "intruso@hub.test"}, {"email": "no-es-un-email"}, {"reason": " "}]
)
def test_Q_237_bad_arguments_are_not_audited(
    recorded: RecordingSink, command: str, args: dict[str, str]
) -> None:
    with_owner()
    recorded.clear()

    error, _ = run_refused(lambda: COMMANDS[command](**args))

    assert error.returncode == 2
    assert recorded.events == []


def test_Q_237_the_rejection_has_its_trigger() -> None:
    assert AUDIT_TRIGGERS[REJECTED] is revoke_owner_invitation
