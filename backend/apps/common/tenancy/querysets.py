"""Querysets that fail closed (RN-TEN-02, AC-TEN-11, design.md §3.4, ADR-0001).

A ``TenantQuerySet`` starts **unscoped**. It reaches the database only after one of:

- ``for_tenant(ctx)``: filters by ``tenant_lookup`` (``organization_id``; ``pk`` for the
  organization itself) and, if a tenant is active (``current_tenant()``), it must be the same one;
- ``unscoped(reason)``: deliberately global, with an ``UnscopedReason`` that the architecture test
  (T-TEN-04) only accepts in a whitelist of files.

Every method that runs SQL (``GUARDED_METHODS``; iteration, ``len``, ``bool`` and slicing go through
``_fetch_all``, the ``a*`` variants through their sync method) raises ``TenantScopeError`` before
touching the database when the queryset has neither. The scope survives ``filter``, ``values`` and
any other clone.

Two querysets combined into one query (``|``, ``&``, ``^``, ``union``, ``intersection``,
``difference``) run under the scope of the left one, so both must carry a scope and the two must
agree (the same organization, or both global). Anything else raises when combined: an unscoped
operand on either side, a plain queryset of the base manager, another organization.

``|``, ``&`` and ``^`` also reject a sliced operand: Django rebuilds it as
``_base_manager.filter(pk__in=...)``, a plain queryset that carries neither the scope nor these
guards. Combine first and slice the result, or use ``union``.

Known gap: an unscoped queryset used as a subquery (``__in=qs``) never runs by itself; the
architecture test catches it, and later RLS (ADR-0001).

Django's internals (forward FKs, ``refresh_from_db``, ``save``) use the model's base manager, which
stays a plain ``Manager``: the guard is for business code, which goes through ``objects``.

``TenantScopeError`` is a bug, never data: the API handler answers it with a generic 500.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Self, TypeVar

from django.db import models

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.current import current_tenant

_M = TypeVar("_M", bound=models.Model)


class UnscopedReason(StrEnum):
    """Why a query is deliberately global (design.md §3.3, §3.5, §3.6)."""

    TENANT_RESOLUTION = "tenant_resolution"
    PLATFORM_COMMAND = "platform_command"
    SYSTEM_FANOUT = "system_fanout"


Scope = TenantContext | UnscopedReason


class TenantScopeError(RuntimeError):
    """A tenant query was about to run without ``for_tenant(ctx)`` or ``unscoped(reason)``."""


class HardDeleteForbidden(RuntimeError):  # noqa: N818 - the name design.md §3.4 publishes
    """A model with ``NoHardDeleteMixin`` is deactivated or revoked, never deleted."""

    def __init__(self, model: str) -> None:
        super().__init__(f"{model} rows are never deleted")


# Methods of ``QuerySet`` that run SQL. ``_insert``/``_update``/``_raw_delete`` are what
# ``bulk_create``, ``update`` and the deletion collector call underneath.
GUARDED_METHODS = (
    "_fetch_all",
    "iterator",
    "aiterator",
    "count",
    "exists",
    "contains",
    "aggregate",
    "explain",
    "get",
    "in_bulk",
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
)
DELETE_METHODS = frozenset({"delete", "_raw_delete"})


class TenantQuerySet(models.QuerySet[_M]):
    tenant_lookup = "organization_id"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._scope: Scope | None = None

    @property
    def scope(self) -> Scope | None:
        return self._scope

    def for_tenant(self, ctx: TenantContext) -> Self:
        if not isinstance(ctx, TenantContext):
            raise TypeError("for_tenant needs a TenantContext")
        active = current_tenant()
        if active is not None and active.organization_id != ctx.organization_id:
            raise TenantScopeError(f"{self._model_name()}: for_tenant with another organization")
        clone = self.filter(**{self.tenant_lookup: ctx.organization_id})
        clone._scope = ctx
        return clone

    def unscoped(self, reason: UnscopedReason) -> Self:
        if not isinstance(reason, UnscopedReason):
            raise TypeError("unscoped needs an UnscopedReason")
        clone = self.all()
        clone._scope = reason
        return clone

    def _require_scope(self, operation: str) -> None:
        if self._scope is None:
            raise TenantScopeError(
                f"{self._model_name()}.{operation} without for_tenant(ctx) or unscoped(reason)"
            )

    def _model_name(self) -> str:
        return getattr(self.model, "__name__", "?")

    def _clone(self) -> Self:
        clone = super()._clone()  # type: ignore[misc]
        clone._scope = self._scope
        return clone  # type: ignore[no-any-return]

    def _require_same_scope(self, other: Any, operation: str) -> None:
        """``other`` joins a query that runs under ``self._scope``: it must not widen it."""
        self._require_scope(operation)
        if not isinstance(other, TenantQuerySet):
            raise TenantScopeError(f"{self._model_name()}.{operation} with an unscoped queryset")
        other._require_scope(operation)
        if not _same_scope(self._scope, other._scope):
            raise TenantScopeError(f"{self._model_name()}.{operation} with a different scope")

    def _require_operands(self, other: Any, operation: str) -> None:
        self._require_same_scope(other, operation)
        if self.query.is_sliced or other.query.is_sliced:
            raise TenantScopeError(
                f"{self._model_name()}.{operation} with a sliced queryset: slice the result instead"
            )

    def _combinator_query(self, combinator: str, *other_qs: Any, all: bool = False) -> Self:
        for other in other_qs:
            self._require_same_scope(other, combinator)
        return super()._combinator_query(combinator, *other_qs, all=all)  # type: ignore[misc, no-any-return]

    # ``a | b`` absorbs the empty WHERE of an unscoped operand and would run marked with the scope
    # of the other: checked here, before Django merges (or, with a slice, rebuilds) the queries.
    def __and__(self, other: Any) -> Self:
        self._require_operands(other, "__and__")
        return super().__and__(other)

    def __or__(self, other: Any) -> Self:
        self._require_operands(other, "__or__")
        return super().__or__(other)

    def __xor__(self, other: Any) -> Self:
        self._require_operands(other, "__xor__")
        # django-stubs has no ``QuerySet.__xor__`` (Django added it in 4.1).
        return super().__xor__(other)  # type: ignore[misc, no-any-return]

    def __repr__(self) -> str:
        """Never queries without a scope: a repr in a log or a failed assertion must not raise."""
        if self._scope is None:
            return f"<{type(self).__name__} {self._model_name()} unscoped>"
        return super().__repr__()


def _same_scope(left: Scope | None, right: Scope | None) -> bool:
    if isinstance(left, TenantContext) and isinstance(right, TenantContext):
        return left.organization_id == right.organization_id
    return isinstance(left, UnscopedReason) and isinstance(right, UnscopedReason)


def _guard(name: str) -> Callable[..., Any]:
    original = getattr(models.QuerySet, name)
    deletes = name in DELETE_METHODS

    @functools.wraps(original)
    def guarded(self: TenantQuerySet[Any], *args: Any, **kwargs: Any) -> Any:
        self._require_scope(name)
        if deletes and getattr(self.model, "hard_delete_forbidden", False):
            raise HardDeleteForbidden(self._model_name())
        return original(self, *args, **kwargs)

    return guarded


# Set after the class so that callers keep Django's typed signatures (django-stubs) and each
# wrapper keeps the attributes Django reads (``alters_data``, ``queryset_only`` via ``wraps``).
for _name in GUARDED_METHODS:
    setattr(TenantQuerySet, _name, _guard(_name))
