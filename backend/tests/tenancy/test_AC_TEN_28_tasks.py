"""Tasks per organization (AC-TEN-28 s2s, RN-TEN-18, RF-TEN-08, design.md §3.6).

There are no charges yet, so the server-to-server event on a ``pending`` charge of a suspended
organization is ``tenant_probe.rename_widget``: a ``TenantTask`` that takes the write lock and
writes. ``Task.apply`` runs it through the same trace and signals as a worker (no broker).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from structlog.contextvars import get_contextvars

from apps.common.tenancy.celery import SystemFanoutTask, TenantTask
from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import current_tenant, tenant_scope
from apps.common.tenancy.errors import OrganizationNotFound
from apps.common.tenancy.querysets import TenantScopeError
from config import celery_app
from tests.tenancy.locking import new_org, new_widget, system_ctx, widget_name
from tests.testapps.tenant_probe.tasks import rename_every_widget, rename_widget

pytestmark = pytest.mark.django_db

seen: list[tuple[TenantContext | None, dict[str, Any]]] = []


@celery_app.task(base=TenantTask, name="tests.tenancy.who_runs")
def who_runs(*, organization_id: str) -> str:
    seen.append((current_tenant(), get_contextvars()))
    return organization_id


@celery_app.task(base=SystemFanoutTask, name="tests.tenancy.fan_out_nothing")
def fan_out_nothing(**kwargs: Any) -> None:
    seen.append((current_tenant(), get_contextvars()))


@pytest.fixture(autouse=True)
def clean() -> None:
    seen.clear()


def test_AC_TEN_28_system_task_runs_on_suspended_org() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)
    widget = new_widget(org)

    kwargs = {"organization_id": str(org.id), "widget_id": str(widget.id), "name": "after"}
    rename_widget.apply(kwargs=kwargs).get()

    assert widget_name(widget) == "after"


def test_AC_TEN_28_system_task_writes_only_in_its_organization() -> None:
    a, b = new_org("A"), new_org("B")
    widget_of_b = new_widget(b)

    kwargs = {"organization_id": str(a.id), "widget_id": str(widget_of_b.id), "name": "after"}
    rename_widget.apply(kwargs=kwargs).get()

    assert widget_name(widget_of_b) == "before"


def test_tenant_task_runs_in_a_system_scope_of_its_organization() -> None:
    org = new_org("A", OrgStatus.SUSPENDED)

    assert who_runs.apply(kwargs={"organization_id": str(org.id)}).get() == str(org.id)

    ((ctx, log_context),) = seen
    assert ctx == TenantContext(org.id, OrgStatus.SUSPENDED, SystemActor(SystemReason.CELERY))
    assert log_context["organization_id"] == str(org.id)
    assert "task_id" in log_context
    assert current_tenant() is None  # the scope ends with the task


def test_tenant_task_takes_a_uuid_too() -> None:
    org = new_org("A")

    who_runs.apply(kwargs={"organization_id": org.id}).get()

    assert seen[0][0] is not None
    assert seen[0][0].organization_id == org.id


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({}, TypeError),
        ({"organization_id": None}, TypeError),
        ({"organization_id": "not-a-uuid"}, ValueError),
        ({"organization_id": str(uuid.uuid4())}, OrganizationNotFound),
    ],
)
def test_tenant_task_without_a_valid_organization_does_not_run(
    kwargs: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        who_runs.apply(kwargs=kwargs).get()

    assert seen == []


def test_tenant_task_rejects_organization_id_as_a_positional_argument() -> None:
    org = new_org("A")

    with pytest.raises(TypeError):
        who_runs.apply(args=(str(org.id),)).get()

    assert seen == []


def test_fanout_task_runs_without_a_tenant() -> None:
    fan_out_nothing.apply().get()

    ((ctx, log_context),) = seen
    assert ctx is None
    assert "organization_id" not in log_context


def test_fanout_task_takes_no_organization() -> None:
    org = new_org("A")

    with pytest.raises(TypeError):
        fan_out_nothing.apply(kwargs={"organization_id": str(org.id)}).get()

    assert seen == []


def test_fanout_task_does_not_run_inside_a_tenant() -> None:
    org = new_org("A")

    with tenant_scope(system_ctx(org.id)), pytest.raises(TenantScopeError):
        fan_out_nothing.apply().get()

    assert seen == []


def test_fanout_enqueues_one_tenant_task_per_row(monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = new_org("A"), new_org("B", OrgStatus.SUSPENDED)
    widgets = {new_widget(a).id: a.id, new_widget(b).id: b.id}
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(rename_widget, "apply_async", lambda **options: sent.append(options))

    assert rename_every_widget.apply(kwargs={"name": "after"}).get() == 2

    by_widget = {uuid.UUID(job["kwargs"]["widget_id"]): job["kwargs"] for job in sent}
    assert {w: uuid.UUID(job["organization_id"]) for w, job in by_widget.items()} == widgets
    assert all(job["name"] == "after" for job in by_widget.values())


def test_fan_out_only_enqueues_tenant_tasks() -> None:
    org = new_org("A")

    with pytest.raises(TypeError):
        SystemFanoutTask.fan_out(fan_out_nothing, org.id)
