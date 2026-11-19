"""The probe's tasks (design.md §3.6, §9): a server-to-server write stands for a ``pending`` charge.

``rename_widget`` is what a webhook or the poller of 06/07 will do: a ``TenantTask`` that runs in
the organization of its ``organization_id``, takes the write lock and writes through ``for_tenant``.
``rename_every_widget`` is the fan-out side: it lists ``(organization_id, id)`` of every
organization with ``unscoped(SYSTEM_FANOUT)`` and enqueues one ``rename_widget`` per row.
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.common.tenancy.celery import SystemFanoutTask, TenantTask
from apps.common.tenancy.current import require_current_tenant
from apps.common.tenancy.locks import ensure_writable
from apps.common.tenancy.querysets import UnscopedReason
from tests.testapps.tenant_probe.models import Widget

RENAME_TASK = "tenant_probe.rename_widget"
FANOUT_TASK = "tenant_probe.rename_every_widget"


@shared_task(base=TenantTask, name=RENAME_TASK, ignore_result=True)
def rename_widget(*, organization_id: str, widget_id: str, name: str) -> None:
    ctx = require_current_tenant()
    with transaction.atomic():
        ensure_writable(ctx)
        Widget.objects.for_tenant(ctx).filter(pk=uuid.UUID(widget_id)).update(name=name)


@shared_task(base=SystemFanoutTask, bind=True, name=FANOUT_TASK, ignore_result=True)
def rename_every_widget(self: Any, *, name: str) -> int:
    rows = Widget.objects.unscoped(UnscopedReason.SYSTEM_FANOUT)
    jobs = rows.values_list("organization_id", "id")
    count = 0
    for organization_id, widget_id in jobs:
        self.fan_out(rename_widget, organization_id, widget_id=str(widget_id), name=name)
        count += 1
    return count
