"""SPEC-02's routes (``apps/tenancy/api/``).

Every ``TenantViewSet`` route of the module registers one ``CrossTenantCase`` per method here, in
the PR that adds it (DoD, ``tasks.md``). A route that runs without an active organization
(``GET /api/organizations/``, accepting an invitation, design.md §3.5) goes to ``EXEMPT`` with its
reason; a ``GET`` behind the login also gives ``read``, the URL the suite reads as A's member to
check it is scoped to the person. Until a route exists, its entry would be stale: the walker fails
on both. The first one is ``GET /api/organizations/`` (T-TEN-12).
"""

from __future__ import annotations

from tests.cross_tenant.registry import CrossTenantCase, Exemption, Seed

_MINE = (
    "ruta de alcance de usuario: las organizaciones de la persona, exenta de la organización activa"
    " (design.md §3.5)"
)

CASES: tuple[CrossTenantCase, ...] = ()
EXEMPT: tuple[Exemption, ...] = (
    Exemption("api/organizations/", _MINE, read=lambda organization: "/api/organizations/"),
)
SEEDS: tuple[Seed, ...] = ()
