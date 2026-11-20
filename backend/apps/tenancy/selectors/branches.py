"""The branches of the active organization (RF-TEN-06, RN-TEN-05, RN-TEN-15, design.md §3.3, §6).

Every read goes through ``Branch.objects.for_tenant(ctx)``: a branch of another organization is
never listed nor found.

- ``list_branches(ctx, is_active)``: ``is_active`` ``None`` lists active and inactive ones alike: an
  inactive branch is still listed, marked as such (AC-TEN-30). Ordered by name, then id, so a page
  never repeats or skips one; the index ``branch_org_active_name`` serves it.
- ``get_branch(ctx, branch_id)``: one branch, active or not, or ``404 not_found`` with the same body
  for one of another organization and one that does not exist (AC-TEN-01). It is also how SPEC-04/05
  check that a branch they link belongs to the organization (RN-TEN-15, design.md §6).
- ``lock_branch(ctx, branch_id)``: the same row ``FOR NO KEY UPDATE`` (its key never changes, and
  the composite foreign keys of SPEC-04/05 point at it), for the edits of ``services/branches.py``:
  two changes of one branch run one after the other, each on what the previous one left.
"""

from __future__ import annotations

import uuid

from django.db.models import QuerySet
from rest_framework.exceptions import NotFound

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.locks import bounded_lock_wait, require_transaction
from apps.tenancy.models import Branch

BRANCH_NOT_FOUND = "La sucursal no existe."


def list_branches(ctx: TenantContext, *, is_active: bool | None = None) -> QuerySet[Branch]:
    branches = Branch.objects.for_tenant(ctx)
    if is_active is not None:
        branches = branches.filter(is_active=is_active)
    return branches.order_by("name", "id")


def get_branch(ctx: TenantContext, branch_id: uuid.UUID) -> Branch:
    branch = Branch.objects.for_tenant(ctx).filter(pk=branch_id).first()
    if branch is None:
        raise NotFound(BRANCH_NOT_FOUND)
    return branch


def lock_branch(ctx: TenantContext, branch_id: uuid.UUID) -> Branch:
    require_transaction("lock_branch")
    with bounded_lock_wait():
        branches = Branch.objects.for_tenant(ctx).select_for_update(no_key=True)
        branch = branches.filter(pk=branch_id).first()
    if branch is None:
        raise NotFound(BRANCH_NOT_FOUND)
    return branch
