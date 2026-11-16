"""The scopes of a ``TenantQuerySet`` (RN-TEN-02, design.md §3.4, ADR-0001).

A queryset reaches the database only under one of:

- a ``TenantContext`` (``for_tenant(ctx)``): one organization, reads and writes;
- an ``UnscopedReason`` (``unscoped(reason)``): deliberately global, in the files the architecture
  test allows;
- a ``ModelScope``: a read that a model declares itself (``Membership.for_user(user_id)``), whose
  filter is the scope. It crosses organizations, so there is no organization to pin a write to:
  every write and ``raw`` fails closed under it (``READ_ONLY_REJECTED``). The architecture test lets
  ``X.objects.<scope>(...)`` through only for the model that declares it
  (``allowlists.MODEL_SCOPES``).

Two querysets combined into one query must share the scope (``same_scope``): the same organization,
both global, or the same model scope with the same value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apps.common.tenancy.context import TenantContext


class UnscopedReason(StrEnum):
    """Why a query is deliberately global (design.md §3.3, §3.5, §3.6)."""

    TENANT_RESOLUTION = "tenant_resolution"
    PLATFORM_COMMAND = "platform_command"
    SYSTEM_FANOUT = "system_fanout"


@dataclass(frozen=True, slots=True)
class ModelScope:
    """A read scope a model declares: ``name`` is its method, ``value`` what it filters by."""

    name: str
    value: object


Scope = TenantContext | UnscopedReason | ModelScope

# What a ``ModelScope`` refuses: it would write, delete or run SQL the filter does not reach.
READ_ONLY_REJECTED = frozenset(
    {
        "create",
        "bulk_create",
        "bulk_update",
        "get_or_create",
        "update_or_create",
        "update",
        "delete",
        "raw",
        "_insert",
        "_update",
        "_raw_delete",
    }
)


def same_scope(left: Scope | None, right: Scope | None) -> bool:
    if isinstance(left, TenantContext) and isinstance(right, TenantContext):
        return left.organization_id == right.organization_id
    if isinstance(left, ModelScope) or isinstance(right, ModelScope):
        return left == right
    return isinstance(left, UnscopedReason) and isinstance(right, UnscopedReason)
