"""The link of a ``Branch`` with an ``Integration`` (RN-INT-13, RN-INT-23, Q-410, design.md §5).

A ``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). It keeps the opaque reference to the provider's counterpart (in Mercado
Pago, the Store; RN-TEN-15: a ``Branch`` is not a Store) and the data the adapter declares in its
schema, validated by the services (RN-INT-23). The constraints are the final net even if a service
fails (ADR-0002 §2):

- ``branch_link_one_per_pair``: at most one link per ``Branch`` + integration, **in any state**:
  an inactive link is reactivated, never created again (Q-429, AC-INT-43). It is also the target
  of the register's composite key on ``(organization_id, branch_id, integration_id)`` (T-INT-04);
- ``branch_link_unique_store_ref``: an informed Store reference once per integration, active or
  not (Q-432 a)); links without a reference never collide;
- ``branch_link_store_origin_valid`` and ``branch_link_store_ref_coherent``: the reference was
  created, imported or typed by hand, or there is none (``none`` exactly when it is empty; Q-424);
- ``branch_link_active_coherent``: ``deactivated_at`` exactly when inactive;
- ``branch_link_branch_same_org`` and ``branch_link_integration_same_org`` (migration ``0003``,
  ``RunSQL``): composite foreign keys to ``tenancy_branch (organization_id, id)``
  (``branch_org_id_uniq``) and to ``integrations_integration (organization_id, id)``
  (``integration_org_id_uniq``), so the three belong to one organization, also for a row written
  without the ORM (RN-INT-13, design.md §5.1). Django 5.2 cannot declare them; the plain FKs are for
  the ORM and keep their own index (none of the composite ones leads with their column).

``branch_link_org_branch_active`` and ``branch_link_org_integ_active`` serve the listings by branch
and by integration. A link is never deleted (``NoHardDeleteMixin``): it is deactivated and can be
reactivated. Its ``str`` and ``repr`` carry only the id.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.tenancy.models import NoHardDeleteMixin, TenantModel
from apps.integrations.models.integration import Integration
from apps.tenancy.models import Branch

STORE_REF_MAX_LENGTH = 128


class StoreOrigin(StrEnum):
    """How the link got its Store reference (RN-INT-23, Q-424)."""

    CREATED = "created"
    IMPORTED = "imported"
    MANUAL = "manual"
    NONE = "none"


_NO_REF = Q(store_origin=StoreOrigin.NONE.value)
_EMPTY_REF = Q(store_ref="")


class BranchLink(NoHardDeleteMixin, TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    integration = models.ForeignKey(Integration, on_delete=models.PROTECT, related_name="+")
    store_ref = models.CharField(max_length=STORE_REF_MAX_LENGTH, blank=True, default="")
    store_origin = models.CharField(max_length=16)
    data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["organization", "branch", "integration"], name="branch_link_one_per_pair"
            ),
            models.CheckConstraint(
                condition=Q(store_origin__in=[origin.value for origin in StoreOrigin]),
                name="branch_link_store_origin_valid",
            ),
            models.CheckConstraint(
                condition=(_NO_REF & _EMPTY_REF) | (~_NO_REF & ~_EMPTY_REF),
                name="branch_link_store_ref_coherent",
            ),
            models.UniqueConstraint(
                fields=["integration", "store_ref"],
                condition=~_EMPTY_REF,
                name="branch_link_unique_store_ref",
            ),
            models.CheckConstraint(
                condition=Q(is_active=True, deactivated_at__isnull=True)
                | Q(is_active=False, deactivated_at__isnull=False),
                name="branch_link_active_coherent",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["organization", "branch", "is_active"],
                name="branch_link_org_branch_active",
            ),
            models.Index(
                fields=["organization", "integration", "is_active"],
                name="branch_link_org_integ_active",
            ),
        ]

    def __str__(self) -> str:
        """The id: a link in a log carries neither its Store reference nor its data."""
        return str(self.pk)
