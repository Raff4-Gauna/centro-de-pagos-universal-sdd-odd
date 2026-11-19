"""A local branch of an organization (RF-TEN-06, RN-TEN-15, RN-TEN-19, design.md §5).

A ``Branch`` is the Hub's own branch, not a Mercado Pago Store (RN-TEN-15, glossary). A
``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). The services normalize what is stored (``services/branches.py``: spaces
removed at both ends); the constraints are the final net even if a service fails (ADR-0002 §2):

- ``branch_unique_active_name``: among the active branches of one organization, a name appears
  once, without telling upper from lower case ("Centro" and "centro" collide, Q-226);
- ``branch_unique_active_code``: an informed ``code`` appears once among the active branches of one
  organization, exact; an empty one never collides (Q-227);
- both are partial on ``is_active``: an inactive branch frees its name and code (AC-TEN-38);
- ``branch_name_not_blank``: a branch always has a name;
- ``branch_org_id_uniq``: ``(organization_id, id)`` unique, the target of the composite foreign
  keys of SPEC-04/05, so a link of a branch with an integration, a Store or a register can only
  name a branch of its own organization (RN-TEN-15).

``branch_org_active_name`` serves the listing (by organization, maybe by ``is_active``, by name).
A branch is never deleted (``NoHardDeleteMixin``): it is deactivated and can be reactivated
(RN-TEN-19, Q-211; T-TEN-25).
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from apps.common.tenancy.models import NoHardDeleteMixin, TenantModel

NAME_MAX_LENGTH = 120
CODE_MAX_LENGTH = 32
ADDRESS_MAX_LENGTH = 255


class Branch(NoHardDeleteMixin, TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    code = models.CharField(max_length=CODE_MAX_LENGTH, blank=True, default="")
    address = models.CharField(max_length=ADDRESS_MAX_LENGTH, blank=True, default="")
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                F("organization"),
                Lower("name"),
                condition=Q(is_active=True),
                name="branch_unique_active_name",
            ),
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=Q(is_active=True) & ~Q(code=""),
                name="branch_unique_active_code",
            ),
            models.CheckConstraint(condition=~Q(name=""), name="branch_name_not_blank"),
            models.UniqueConstraint(fields=["organization", "id"], name="branch_org_id_uniq"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["organization", "is_active", "name"], name="branch_org_active_name"
            ),
        ]

    def __str__(self) -> str:
        return str(self.pk)
