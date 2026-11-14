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

Under a tenant scope (``for_tenant``) some writes and reads do not carry the organization filter, so
they fail closed and are only allowed with ``unscoped(reason)``:

- ``bulk_create`` (and ``abulk_create``) with ``ignore_conflicts`` or ``update_conflicts``, and
  ``_insert`` with any ``on_conflict``: the ``INSERT ... ON CONFLICT`` has no ``WHERE`` and would
  touch the conflicting row of another organization.
- ``raw``: the SQL is written by hand and ignores the filter.

What a tenant scope inserts (``create``, ``get_or_create``, ``update_or_create``, ``bulk_create``,
``_insert``) belongs to the organization of the scope, checked without SQL on ``tenant_lookup``: an
empty one is filled with it (RN-TEN-04) and another one raises. For ``Organization`` the lookup is
its ``pk``, which is never empty: a tenant scope inserts no organization, and new organizations go
through ``unscoped(reason)``.

The organization of a row never changes through ``update``, ``_update`` or ``bulk_update`` (and
their ``a*`` variants), under any scope: ``organization``/``organization_id`` among the values or
fields raise (RN-TEN-04).

Assigning ``qs.query = ...`` replaces the filter with a query that may not have it, so it clears the
scope: the queryset fails closed until it is scoped again.

Known gap: an unscoped queryset used as a subquery (``__in=qs``) never runs by itself; the
architecture test catches it, and later RLS (ADR-0001).

Django's internals (forward FKs, ``refresh_from_db``, ``save``) use the model's base manager, which
stays a plain ``Manager``: the guard is for business code, which goes through ``objects``
(``TenantManager``). ``save`` and ``delete`` of an instance have their own guard, in
``TenantModel`` (``apps.common.tenancy.models``) and ``Organization``.

``TenantScopeError`` is a bug, never data: the API handler answers it with a generic 500.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Collection, Iterable
from enum import StrEnum
from typing import Any, Self, TypeVar

from django.db import models
from django.db.models.query import RawQuerySet
from django.db.models.sql.query import Query

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
_BASE_QUERY: property = vars(models.QuerySet)["query"]


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

    @property
    def query(self) -> Query:
        return _BASE_QUERY.fget(self)  # type: ignore[misc, no-any-return]

    @query.setter
    def query(self, value: Query) -> None:
        _BASE_QUERY.fset(self, value)  # type: ignore[misc]
        self._scope = None  # the new query may not carry the filter of the scope

    def bulk_create(
        self,
        objs: Iterable[_M],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list[_M]:
        self._require_scope("bulk_create")
        objs = list(objs)
        if isinstance(self._scope, TenantContext):
            if ignore_conflicts or update_conflicts:
                raise TenantScopeError(
                    f"{self._model_name()}.bulk_create on conflict needs unscoped(reason)"
                )
            self._pin_rows(objs, self._scope, "bulk_create")
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    bulk_create.alters_data = True  # type: ignore[attr-defined]  # as Django's

    def create(self, **kwargs: Any) -> _M:
        self._require_scope("create")
        if isinstance(self._scope, TenantContext):
            # Built once to read ``tenant_lookup`` as Django resolves it (``organization`` or
            # ``organization_id``, a default ``pk``); Django builds it again from ``kwargs``.
            probe = self.model(**kwargs)
            if getattr(probe, self.tenant_lookup) is None:
                kwargs[self.tenant_lookup] = self._scope.organization_id
            else:
                self._pin_rows([probe], self._scope, "create")
        return super().create(**kwargs)

    create.alters_data = True  # type: ignore[attr-defined]  # as Django's

    def _insert(
        self,
        objs: list[_M],
        fields: Any,
        returning_fields: Any = None,
        raw: bool = False,
        using: str | None = None,
        on_conflict: Any = None,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        """What ``bulk_create`` runs underneath, and anyone reaching past it."""
        self._require_scope("_insert")
        if isinstance(self._scope, TenantContext):
            if on_conflict is not None:
                raise TenantScopeError(f"{self._model_name()}._insert on conflict needs unscoped")
            self._pin_rows(objs, self._scope, "_insert")
        return super()._insert(  # type: ignore[misc]
            objs,
            fields,
            returning_fields=returning_fields,
            raw=raw,
            using=using,
            on_conflict=on_conflict,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )

    _insert.alters_data = True  # type: ignore[attr-defined]  # as Django's
    _insert.queryset_only = False  # type: ignore[attr-defined]  # as Django's

    def update(self, **kwargs: Any) -> int:
        self._require_scope("update")
        self._require_fixed_tenant(kwargs, "update")
        return super().update(**kwargs)

    update.alters_data = True  # type: ignore[attr-defined]  # as Django's

    def _update(self, values: Any) -> Any:
        """What ``update`` and ``Model.save()`` run underneath: (field, model, value) tuples."""
        self._require_scope("_update")
        self._require_fixed_tenant([field.name for field, _model, _value in values], "_update")
        return super()._update(values)  # type: ignore[misc]

    _update.alters_data = True  # type: ignore[attr-defined]  # as Django's
    _update.queryset_only = False  # type: ignore[attr-defined]  # as Django's

    def bulk_update(
        self, objs: Iterable[_M], fields: Iterable[str], batch_size: int | None = None
    ) -> int:
        self._require_scope("bulk_update")
        fields = list(fields)
        self._require_fixed_tenant(fields, "bulk_update")
        return super().bulk_update(objs, fields, batch_size=batch_size)

    bulk_update.alters_data = True  # type: ignore[attr-defined]  # as Django's

    def _require_fixed_tenant(self, names: Iterable[str], operation: str) -> None:
        """``names`` (field names or attnames) must not include the organization of the row."""
        if self.tenant_lookup == "pk":
            return  # ``Organization``: the row is the organization
        field = self.model._meta.get_field(self.tenant_lookup)
        if {field.name, getattr(field, "attname", field.name)} & set(names):
            raise TenantScopeError(
                f"{self._model_name()}.{operation} cannot change the organization"
            )

    def _pin_rows(self, objs: Iterable[_M], ctx: TenantContext, operation: str) -> None:
        """Rows inserted under ``ctx``: an empty ``tenant_lookup`` gets it, another one raises."""
        organization_id = ctx.organization_id
        for obj in objs:
            if getattr(obj, self.tenant_lookup) is None:
                setattr(obj, self.tenant_lookup, organization_id)
            elif getattr(obj, self.tenant_lookup) != organization_id:
                raise TenantScopeError(f"{self._model_name()}.{operation} for another organization")

    def raw(
        self,
        raw_query: Any,
        params: Any = (),
        translations: dict[str, str] | None = None,
        using: str | None = None,
    ) -> RawQuerySet[_M]:
        self._require_scope("raw")
        if isinstance(self._scope, TenantContext):
            raise TenantScopeError(f"{self._model_name()}.raw needs unscoped(reason)")
        return super().raw(raw_query, params, translations, using)

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
# The methods defined on the class (``create``, ``update``, ``bulk_create``, ``_insert``, ``raw``
# and the rest) check the scope themselves.
for _name in GUARDED_METHODS:
    if _name not in vars(TenantQuerySet):
        setattr(TenantQuerySet, _name, _guard(_name))

# ``objects`` of every ``TenantModel`` (design.md §3.4): its querysets start unscoped.
TenantManager = models.Manager.from_queryset(TenantQuerySet)
