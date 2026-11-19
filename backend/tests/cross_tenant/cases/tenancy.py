"""SPEC-02's routes (``apps/tenancy/api/``).

Every ``TenantViewSet`` route of the module registers one ``CrossTenantCase`` per method here, in
the PR that adds it (DoD, ``tasks.md``). A route that runs without an active organization
(``GET /api/organizations/``, accepting an invitation, design.md §3.5) goes to ``EXEMPT`` with its
reason; a ``GET`` behind the login also gives ``read``, the URL the suite reads as A's member to
check it is scoped to the person. Until a route exists, its entry would be stale: the walker fails
on both. The first one is ``GET /api/organizations/`` (T-TEN-12).

``/api/organizations/current/`` (T-TEN-13) names no object: the organization is the header's.
``SEEDS`` adds the organization's own editable row, so the suite sees an edit that lands on B, or
on A while it is suspended.
"""

from __future__ import annotations

from typing import Any

from apps.tenancy.models import Organization
from tests.cross_tenant.registry import CrossTenantCase, Exemption, Seed
from tests.tenancy.api.probe import PLATFORM

_MINE = (
    "ruta de alcance de usuario: las organizaciones de la persona, exenta de la organización activa"
    " (design.md §3.5)"
)
CURRENT = "api/organizations/current/"
_FIELDS = ("id", "name", "legal_name", "tax_id", "timezone", "status")


def _current(organization: Organization) -> str:
    return f"/{CURRENT}"


def _renamed(organization: Organization) -> dict[str, str]:
    return {"name": f"renamed-in-{organization.name}", "legal_name": "Razón social nueva"}


def _no_rows(organization: Organization) -> None:
    """The organization row already exists: the suite created it."""


def _organization_row(organization: Organization) -> frozenset[tuple[Any, ...]]:
    rows = Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk)
    return frozenset(rows.values_list(*_FIELDS))


CASES: tuple[CrossTenantCase, ...] = (
    CrossTenantCase(CURRENT, "GET", _current),
    CrossTenantCase(CURRENT, "PATCH", _current, body=_renamed),
)
EXEMPT: tuple[Exemption, ...] = (
    Exemption("api/organizations/", _MINE, read=lambda organization: "/api/organizations/"),
)
SEEDS: tuple[Seed, ...] = (Seed(create=_no_rows, rows=_organization_row),)
