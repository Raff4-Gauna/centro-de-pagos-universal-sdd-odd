"""Celery tasks that carry their organization (RF-TEN-08, RN-TEN-18, design.md §3.6, ADR-0001).

A process without a user fixes the organization of what it processes before it touches business
data. Two bases, given with ``@shared_task(base=...)``:

- ``TenantTask``: ``organization_id`` is a **keyword** argument (a UUID, or its text as it comes
  out of the JSON message). Before the body runs, ``__call__`` opens
  ``tenant_scope(system_context(organization_id, SystemReason.CELERY))``: the selectors read with
  ``for_tenant(ctx)`` as in a request and ``organization_id`` goes to every log event of the task
  (``task_id`` and ``request_id`` are bound by ``apps/common/celery_signals.py``). Missing, not a
  UUID or of an unknown organization: the task fails before its body, which never runs without a
  tenant. ``ensure_writable`` does not stop it on a suspended organization (``locks.py``). It
  does not run inside an active tenant either (``Task.apply`` or a direct call in a request or
  another task): it would switch organization, or turn a user, whom the suspension stops, into a
  system actor, whom it does not (review of PR #117).
- ``SystemFanoutTask``: the work of several organizations (the poller, the expiry of invitations).
  It runs with **no** tenant and takes no ``organization_id``; its body only lists
  ``(organization_id, id)`` with ``unscoped(UnscopedReason.SYSTEM_FANOUT)`` and hands each pair to
  ``fan_out``, which enqueues a ``TenantTask``: business data is processed there, never here.
  ``fan_out`` refuses to run inside a tenant, so a task of one organization cannot enqueue work
  for another through it.

Celery acknowledges a message before it runs the task (``acks_late`` is off), so a task that fails
is not delivered again: a lock timeout (``OperationalError``, ``locks.py``) ends it in ``FAILURE``.
A server-to-server consumer (SPEC-06/07) declares ``autoretry_for=(OperationalError,)`` with a
backoff, or the event is lost; ``retry()`` keeps the kwargs, ``organization_id`` included.

Celery calls ``__call__`` of a task that overrides it, in the worker and in ``Task.apply``; the
scope is a ``ContextVar``, so the tasks of one worker never see each other's tenant.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from celery import Task

from apps.common.tenancy.context import SystemReason
from apps.common.tenancy.current import current_tenant, tenant_scope
from apps.common.tenancy.locks import system_context
from apps.common.tenancy.querysets import TenantScopeError

ORGANIZATION_KWARG = "organization_id"

# The stubs make ``Task`` generic; the class itself is not subscriptable at runtime.
if TYPE_CHECKING:
    _BaseTask = Task[Any, Any]
else:
    _BaseTask = Task


class TenantTask(_BaseTask):
    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        organization_id = _organization_id(kwargs.get(ORGANIZATION_KWARG))
        if current_tenant() is not None:
            raise TenantScopeError("a TenantTask does not run inside a tenant: enqueue it")
        with tenant_scope(system_context(organization_id, SystemReason.CELERY)):
            return super().__call__(*args, **kwargs)


class SystemFanoutTask(_BaseTask):
    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if ORGANIZATION_KWARG in kwargs:
            raise TypeError("a SystemFanoutTask takes no organization_id: enqueue a TenantTask")
        if current_tenant() is not None:
            raise TenantScopeError("a SystemFanoutTask runs without a tenant")
        return super().__call__(*args, **kwargs)

    @staticmethod
    def fan_out(task: Any, organization_id: uuid.UUID | str, **kwargs: Any) -> None:
        """Enqueue ``task``, a ``TenantTask``, for one organization of the fan-out."""
        if not isinstance(task, TenantTask):
            raise TypeError("fan_out enqueues TenantTask tasks only")
        if current_tenant() is not None:
            raise TenantScopeError("fan_out runs without a tenant, in a SystemFanoutTask")
        kwargs[ORGANIZATION_KWARG] = str(_organization_id(organization_id))
        task.apply_async(kwargs=kwargs)


def _organization_id(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        raise TypeError("a TenantTask needs organization_id as a keyword argument")
    return uuid.UUID(value)  # ValueError if it is not one
