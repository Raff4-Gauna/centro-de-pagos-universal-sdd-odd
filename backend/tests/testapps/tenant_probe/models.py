"""The probe's tenant table (design.md §9): the smallest ``TenantModel`` with a field to write."""

from __future__ import annotations

import uuid

from django.db import models

from apps.common.tenancy.models import TenantModel


class Widget(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)

    def __str__(self) -> str:
        return str(self.pk)
