"""What each module declares to the cross-tenant suite (AC-TEN-12, RNF-TEN-01, design.md §9).

Every module that adds routes adds ``tests/cross_tenant/cases/<app>.py`` with any of:

- ``CASES``: one ``CrossTenantCase`` per (route, method) of each ``TenantViewSet`` route. ``path``
  builds the URL that targets the objects of the organization it gets; ``body`` the JSON of a write.
  ``restore`` is for a case whose request changes A even on a step aimed at B (leaving names no
  object, so it always leaves A): it puts A back as the next step needs it. The harness calls it
  before every request, so neither ``path`` nor ``body`` has side effects.
- ``EXEMPT``: one ``Exemption`` per route that runs without an active organization, with its reason
  (``TENANT_EXEMPT_ROUTES`` of design.md §3.5). ``optional`` marks a route mounted only under a
  setting (the fake OIDC provider): it may be absent without the entry being stale. ``read`` is the
  ``GET`` URL of a route scoped to the person: the suite reads it as A's member and checks that
  nothing of B or of B's owner shows up, with or without B in ``X-Organization-Id``. A ``GET`` that
  requires the Hub's login and is exempt must give one (``classifier``).
- ``SEEDS``: the tenant rows of the module, created in both organizations of the suite so a leak of
  the other one's rows or a write on them is visible.

``load()`` imports every module of the package: a new module is picked up without a list to keep.
A route is a ``str`` of the resolver: the ``path()``/``re_path()`` pieces joined, anchors removed.
"""

from __future__ import annotations

import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.tenancy.models import Organization


@dataclass(frozen=True)
class CrossTenantCase:
    route: str
    method: str
    path: Callable[[Organization], str]
    body: Callable[[Organization], Mapping[str, Any]] | None = None
    restore: Callable[[Organization], None] | None = None


@dataclass(frozen=True)
class Exemption:
    route: str
    reason: str
    optional: bool = False
    read: Callable[[Organization], str] | None = None


@dataclass(frozen=True)
class Seed:
    create: Callable[[Organization], None]
    # Every row of that organization; the first value of each row is its id.
    rows: Callable[[Organization], frozenset[tuple[Any, ...]]]


@dataclass(frozen=True)
class Registry:
    cases: tuple[CrossTenantCase, ...] = ()
    exemptions: tuple[Exemption, ...] = ()
    seeds: tuple[Seed, ...] = ()

    def case_for(self, route: str, method: str) -> CrossTenantCase | None:
        found = [case for case in self.cases if (case.route, case.method) == (route, method)]
        return found[0] if found else None


def load() -> Registry:
    from tests.cross_tenant import cases

    cases_found: list[CrossTenantCase] = []
    exemptions: list[Exemption] = []
    seeds: list[Seed] = []
    for info in sorted(pkgutil.iter_modules(cases.__path__), key=lambda item: item.name):
        module = import_module(f"{cases.__name__}.{info.name}")
        cases_found.extend(getattr(module, "CASES", ()))
        exemptions.extend(getattr(module, "EXEMPT", ()))
        seeds.extend(getattr(module, "SEEDS", ()))
    return Registry(tuple(cases_found), tuple(exemptions), tuple(seeds))
