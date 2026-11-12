"""The active tenant of the current request or task (RF-TEN-01, design.md §3.1).

One ``ContextVar``, so threads and asyncio tasks never see each other's tenant.
``tenant_scope(ctx)`` sets it for a block (tasks, commands, tests): it binds ``organization_id`` to
the structlog context (C-16) and, on exit (also on an exception), restores both the variable and
the log key to what they were before, so a nested scope gives the outer one back. A request cannot
wrap its view in ``with``: the DRF permission calls ``activate_tenant(ctx)`` (same check and log
binding, no restore) and ``TenantContextMiddleware`` clears both when the request ends
(``clear_tenant``).

``require_current_tenant()`` raises ``TenantContextMissingError``: reaching business code without a
tenant is a bug, answered as a generic 500, never as data.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from structlog.contextvars import bind_contextvars, reset_contextvars, unbind_contextvars

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import TenantContextMissingError

_current: ContextVar[TenantContext | None] = ContextVar("hub_tenant_context", default=None)


def _check(ctx: TenantContext) -> None:
    if not isinstance(ctx, TenantContext):
        raise TypeError("a TenantContext is required")


@contextmanager
def tenant_scope(ctx: TenantContext) -> Iterator[TenantContext]:
    _check(ctx)
    token = _current.set(ctx)
    log_tokens = bind_contextvars(organization_id=str(ctx.organization_id))
    try:
        yield ctx
    finally:
        reset_contextvars(**log_tokens)
        _current.reset(token)


def current_tenant() -> TenantContext | None:
    return _current.get()


def require_current_tenant() -> TenantContext:
    ctx = _current.get()
    if ctx is None:
        raise TenantContextMissingError
    return ctx


def activate_tenant(ctx: TenantContext) -> None:
    """For the request's DRF permission only: active until ``TenantContextMiddleware`` clears it."""
    _check(ctx)
    _current.set(ctx)
    bind_contextvars(organization_id=str(ctx.organization_id))


def clear_tenant() -> None:
    """For ``TenantContextMiddleware`` only: no tenant and no ``organization_id`` log key."""
    _current.set(None)
    unbind_contextvars("organization_id")
