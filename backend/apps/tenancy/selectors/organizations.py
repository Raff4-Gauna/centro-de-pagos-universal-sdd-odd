"""The active organization's own row (RF-TEN-03, design.md §3.3, §6).

Both read through ``Organization.objects.for_tenant(ctx)``: only the organization of the context,
never another one (AC-TEN-11). A context whose organization no longer exists is
``organization_not_found``, the body of an unknown one.

- ``get_organization(ctx)``: the data ``GET /api/organizations/current/`` shows;
- ``lock_organization(ctx)``: the same row ``FOR NO KEY UPDATE`` (its key never changes), for the
  edit of ``services/organizations.py``. Two edits of the organization run one after the other, so
  each one compares against the values the previous one left. It queues with the membership
  changes, which take the same lock (``selectors/locks.py``); a business write (``FOR KEY SHARE``)
  does not wait for it, and the operator's suspension (``FOR UPDATE``) does
  (``apps/common/tenancy/locks.py``).
"""

from __future__ import annotations

from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import OrganizationNotFound
from apps.common.tenancy.locks import bounded_lock_wait, require_transaction
from apps.tenancy.models import Organization


def get_organization(ctx: TenantContext) -> Organization:
    organization = Organization.objects.for_tenant(ctx).first()
    if organization is None:
        raise OrganizationNotFound
    return organization


def lock_organization(ctx: TenantContext) -> Organization:
    require_transaction("lock_organization")
    with bounded_lock_wait():
        organization = Organization.objects.for_tenant(ctx).select_for_update(no_key=True).first()
    if organization is None:
        raise OrganizationNotFound
    return organization
