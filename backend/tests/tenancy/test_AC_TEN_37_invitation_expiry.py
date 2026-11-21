"""The expiry of invitations on beat (AC-TEN-37, Q-225, RF-TEN-05, design.md §3.6): ``tasks.py``.

``expire_invitations`` (a ``SystemFanoutTask``) lists the due ``pending`` invitations and enqueues
one ``expire_invitation`` (a ``TenantTask``) per pair; the tests catch what it enqueues by patching
``apply_async`` and run each job with ``Task.apply``, outside any tenant, as a worker would. Every
``invitation.expired`` (the task's, a creation's lazy expiry, an acceptance's) names the same actor:
``SystemReason.INVITATION_EXPIRY`` (review of PR #131).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from celery.schedules import crontab

from apps.common.audit.port import AuditActor, AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason
from apps.common.tenancy.current import current_tenant, tenant_scope
from apps.common.tenancy.querysets import TenantScopeError
from apps.tenancy import beat
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import InvalidReason, InvitationStatus
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_by_token
from apps.tenancy.services.invitations import create_invitation, expire_due_invitation
from apps.tenancy.tasks import expire_invitation, expire_invitations
from config import celery_app
from tests.tenancy.api.probe import PLATFORM, add_member, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, make_due, set_status, status_of
from tests.tenancy.locking import system_ctx, user_ctx

pytestmark = pytest.mark.django_db

EXPIRY_ACTOR = AuditActor(kind=AuditActorKind.SYSTEM, name="invitation_expiry")


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What the fan-out enqueues: the options of each ``apply_async``, nothing goes out."""
    jobs: list[dict[str, Any]] = []
    monkeypatch.setattr(expire_invitation, "apply_async", lambda **options: jobs.append(options))
    return jobs


def due(organization: Organization, email: str) -> Invitation:
    invitation, _ = issue(organization, email)
    make_due(invitation)
    return invitation


def expired_events(sink: RecordingSink) -> list[Any]:
    return [e for e in sink.events if e.action == TenancyAuditAction.INVITATION_EXPIRED]


# --- AC-TEN-37 -----------------------------------------------------------------------------------


def test_AC_TEN_37_expiry_task_emits_system_event(
    recorded: RecordingSink, sent: list[dict[str, Any]]
) -> None:
    a, b = new_org("A"), new_org("B", OrgStatus.SUSPENDED)  # a system actor is not stopped
    due_a, due_b = due(a, "ana@hub.test"), due(b, "beto@hub.test")
    valid, _ = issue(a, "caro@hub.test")

    assert expire_invitations.apply().get() == 2
    for job in sent:
        assert expire_invitation.apply(kwargs=job["kwargs"]).get() is True

    assert status_of(due_a) == status_of(due_b) == InvitationStatus.EXPIRED
    assert status_of(valid) == InvitationStatus.PENDING
    events = sorted(expired_events(recorded), key=lambda e: e.metadata["invitation_id"])
    expected = sorted([(due_a, a), (due_b, b)], key=lambda pair: str(pair[0].pk))
    assert [(e.organization_id, e.metadata) for e in events] == [
        (org.id, {"invitation_id": str(inv.pk)}) for inv, org in expected
    ]
    assert {e.actor for e in events} == {EXPIRY_ACTOR}
    assert current_tenant() is None


def test_fanout_only_enumerates_ids(
    recorded: RecordingSink, sent: list[dict[str, Any]], django_assert_num_queries: Any
) -> None:
    """The fan-out lists ids with one query and enqueues one ``TenantTask`` per pair: it writes
    nothing, emits nothing and hands over nothing but the two ids (design.md §3.6)."""
    a, b = new_org("A"), new_org("B")
    pairs = {due(a, "ana@hub.test").pk: a.id, due(b, "beto@hub.test").pk: b.id}
    issue(a, "caro@hub.test")  # still valid: not listed
    revoked = due(a, "dani@hub.test")
    set_status(revoked, InvitationStatus.REVOKED)  # past its date, but no longer pending

    with django_assert_num_queries(1):
        assert expire_invitations.apply().get() == 2

    assert {frozenset(job) for job in sent} == {frozenset({"kwargs"})}
    jobs = [job["kwargs"] for job in sent]
    assert all(set(job) == {"organization_id", "invitation_id"} for job in jobs)
    assert {uuid.UUID(j["invitation_id"]): uuid.UUID(j["organization_id"]) for j in jobs} == pairs
    assert recorded.events == []
    statuses = Invitation.objects.unscoped(PLATFORM).values_list("status")
    assert sorted(s for (s,) in statuses) == ["pending", "pending", "pending", "revoked"]


def test_AC_TEN_37_expiry_task_is_a_noop_once_no_longer_due(recorded: RecordingSink) -> None:
    """Between the listing and the task the invitation was accepted, revoked or renewed: the task
    re-reads it under the locks and leaves it alone (a late or repeated run does no harm)."""
    org = new_org("A")
    gone = due(org, "ana@hub.test")
    set_status(gone, InvitationStatus.REVOKED)
    valid, _ = issue(org, "beto@hub.test")
    expired = due(org, "caro@hub.test")
    set_status(expired, InvitationStatus.EXPIRED)

    for invitation in (gone, valid, expired):
        job = {"organization_id": str(org.id), "invitation_id": str(invitation.pk)}
        assert expire_invitation.apply(kwargs=job).get() is False

    assert [status_of(i) for i in (gone, valid, expired)] == ["revoked", "pending", "expired"]
    assert recorded.events == []


def test_AC_TEN_37_expiry_task_stays_in_its_organization(recorded: RecordingSink) -> None:
    a, b = new_org("A"), new_org("B")
    of_b = due(b, "ana@hub.test")

    job = {"organization_id": str(a.id), "invitation_id": str(of_b.pk)}
    assert expire_invitation.apply(kwargs=job).get() is False

    assert status_of(of_b) == InvitationStatus.PENDING
    assert recorded.events == []


def test_AC_TEN_37_expiry_tasks_do_not_run_inside_a_tenant(sent: list[dict[str, Any]]) -> None:
    org = new_org("A")
    invitation = due(org, "ana@hub.test")
    job = {"organization_id": str(org.id), "invitation_id": str(invitation.pk)}

    with tenant_scope(system_ctx(org.id)):
        with pytest.raises(TenantScopeError):
            expire_invitations.apply().get()
        with pytest.raises(TenantScopeError):
            expire_invitation.apply(kwargs=job).get()

    assert sent == []
    assert status_of(invitation) == InvitationStatus.PENDING


def test_AC_TEN_37_expiry_trigger_is_registered() -> None:
    assert AUDIT_TRIGGERS[TenancyAuditAction.INVITATION_EXPIRED] is expire_due_invitation


def test_AC_TEN_37_every_expiry_names_the_same_system_actor(recorded: RecordingSink) -> None:
    """Lazy expiry on creating and on accepting, and the task: one actor (review of PR #131)."""
    org = new_org("A")
    owner = add_member(org, new_user("owner"), Role.OWNER)
    on_create = due(org, "ana@hub.test")
    on_accept, token = issue(org, "beto@hub.test")
    make_due(on_accept)
    by_task = due(org, "caro@hub.test")

    with tenant_scope(user_ctx(owner)):
        create_invitation(user_ctx(owner), "ana@hub.test", Role.VIEWER)
    with pytest.raises(InvitationInvalid) as refused:
        accept_by_token(token, invitee(new_user("beto")))
    assert refused.value.problem_reason == InvalidReason.EXPIRED.value
    job = {"organization_id": str(org.id), "invitation_id": str(by_task.pk)}
    expire_invitation.apply(kwargs=job).get()

    events = expired_events(recorded)
    assert [e.metadata["invitation_id"] for e in events] == [
        str(i.pk) for i in (on_create, on_accept, by_task)
    ]
    assert {e.actor for e in events} == {EXPIRY_ACTOR}
    assert AuditActor.for_tenant_actor(SystemActor(SystemReason.INVITATION_EXPIRY)) == EXPIRY_ACTOR


def test_AC_TEN_37_expiry_service_checks_the_clock(recorded: RecordingSink) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    ctx = system_ctx(org.id)

    with tenant_scope(ctx):
        early = expire_due_invitation(ctx, invitation.pk, now=invitation.expires_at - timedelta(1))
        on_time = expire_due_invitation(ctx, invitation.pk, now=invitation.expires_at)

    assert (early, on_time) == (False, True)
    assert status_of(invitation) == InvitationStatus.EXPIRED
    assert len(expired_events(recorded)) == 1


# --- Beat ----------------------------------------------------------------------------------------


def test_AC_TEN_37_expiry_is_scheduled_every_hour() -> None:
    entry = celery_app.conf.beat_schedule[beat.EXPIRE_TASK]

    assert entry == beat.SCHEDULE[beat.EXPIRE_TASK]
    assert entry["task"] == "tenancy.expire_invitations"
    assert entry["schedule"] == crontab(minute=37)
    assert 0 < entry["options"]["expires"] <= 3600
    # The identity entry is still there: each app adds its own.
    assert "identity.purge_auth_data" in celery_app.conf.beat_schedule


def test_AC_TEN_37_expiry_tasks_are_registered_under_their_names() -> None:
    celery_app.loader.import_default_modules()

    # Bound (``bind=True``): each access is a new bound method of the same task and function.
    assert celery_app.tasks["tenancy.expire_invitations"].run == expire_invitations.run
    assert celery_app.tasks["tenancy.expire_invitation"].run is expire_invitation.run
    assert expire_invitations.__module__ == "apps.tenancy.tasks"
