"""The branches of the active organization (RF-TEN-06, RN-TEN-05, design.md §3.3, §6).

``list_branches(ctx, is_active)`` reads only the organization of ``ctx``
(``Branch.objects.for_tenant``): a branch of another organization is never listed. ``is_active``
``None`` lists active and inactive ones alike: an inactive branch is still listed, marked as such
(AC-TEN-30). Ordered by name, then id, so a page never repeats or skips one; the index
``branch_org_active_name`` serves it.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.common.tenancy.context import TenantContext
from apps.tenancy.models import Branch


def list_branches(ctx: TenantContext, *, is_active: bool | None = None) -> QuerySet[Branch]:
    branches = Branch.objects.for_tenant(ctx)
    if is_active is not None:
        branches = branches.filter(is_active=is_active)
    return branches.order_by("name", "id")
