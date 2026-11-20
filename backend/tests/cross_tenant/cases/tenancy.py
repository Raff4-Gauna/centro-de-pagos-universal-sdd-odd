"""SPEC-02's routes (``apps/tenancy/api/``).

Every ``TenantViewSet`` route of the module registers one ``CrossTenantCase`` per method here, in
the PR that adds it (DoD, ``tasks.md``). A route that runs without an active organization
(``GET /api/organizations/``, ``POST /api/invitations/accept/``, design.md §3.5) goes to ``EXEMPT``
with its reason; a ``GET`` behind the login also gives ``read``, the URL the suite reads as A's
member to check it is scoped to the person. Until a route exists, its entry would be stale: the
walker fails on both. The first one is ``GET /api/organizations/`` (T-TEN-12).

``/api/organizations/current/`` (T-TEN-13) names no object: the organization is the header's.
``SEEDS`` adds the organization's own editable row, so the suite sees an edit that lands on B, or
on A while it is suspended.

``/api/branches/`` (T-TEN-24): two branches in each organization, one of them inactive, so a
listing that leaks B's rows, active or not, carries B's ids. A ``POST`` names the organization it
is built for in the name of the new branch; it can only land in the active one.
"""

from __future__ import annotations

from typing import Any

from apps.common.tenancy.current import tenant_scope
from apps.tenancy.models import Branch, Organization
from tests.cross_tenant.registry import CrossTenantCase, Exemption, Seed
from tests.tenancy.api.probe import PLATFORM, platform_ctx

_MINE = (
    "ruta de alcance de usuario: las organizaciones de la persona, exenta de la organización activa"
    " (design.md §3.5)"
)
_ACCEPT = (
    "aceptar una invitación con su token: la persona todavía no es miembro; la organización es la "
    "de la invitación, no la del header (design.md §3.5, §4.4)"
)
CURRENT = "api/organizations/current/"
_FIELDS = ("id", "name", "legal_name", "tax_id", "timezone", "status")
BRANCHES = "api/branches/"


def _current(organization: Organization) -> str:
    return f"/{CURRENT}"


def _renamed(organization: Organization) -> dict[str, str]:
    return {"name": f"renamed-in-{organization.name}", "legal_name": "Razón social nueva"}


def _no_rows(organization: Organization) -> None:
    """The organization row already exists: the suite created it."""


def _organization_row(organization: Organization) -> frozenset[tuple[Any, ...]]:
    rows = Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk)
    return frozenset(rows.values_list(*_FIELDS))


def _create_branches(organization: Organization) -> None:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        branches = Branch.objects.for_tenant(ctx)
        branches.create(name=f"{organization.name}-centro", code=f"{organization.name}-C01")
        branches.create(name=f"{organization.name}-norte", is_active=False)


def _branch_rows(organization: Organization) -> frozenset[tuple[Any, ...]]:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        rows = Branch.objects.for_tenant(ctx).values_list("id", "name", "code", "is_active")
        return frozenset(rows)


def _branches(organization: Organization) -> str:
    return f"/{BRANCHES}"


def _new_branch(organization: Organization) -> dict[str, str]:
    return {"name": f"nueva-en-{organization.name}"}


CASES: tuple[CrossTenantCase, ...] = (
    CrossTenantCase(CURRENT, "GET", _current),
    CrossTenantCase(CURRENT, "PATCH", _current, body=_renamed),
    CrossTenantCase(BRANCHES, "GET", _branches),
    CrossTenantCase(BRANCHES, "POST", _branches, body=_new_branch),
)
EXEMPT: tuple[Exemption, ...] = (
    Exemption("api/organizations/", _MINE, read=lambda organization: "/api/organizations/"),
    Exemption("api/invitations/accept/", _ACCEPT),
)
SEEDS: tuple[Seed, ...] = (
    Seed(create=_no_rows, rows=_organization_row),
    Seed(create=_create_branches, rows=_branch_rows),
)
