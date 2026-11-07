"""Ports towards SPEC-02 and SPEC-10: stubs, registry and audit catalog (design.md §6.4, §7.4).

AC-IDA-24 here is only the catalog against RN-IDA-17; that each event is emitted comes with the
services. The expected values are copied from the spec on purpose: changing the catalog takes
changing this list too.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.db import transaction
from django.test import override_settings

from apps.identity.domain.audit_events import (
    AUDIT_REASONS,
    AuditActorType,
    AuditResult,
    IdentityAuditAction,
    LoginRejectionReason,
    SessionRevocationReason,
)
from apps.identity.ports.audit import AuditEvent, AuditPort
from apps.identity.ports.invitations import (
    InvitationPort,
    InvitationRef,
    InvitationsNoLongerValid,
)
from apps.identity.ports.memberships import MembershipSelectorPort
from apps.identity.ports.registry import (
    get_audit_port,
    get_invitation_port,
    get_membership_selector,
)
from apps.identity.ports.stubs import EmptyMembershipSelector, LogAuditPort, NullInvitationPort
from config.settings.env import PlatformEnv

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
REJECTIONS = {
    "google_auth_failed",
    "email_not_verified",
    "not_invited",
    "user_inactive",
    "identity_conflict",
}
REVOCATIONS = {"user_revoked", "revoked_others", "user_deactivated", "refresh_reuse", "superseded"}
NOT_AUDITED = {"rate_limited", "google_unavailable", "login_cancelled"}
PORT_SETTINGS = ("IDENTITY_INVITATION_PORT", "IDENTITY_MEMBERSHIP_SELECTOR", "IDENTITY_AUDIT_PORT")


class RecordingAuditPort:
    def record(self, event: AuditEvent) -> None:
        """Stands for the implementation SPEC-10 will register by settings."""


def audit_event(**overrides: Any) -> AuditEvent:
    fields: dict[str, Any] = {
        "action": IdentityAuditAction.LOGOUT,
        "result": AuditResult.SUCCESS,
        "reason": None,
        "actor_type": AuditActorType.USER,
        "actor_id": uuid.uuid4(),
        "organization_id": None,
        "occurred_at": NOW,
        "metadata": {},
    }
    return AuditEvent(**{**fields, **overrides})


def audit_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    return [line for line in lines if line.get("component") == "audit"]


def test_AC_IDA_24_catalog_matches_spec() -> None:
    assert {action.value for action in IdentityAuditAction} == {
        "identity.login_succeeded",
        "identity.login_rejected",
        "identity.user_created_by_invitation",
        "identity.logout",
        "identity.session_revoked",
        "identity.refresh_reuse_detected",
        "identity.user_deactivated",
        "identity.user_reactivated",
        "identity.email_changed",
        "identity.email_change_collision",
    }
    assert {reason.value for reason in LoginRejectionReason} == REJECTIONS
    assert {reason.value for reason in SessionRevocationReason} == REVOCATIONS
    assert {actor.value for actor in AuditActorType} == {
        "user",
        "anonymous",
        "platform_operator",
        "system",
    }


def test_AC_IDA_24_operational_outcomes_are_not_audit_reasons() -> None:
    # Q-111 and design.md §4.2: logs and metrics only. `logout` has an event of its own.
    audited = {str(reason) for reasons in AUDIT_REASONS.values() for reason in reasons}
    assert audited == REJECTIONS | REVOCATIONS
    assert audited.isdisjoint(NOT_AUDITED | {"logout"})


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (IdentityAuditAction.LOGIN_REJECTED, None),
        (IdentityAuditAction.LOGIN_REJECTED, "google_unavailable"),
        (IdentityAuditAction.LOGIN_REJECTED, "user_revoked"),
        (IdentityAuditAction.SESSION_REVOKED, None),
        (IdentityAuditAction.SESSION_REVOKED, "logout"),
    ],
)
def test_RN_IDA_17_reason_outside_the_catalog_is_refused(
    action: IdentityAuditAction, reason: str | None
) -> None:
    with pytest.raises(ValueError, match="reason"):
        audit_event(action=action, result=AuditResult.FAILURE, reason=reason)


def test_RN_IDA_17_catalog_reason_is_accepted() -> None:
    rejected = audit_event(
        action=IdentityAuditAction.LOGIN_REJECTED,
        result=AuditResult.FAILURE,
        reason=LoginRejectionReason.NOT_INVITED,
        actor_type=AuditActorType.ANONYMOUS,
        actor_id=None,
    )
    assert rejected.reason == "not_invited"


@pytest.mark.parametrize(
    "occurred_at",
    [NOW.replace(tzinfo=None), NOW.astimezone(timezone(timedelta(hours=-3)))],
)
def test_RN_IDA_17_occurred_at_must_be_utc(occurred_at: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        audit_event(occurred_at=occurred_at)


def test_null_port_finds_nothing() -> None:
    port: InvitationPort = NullInvitationPort()
    assert port.find_valid_invitations("ana@x.com", now=NOW) == []


@pytest.mark.parametrize(
    "invitations",
    [[], [InvitationRef(invitation_id=uuid.uuid4(), organization_id=uuid.uuid4())]],
)
def test_RN_IDA_06_null_port_accepts_nothing(invitations: Sequence[InvitationRef]) -> None:
    # All or nothing: a stub that returned quietly would leave a user without its invitation.
    port: InvitationPort = NullInvitationPort()
    with pytest.raises(InvitationsNoLongerValid):
        port.accept_invitations(invitations, uuid.uuid4(), now=NOW)


def test_RF_IDA_06_empty_selector_has_no_memberships() -> None:
    selector: MembershipSelectorPort = EmptyMembershipSelector()
    assert selector.list_active_memberships(uuid.uuid4()) == []


def test_RF_IDA_09_registry_defaults_to_the_stubs() -> None:
    assert isinstance(get_invitation_port(), NullInvitationPort)
    assert isinstance(get_membership_selector(), EmptyMembershipSelector)
    assert isinstance(get_audit_port(), LogAuditPort)


@override_settings(IDENTITY_AUDIT_PORT=f"{__name__}.RecordingAuditPort")
def test_RF_IDA_09_registry_resolves_by_settings() -> None:
    assert isinstance(get_audit_port(), RecordingAuditPort)


def test_RF_IDA_09_ports_never_come_from_the_environment() -> None:
    for name in PORT_SETTINGS:
        assert getattr(django_settings, name).startswith("apps.identity.ports.stubs.")
        assert name not in PlatformEnv.model_fields


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_IDA_09_log_port_writes_the_event_to_the_audit_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    port: AuditPort = LogAuditPort()
    actor_id = uuid.uuid4()
    capsys.readouterr()
    port.record(audit_event(actor_id=actor_id, metadata={"alert": True}))
    [line] = audit_lines(capsys)
    assert line["message"] == "audit.event"
    assert line["action"] == "identity.logout"
    assert line["result"] == "success"
    assert line["reason"] is None
    assert line["actor_type"] == "user"
    assert line["actor_id"] == str(actor_id)
    assert line["organization_id"] is None
    assert line["occurred_at"] == "2026-11-07T12:00:00+00:00"
    assert line["metadata"] == {"alert": True}


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_IDA_09_log_port_waits_for_the_commit(capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    with transaction.atomic():
        LogAuditPort().record(audit_event())
        assert audit_lines(capsys) == []
    assert len(audit_lines(capsys)) == 1


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_IDA_09_log_port_keeps_the_metadata_of_the_moment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    metadata: dict[str, object] = {"alert": True}
    capsys.readouterr()
    with transaction.atomic():
        LogAuditPort().record(audit_event(metadata=metadata))
        metadata["alert"] = False
    assert audit_lines(capsys)[0]["metadata"] == {"alert": True}


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_IDA_09_log_port_drops_the_event_on_rollback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def callback_that_fails() -> None:
        with transaction.atomic():
            LogAuditPort().record(audit_event())
            raise InvitationsNoLongerValid

    capsys.readouterr()
    with pytest.raises(InvitationsNoLongerValid):
        callback_that_fails()
    assert audit_lines(capsys) == []
