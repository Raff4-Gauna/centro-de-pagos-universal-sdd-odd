"""The organization, root of every tenant (spec §9, design.md §5, ADR-0002).

It is not a ``TenantModel`` (it *is* the tenant), but its manager fails closed all the same:
``for_tenant(ctx)`` reads only the organization of the context and ``unscoped(reason)`` is for the
operator's commands and the request resolution (AC-TEN-11). Enums are ``varchar`` plus a
``CheckConstraint``. ``timezone`` and the CUIT check digit are validated by the services that
write them (design.md §5); the database only keeps the CUIT as 11 digits or empty.

``save()`` goes through the base manager, without scope: it keeps the ``pk`` the instance was read
from (``org.pk = other.pk`` would overwrite the other organization) and, under a tenant, saves only
that organization (``guard_organization_save``). Without a tenant, the operator's commands create
and update any of them.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any, ClassVar, Self

from django.db import models
from django.db.models import Q

from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.models import (
    NoHardDeleteMixin,
    guard_organization_save,
    remember_saved_pk,
)
from apps.common.tenancy.querysets import TenantQuerySet

DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"


class OrganizationQuerySet(TenantQuerySet["Organization"]):
    tenant_lookup = "pk"


OrganizationManager = models.Manager.from_queryset(OrganizationQuerySet)


class Organization(NoHardDeleteMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    legal_name = models.CharField(max_length=200, blank=True, default="")
    tax_id = models.CharField(max_length=11, blank=True, default="")
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    status = models.CharField(max_length=16, default=OrgStatus.ACTIVE.value)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    # NULL, not "": many organizations have no key and NULLs never collide in the unique index.
    platform_creation_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_by_operator = models.CharField(max_length=254)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[OrganizationManager] = OrganizationManager()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(status__in=[status.value for status in OrgStatus]),
                name="org_status_valid",
            ),
            models.CheckConstraint(condition=~Q(name=""), name="org_name_not_blank"),
            models.CheckConstraint(
                condition=Q(tax_id="") | Q(tax_id__regex=r"^[0-9]{11}$"),
                name="org_tax_id_digits",
            ),
        ]

    def __str__(self) -> str:
        return str(self.pk)

    def save(self, *args: Any, **kwargs: Any) -> None:
        guard_organization_save(self)
        super().save(*args, **kwargs)
        remember_saved_pk(self)

    @classmethod
    def from_db(cls, db: str | None, field_names: Collection[str], values: Collection[Any]) -> Self:
        organization = super().from_db(db, field_names, values)
        remember_saved_pk(organization)
        return organization
