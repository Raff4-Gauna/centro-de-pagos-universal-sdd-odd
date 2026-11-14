"""Model bases of the tenant (design.md §3.1, §3.4, ADR-0001, ADR-0002).

``TenantModel``: every business table (RN-TEN-01). Its ``organization`` is a ``PROTECT`` FK to
``settings.TENANT_MODEL`` without reverse accessor (``related_name="+"``) and out of forms and
serializers (``editable=False``): the organization of a write comes from the validated context,
never from the client (RN-TEN-04). ``objects`` is a ``TenantManager``: its querysets fail closed
(AC-TEN-11). ``save()`` and ``delete()`` go through the base manager, which carries no scope, so
they have their own guard (AC-TEN-07):

- a tenant must be active (``tenant_scope``); without one they raise ``TenantScopeError``;
- ``save()`` fills an empty ``organization`` with the active one and rejects another one;
- ``organization`` and ``pk`` do not change once the row was read or saved;
- the ``UPDATE`` of ``save()`` also filters by organization: a row of another organization with the
  same ``pk`` is never written (the ``INSERT`` that Django tries next fails on the primary key);
- ``delete()`` first checks that the row of that ``pk`` belongs to the active organization.

``Organization`` keeps its ``pk`` the same way (``guard_organization_save``): ``org.pk = other.pk``
followed by ``save()`` would otherwise overwrite the other organization.

``NoHardDeleteMixin``: ``Organization``, ``Membership``, ``Invitation`` and ``Branch`` are
deactivated or revoked, never deleted. ``Model.delete()`` raises here and ``QuerySet.delete()`` in
``TenantQuerySet`` (it reads ``hard_delete_forbidden``); every FK to these tables is ``PROTECT``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Any, ClassVar, Self

from django.conf import settings
from django.db import models

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.current import current_tenant
from apps.common.tenancy.querysets import HardDeleteForbidden, TenantManager, TenantScopeError

# What an instance was read from or last saved to; absent on a new instance.
_SAVED_PK = "_tenant_saved_pk"
_SAVED_ORGANIZATION = "_tenant_saved_organization_id"


class NoHardDeleteMixin:
    hard_delete_forbidden: ClassVar[bool] = True

    def delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        raise HardDeleteForbidden(type(self).__name__)


def remember_saved_pk(instance: models.Model) -> None:
    setattr(instance, _SAVED_PK, instance.pk)


def require_same_pk(instance: models.Model, operation: str) -> None:
    """``pk`` may be cleared (Django's copy idiom: a new row), never pointed at another row."""
    saved = getattr(instance, _SAVED_PK, None)
    if saved is not None and instance.pk is not None and instance.pk != saved:
        raise TenantScopeError(f"{type(instance).__name__}.{operation} with a changed pk")


def guard_organization_save(organization: models.Model) -> None:
    """``Organization.save()``: same ``pk``, and under a tenant only that organization."""
    require_same_pk(organization, "save")
    active = current_tenant()
    if active is not None and organization.pk != active.organization_id:
        raise TenantScopeError(f"{type(organization).__name__}.save of another organization")


class TenantModel(models.Model):
    organization = models.ForeignKey(
        settings.TENANT_MODEL, on_delete=models.PROTECT, related_name="+", editable=False
    )

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        ctx = self._require_tenant("save")
        if self.organization_id is None:
            self.organization_id = ctx.organization_id
        elif self.organization_id != ctx.organization_id:
            raise TenantScopeError(f"{type(self).__name__}.save for another organization")
        require_same_pk(self, "save")
        saved_organization = getattr(self, _SAVED_ORGANIZATION, None)
        if saved_organization is not None and saved_organization != self.organization_id:
            raise TenantScopeError(f"{type(self).__name__}.save with a changed organization")
        super().save(*args, **kwargs)
        self._remember_saved()

    def delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        ctx = self._require_tenant("delete")
        require_same_pk(self, "delete")
        own_row = (
            type(self)
            ._base_manager.using(using)
            .filter(pk=self.pk, organization_id=ctx.organization_id)
        )
        if self.organization_id != ctx.organization_id or not own_row.exists():
            raise TenantScopeError(f"{type(self).__name__}.delete of another organization")
        return super().delete(using, keep_parents)

    @classmethod
    def from_db(cls, db: str | None, field_names: Collection[str], values: Collection[Any]) -> Self:
        instance = super().from_db(db, field_names, values)
        instance._remember_saved()
        return instance

    def _do_update(
        self,
        base_qs: models.QuerySet[Self],
        using: str | None,
        pk_val: Any,
        values: Collection[tuple[models.Field[Any, Any], type[models.Model] | None, Any]],
        update_fields: Iterable[str] | None,
        forced_update: bool,
    ) -> bool:
        # Checked against the context by ``save()``: the UPDATE never reaches another organization.
        scoped = base_qs.filter(organization_id=self.organization_id)
        return super()._do_update(scoped, using, pk_val, values, update_fields, forced_update)

    def _require_tenant(self, operation: str) -> TenantContext:
        ctx = current_tenant()
        if ctx is None:
            raise TenantScopeError(f"{type(self).__name__}.{operation} without an active tenant")
        return ctx

    def _remember_saved(self) -> None:
        remember_saved_pk(self)
        # From ``__dict__``: a deferred ``organization`` must not cost a query here.
        setattr(self, _SAVED_ORGANIZATION, self.__dict__.get("organization_id"))
