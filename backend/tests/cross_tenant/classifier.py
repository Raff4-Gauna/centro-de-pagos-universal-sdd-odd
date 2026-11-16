"""Walk every registered URL and classify it (AC-TEN-12, RNF-TEN-01, design.md §9).

``walk`` reads the resolver of a URLconf, not a hand-kept list: a route added anywhere shows up.
``classify`` sorts each one:

- **tenant-scoped**: its view is a ``TenantViewSet``. Every method it maps needs a
  ``CrossTenantCase``, and the view must keep the guard of ``TenantViewSet`` intact
  (``guard_errors``).
- **exempt**: listed in some ``EXEMPT`` with a reason (design.md §3.5). If it is a ``GET`` behind
  the Hub's login (``IsAuthenticated``), the entry must give ``read``: the harness proves on it
  that the route is scoped to the person (``harness.check_exempt``).
- anything else (a DRF view, a plain Django view, a view that calls itself tenant-scoped without
  being a ``TenantViewSet``) fails as unclassified.

``guard_errors`` is the static half of the net for what ``TenantViewSet.__init_subclass__`` cannot
see (T-TEN-08): ``as_view()`` initkwargs that replace a method or an attribute of the guard, a
guard method reassigned on the class after import, and a ``dispatch``/``initial`` of its own that
could skip ``check_permissions``. The behavioral half is ``harness.check_endpoint``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver

from apps.identity.api.authentication import IsAuthenticated
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.api.permissions import ActionPermission, ResolveTenant
from tests.cross_tenant.registry import Exemption, Registry

# What DRF's routers pass to ``ViewSet.as_view()``; anything else in initkwargs fails.
ROUTER_INITKWARGS = frozenset({"basename", "detail", "suffix", "name", "description"})
# The methods that decide whether the permissions run. A ``TenantViewSet`` keeps the base's own.
GUARDED_METHODS = ("dispatch", "initial", "check_permissions", "get_permissions")
# DRF adds HEAD to a route that maps GET on its first request: it is checked with GET.
DERIVED_METHODS = frozenset({"head"})


@dataclass(frozen=True)
class Route:
    route: str
    callback: Callable[..., Any]

    @property
    def view_class(self) -> type[Any] | None:
        cls = getattr(self.callback, "cls", None)
        return cls if isinstance(cls, type) else None

    @property
    def initkwargs(self) -> Mapping[str, Any]:
        return getattr(self.callback, "initkwargs", None) or {}

    @property
    def actions(self) -> Mapping[str, str]:
        return getattr(self.callback, "actions", None) or {}

    @property
    def label(self) -> str:
        cls = self.view_class
        view = cls if cls is not None else self.callback
        return f"{self.route} ({view.__module__}.{view.__qualname__})"


@dataclass(frozen=True)
class Endpoint:
    route: str
    method: str
    action: str
    view_class: type[TenantViewSet]

    @property
    def label(self) -> str:
        return f"{self.method} {self.route}"


def _clean(piece: str) -> str:
    return piece.removeprefix("^").removesuffix("$")


def _walk(patterns: Iterable[URLPattern | URLResolver], prefix: str) -> Iterator[Route]:
    for pattern in patterns:
        route = prefix + _clean(str(pattern.pattern))
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns, route)
        else:
            yield Route(route, pattern.callback)


def walk(urlconf: str) -> list[Route]:
    return list(_walk(get_resolver(urlconf).url_patterns, ""))


def is_tenant_route(route: Route) -> bool:
    cls = route.view_class
    return cls is not None and issubclass(cls, TenantViewSet)


def endpoints_of(route: Route) -> list[Endpoint]:
    cls = route.view_class
    if cls is None or not issubclass(cls, TenantViewSet):
        return []
    return [
        Endpoint(route.route, method.upper(), action, cls)
        for method, action in sorted(route.actions.items())
        if method not in DERIVED_METHODS
    ]


def tenant_endpoints(routes: Iterable[Route]) -> list[Endpoint]:
    return [endpoint for route in routes for endpoint in endpoints_of(route)]


def _permission_order_ok(permission_classes: Sequence[Any]) -> bool:
    classes = list(permission_classes)
    if ResolveTenant not in classes or ActionPermission not in classes:
        return False
    return classes.index(ResolveTenant) < classes.index(ActionPermission)


def guard_errors(route: Route) -> list[str]:
    cls = route.view_class
    assert cls is not None
    assert issubclass(cls, TenantViewSet)
    errors = [
        f"{route.label}: as_view() initkwarg {name!r} can replace the tenant guard"
        for name in sorted(set(route.initkwargs) - ROUTER_INITKWARGS)
    ]
    errors.extend(
        f"{route.label}: {name} is not TenantViewSet's (overridden or reassigned)"
        for name in GUARDED_METHODS
        if getattr(cls, name) is not getattr(TenantViewSet, name)
    )
    if not _permission_order_ok(cls.permission_classes):
        errors.append(f"{route.label}: permission_classes lost ResolveTenant → ActionPermission")
    if not route.actions:
        errors.append(f"{route.label}: no method is mapped to an action")
    return errors


def reads_as_a_user(route: Route) -> bool:
    """A ``GET`` that only a logged-in person reaches: what it lists must be that person's."""
    cls = route.view_class
    # An APIView has its ``get``; a ViewSet maps it at ``as_view()`` (``route.actions``).
    if cls is None or not (callable(getattr(cls, "get", None)) or "get" in route.actions):
        return False
    classes = getattr(cls, "permission_classes", ())
    return any(isinstance(c, type) and issubclass(c, IsAuthenticated) for c in classes)


def exempt_reads(routes: Iterable[Route], registry: Registry) -> list[Exemption]:
    """The exemptions whose route is registered and that give a ``read`` URL."""
    present = {route.route for route in routes}
    return [e for e in registry.exemptions if e.read is not None and e.route in present]


def _claims_tenant(route: Route) -> bool:
    return bool(getattr(route.view_class, "tenant_scoped", False))


def _registry_errors(registry: Registry) -> list[str]:
    keys = Counter((case.route, case.method) for case in registry.cases)
    errors = [
        f"{method} {route}: more than one CrossTenantCase"
        for (route, method), n in keys.items()
        if n > 1
    ]
    routes = Counter(exemption.route for exemption in registry.exemptions)
    errors.extend(f"{route}: exempt more than once" for route, n in routes.items() if n > 1)
    errors.extend(
        f"{exemption.route}: exempt without a reason"
        for exemption in registry.exemptions
        if not exemption.reason.strip()
    )
    return errors


def classify(routes: Sequence[Route], registry: Registry) -> list[str]:
    """Every problem of ``routes`` against ``registry``; empty when all is classified."""
    errors = _registry_errors(registry)
    exempt = {exemption.route: exemption for exemption in registry.exemptions}
    case_keys = {(case.route, case.method) for case in registry.cases}
    needed: set[tuple[str, str]] = set()
    for route in routes:
        if is_tenant_route(route):
            if route.route in exempt:
                errors.append(f"{route.label}: a TenantViewSet cannot be exempt")
            errors.extend(guard_errors(route))
            for endpoint in endpoints_of(route):
                needed.add((endpoint.route, endpoint.method))
                if (endpoint.route, endpoint.method) not in case_keys:
                    errors.append(
                        f"{endpoint.label}: tenant-scoped route without a CrossTenantCase"
                    )
        elif _claims_tenant(route):
            errors.append(f"{route.label}: tenant_scoped without being a TenantViewSet")
        elif route.route not in exempt:
            errors.append(f"{route.label}: unclassified: neither a TenantViewSet nor exempt")
        elif reads_as_a_user(route) and exempt[route.route].read is None:
            errors.append(f"{route.label}: exempt GET behind the login without a read URL")
    present = {route.route for route in routes}
    errors.extend(
        f"{exemption.route}: exempt but no such route (stale entry)"
        for exemption in registry.exemptions
        if exemption.route not in present and not exemption.optional
    )
    errors.extend(
        f"{method} {route}: CrossTenantCase without a tenant-scoped route (stale entry)"
        for route, method in sorted(case_keys - needed)
    )
    return errors
