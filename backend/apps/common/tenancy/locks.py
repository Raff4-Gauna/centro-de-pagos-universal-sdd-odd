"""The status of the organization as a write sees it (RN-TEN-18, AC-TEN-28, design.md §3.6, §3.7).

The request resolution reads the status once, before the view runs; the operator may suspend the
organization in between. Every write of a user or an API key calls ``ensure_writable(ctx)`` inside
its transaction: ``lock_org_for_write`` re-reads the status with ``SELECT ... FOR KEY SHARE`` on the
organization row. The operator's suspension locks the row ``FOR UPDATE``, which conflicts with
``KEY SHARE``: a write that already holds the lock commits before the suspension, and one that comes
after waits for it and reads ``suspended``. ``KEY SHARE`` is compatible with itself and with the
``NO KEY UPDATE`` of a membership change or an edit of the organization, so writes never wait for
each other.

A ``SystemActor`` is never stopped by the suspension: the server-to-server events of a ``pending``
charge are still processed (RN-TEN-18); the other checks (status of the charge, idempotency) belong
to the module that owns it.

``system_context(organization_id, reason)`` is the context of a process without a user (a task, a
webhook, a command): it reads the real status. It lives here and not in ``context.py``, which stays
pure: this is the one module of ``common/tenancy`` with raw SQL (``_select_status``), because it
cannot import the organization model of ``apps.tenancy`` (``common`` is below it) and the manager of
that model needs a ``TenantContext`` to read at all. The table comes from ``settings.TENANT_MODEL``.

Waiting for a lock is bounded (``LOCK_TIMEOUT``, design.md §11): ``bounded_lock_wait`` sets it for
the lock only and gives the previous value back. A timeout raises the database's
``OperationalError`` and rolls back the write: a bug or a stuck transaction, answered as a 500.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Literal

from django.apps import apps
from django.conf import settings
from django.db import DatabaseError, connection
from django.db.transaction import TransactionManagementError

from apps.common.tenancy.context import OrgStatus, SystemActor, SystemReason, TenantContext
from apps.common.tenancy.current import current_tenant
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.common.tenancy.querysets import TenantScopeError

LOCK_TIMEOUT = "5s"

_LOCKS = {"none": "", "key_share": " FOR KEY SHARE"}


def require_transaction(operation: str) -> None:
    """A row lock outside a transaction ends with its statement: it would protect nothing."""
    if not connection.in_atomic_block:
        raise TransactionManagementError(f"{operation} needs transaction.atomic()")


@contextmanager
def bounded_lock_wait() -> Iterator[None]:
    """Locks taken in the block wait at most ``LOCK_TIMEOUT``; the previous value comes back."""
    require_transaction("bounded_lock_wait")
    previous = _execute("SELECT current_setting('lock_timeout')", ())
    _execute("SELECT set_config('lock_timeout', %s, true)", (LOCK_TIMEOUT,))
    try:
        yield
    except DatabaseError:
        # The error aborted the transaction (or its savepoint): its rollback restores the setting,
        # and no statement runs before it.
        raise
    except BaseException:
        _execute("SELECT set_config('lock_timeout', %s, true)", previous)
        raise
    _execute("SELECT set_config('lock_timeout', %s, true)", previous)


def lock_org_for_write(ctx: TenantContext) -> OrgStatus:
    """The status of ``ctx``'s organization, locked ``FOR KEY SHARE`` until the transaction ends."""
    _check(ctx)
    require_transaction("lock_org_for_write")
    with bounded_lock_wait():
        return _select_status(ctx.organization_id, "key_share")


def ensure_writable(ctx: TenantContext) -> OrgStatus:
    """``organization_suspended`` for a user or an API key; a ``SystemActor`` always writes."""
    status = lock_org_for_write(ctx)
    if status is OrgStatus.SUSPENDED and not isinstance(ctx.actor, SystemActor):
        raise OrganizationSuspended
    return status


def system_context(organization_id: uuid.UUID, reason: SystemReason) -> TenantContext:
    """The context of a process without a user, with the status the organization has now."""
    if not isinstance(organization_id, uuid.UUID):
        raise TypeError("organization_id must be a UUID")
    actor = SystemActor(reason)
    return TenantContext(organization_id, _select_status(organization_id, "none"), actor)


def _check(ctx: TenantContext) -> None:
    if not isinstance(ctx, TenantContext):
        raise TypeError("a TenantContext is required")
    active = current_tenant()
    if active is not None and active.organization_id != ctx.organization_id:
        raise TenantScopeError("lock of another organization than the active one")


def _select_status(organization_id: uuid.UUID, lock: Literal["none", "key_share"]) -> OrgStatus:
    table = connection.ops.quote_name(apps.get_model(settings.TENANT_MODEL)._meta.db_table)
    sql = f"SELECT status FROM {table} WHERE id = %s{_LOCKS[lock]}"  # noqa: S608 - names, not data
    row = _execute(sql, (organization_id,))
    if not row:
        raise OrganizationNotFound
    return OrgStatus(str(row[0]))


def _execute(sql: str, params: Sequence[Any]) -> tuple[Any, ...]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return () if row is None else tuple(row)
