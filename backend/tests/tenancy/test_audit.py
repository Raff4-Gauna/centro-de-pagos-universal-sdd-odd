"""RF-TEN-09 / RN-TEN-17 (design.md §3.1, §9): the audit port, its stub sinks and SPEC-02's catalog.

AC-TEN-23 here is only the base: the catalog against RNF-TEN-04 and the fields every event carries.
That each action is emitted by its service comes with the services, and its completeness with
T-TEN-27. The expected values are copied from the spec on purpose: changing the catalog takes
changing this list too.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from django.db import transaction
from django.test import override_settings

from apps.common.audit.port import AuditActor, AuditActorKind, AuditEvent, emit, get_sink
from apps.common.audit.sinks import RecordingSink, StructlogAuditSink
from apps.common.tenancy.context import (
    ApiKeyActor,
    OrgStatus,
    SystemActor,
    SystemReason,
    TenantContext,
    UserActor,
)
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.services.audit import AUDIT_TRIGGERS, audit_trigger, record_event

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RNF_TEN_04 = {
    "organization.created",
    "organization.updated",
    "organization.suspended",
    "organization.reactivated",
    "membership.created",
    "membership.role_changed",
    "membership.revoked",
    "membership.left",
    "invitation.created",
    "invitation.resent",
    "invitation.revoked",
    "invitation.accepted",
    "invitation.rejected",
    "branch.created",
    "branch.updated",
    "branch.deactivated",
    "branch.reactivated",
    "owner_protection.rejected",
    "invitation.expired",
    "invitation.auto_revoked",
    "transition.rejected",
}


def user_ctx() -> TenantContext:
    actor = UserActor(user_id=USER_ID, membership_id=uuid.uuid4(), role="owner")
    return TenantContext(ORG_ID, OrgStatus.ACTIVE, actor)


def audit_event(**overrides: Any) -> AuditEvent:
    fields: dict[str, Any] = {
        "action": TenancyAuditAction.MEMBERSHIP_CREATED,
        "actor": AuditActor(kind=AuditActorKind.USER, id=USER_ID),
        "organization_id": ORG_ID,
        "occurred_at": NOW,
        "metadata": {},
    }
    return AuditEvent(**{**fields, **overrides})


def audit_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    return [line for line in lines if line.get("component") == "audit"]


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def test_AC_TEN_23_catalog_equals_spec_list() -> None:
    assert {action.value for action in TenancyAuditAction} == RNF_TEN_04


def test_AC_TEN_23_event_carries_actor_action_organization_and_date(
    recorded: RecordingSink,
) -> None:
    event = record_event(TenancyAuditAction.ORGANIZATION_UPDATED, ctx=user_ctx())
    assert recorded.events == [event]
    assert event.action == "organization.updated"
    assert event.actor == AuditActor(kind=AuditActorKind.USER, id=USER_ID)
    assert event.organization_id == ORG_ID
    assert event.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        (
            UserActor(user_id=USER_ID, membership_id=uuid.uuid4(), role="admin"),
            AuditActor(kind=AuditActorKind.USER, id=USER_ID),
        ),
        (
            ApiKeyActor(key_id=USER_ID, scopes=frozenset()),
            AuditActor(kind=AuditActorKind.API_KEY, id=USER_ID),
        ),
        (
            SystemActor(SystemReason.CELERY),
            AuditActor(kind=AuditActorKind.SYSTEM, name="celery"),
        ),
    ],
)
def test_RN_TEN_17_actor_comes_from_the_tenant_context(actor: Any, expected: AuditActor) -> None:
    assert AuditActor.for_tenant_actor(actor) == expected


def test_RN_TEN_17_operator_overrides_the_context_actor(recorded: RecordingSink) -> None:
    ctx = TenantContext(ORG_ID, OrgStatus.ACTIVE, SystemActor(SystemReason.PLATFORM_COMMAND))
    operator = AuditActor.platform_operator("ops@hub.example")
    event = record_event(TenancyAuditAction.ORGANIZATION_CREATED, ctx=ctx, actor=operator)
    assert event.actor.kind is AuditActorKind.PLATFORM_OPERATOR
    assert event.actor.name == "ops@hub.example"
    assert recorded.events == [event]


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": AuditActorKind.USER},
        {"kind": AuditActorKind.USER, "id": USER_ID, "name": "ana"},
        {"kind": AuditActorKind.API_KEY},
        {"kind": AuditActorKind.SYSTEM},
        {"kind": AuditActorKind.SYSTEM, "name": "celery", "id": USER_ID},
        {"kind": AuditActorKind.PLATFORM_OPERATOR, "name": " "},
        {"kind": "user", "id": USER_ID},
        {"kind": AuditActorKind.USER, "id": str(USER_ID)},
    ],
)
def test_RN_TEN_17_actor_without_who_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        AuditActor(**fields)


@pytest.mark.parametrize(
    "overrides",
    [
        {"occurred_at": NOW.replace(tzinfo=None)},
        {"occurred_at": NOW.astimezone(timezone(timedelta(hours=-3)))},
        {"organization_id": str(ORG_ID)},
        {"organization_id": None},
        {"action": ""},
        {"actor": USER_ID},
    ],
)
def test_RN_TEN_17_incomplete_event_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        audit_event(**overrides)


def test_recording_sink_keeps_events() -> None:
    sink = RecordingSink()
    metadata: dict[str, object] = {"role": "admin"}
    first = audit_event(metadata=metadata)
    second = audit_event(action=TenancyAuditAction.MEMBERSHIP_REVOKED)
    sink.record(first)
    sink.record(second)
    metadata["role"] = "owner"
    assert [event.action for event in sink.events] == ["membership.created", "membership.revoked"]
    assert sink.events[0].metadata == {"role": "admin"}
    sink.clear()
    assert sink.events == []


def test_RF_TEN_09_emit_uses_the_sink_of_the_settings() -> None:
    with override_settings(AUDIT_SINK="apps.common.audit.sinks.StructlogAuditSink"):
        assert isinstance(get_sink(), StructlogAuditSink)
    assert isinstance(get_sink(), RecordingSink)
    assert get_sink() is get_sink()


def test_RF_TEN_09_emit_reaches_the_recording_sink(recorded: RecordingSink) -> None:
    event = audit_event()
    emit(event)
    assert recorded.events == [event]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_TEN_09_structlog_sink_writes_to_the_audit_channel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    StructlogAuditSink().record(audit_event(metadata={"role": "viewer"}))
    [line] = audit_lines(capsys)
    assert line["message"] == "audit.event"
    assert line["action"] == "membership.created"
    assert line["actor"] == {"kind": "user", "id": str(USER_ID), "name": None}
    assert line["organization_id"] == str(ORG_ID)
    assert line["occurred_at"] == "2026-11-12T12:00:00+00:00"
    assert line["reason"] is None
    assert line["metadata"] == {"role": "viewer"}


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_TEN_09_structlog_sink_waits_for_the_commit(capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    with transaction.atomic():
        StructlogAuditSink().record(audit_event())
        assert audit_lines(capsys) == []
    assert len(audit_lines(capsys)) == 1


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_RF_TEN_09_structlog_sink_drops_the_event_on_rollback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def change_that_fails() -> None:
        with transaction.atomic():
            StructlogAuditSink().record(audit_event())
            raise RuntimeError

    capsys.readouterr()
    with pytest.raises(RuntimeError):
        change_that_fails()
    assert audit_lines(capsys) == []


def test_AC_TEN_23_trigger_registry_maps_each_action_to_one_function() -> None:
    registry: dict[TenancyAuditAction, Callable[..., object]] = {}

    @audit_trigger(
        TenancyAuditAction.INVITATION_RESENT,
        TenancyAuditAction.INVITATION_REVOKED,
        registry=registry,
    )
    def resend() -> None: ...

    audit_trigger(TenancyAuditAction.INVITATION_RESENT, registry=registry)(resend)
    assert registry == {
        TenancyAuditAction.INVITATION_RESENT: resend,
        TenancyAuditAction.INVITATION_REVOKED: resend,
    }

    def revoke() -> None: ...

    with pytest.raises(ValueError, match=r"invitation\.revoked"):
        audit_trigger(TenancyAuditAction.INVITATION_REVOKED, registry=registry)(revoke)


def test_AC_TEN_23_global_registry_holds_only_catalog_actions() -> None:
    # Empty until the services register theirs; T-TEN-27 requires one per action.
    assert set(AUDIT_TRIGGERS) <= set(TenancyAuditAction)
