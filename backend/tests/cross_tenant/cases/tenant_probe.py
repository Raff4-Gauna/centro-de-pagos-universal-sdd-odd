"""``tenant_probe``'s routes: a ``Widget`` CRUD on ``TenantViewSet`` (design.md §9).

There are no business routes yet (T-TEN-12 and later add them), so this is the route that proves
the suite end to end on real rows: list, create, retrieve, partial update and delete, each with its
``ActionSpec`` (the ``branch.*`` ones of the matrix: a ``READ`` for every role, ``WRITE`` for
owner/admin). ``tests/cross_tenant/urls.py`` mounts ``router`` next to the real URLconf.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.common.tenancy.current import tenant_scope
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Organization
from tests.cross_tenant.registry import CrossTenantCase, Seed
from tests.tenancy.api.probe import platform_ctx
from tests.testapps.tenant_probe.models import Widget

PREFIX = "api/probe/widgets"
LIST = f"{PREFIX}/"
DETAIL = f"{PREFIX}/(?P<pk>[0-9a-f-]{{36}})/"


def _as_json(widget: Widget) -> dict[str, str]:
    return {"id": str(widget.pk), "name": widget.name}


class WidgetViewSet(TenantViewSet):
    lookup_value_regex = "[0-9a-f-]{36}"
    action_specs = {  # noqa: RUF012 - read once by TenantViewSet.__init_subclass__
        "list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "retrieve": TENANCY_ACTIONS[TenancyAction.BRANCH_READ],
        "create": TENANCY_ACTIONS[TenancyAction.BRANCH_CREATE],
        "partial_update": TENANCY_ACTIONS[TenancyAction.BRANCH_UPDATE],
        "destroy": TENANCY_ACTIONS[TenancyAction.BRANCH_DEACTIVATE],
    }

    def _widget(self, pk: str) -> Widget:
        return get_object_or_404(Widget.objects.for_tenant(self.tenant), pk=pk)

    def list(self, request: Request) -> Response:
        widgets = Widget.objects.for_tenant(self.tenant).order_by("name")
        return Response([_as_json(widget) for widget in widgets])

    def create(self, request: Request) -> Response:
        widget = Widget.objects.for_tenant(self.tenant).create(name=str(request.data["name"]))
        return Response(_as_json(widget), status=201)

    def retrieve(self, request: Request, pk: str) -> Response:
        return Response(_as_json(self._widget(pk)))

    def partial_update(self, request: Request, pk: str) -> Response:
        widget = self._widget(pk)
        widget.name = str(request.data["name"])
        widget.save(update_fields=["name"])
        return Response(_as_json(widget))

    def destroy(self, request: Request, pk: str) -> Response:
        self._widget(pk).delete()
        return Response(status=204)


router = SimpleRouter()
router.register(PREFIX, WidgetViewSet, basename="probe-widget")


def _create(organization: Organization) -> None:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        for n in (1, 2):
            Widget.objects.for_tenant(ctx).create(name=f"{organization.name}-{n}")


def _rows(organization: Organization) -> frozenset[tuple[Any, ...]]:
    ctx = platform_ctx(organization)
    with tenant_scope(ctx):
        return frozenset(Widget.objects.for_tenant(ctx).values_list("id", "name"))


def _first(organization: Organization) -> str:
    ids = sorted(str(row[0]) for row in _rows(organization))
    return f"/{PREFIX}/{ids[0]}/"


def _list(organization: Organization) -> str:
    return f"/{LIST}"


def _renamed(organization: Organization) -> dict[str, str]:
    return {"name": f"renamed-in-{organization.name}"}


SEEDS = (Seed(create=_create, rows=_rows),)

CASES = (
    CrossTenantCase(LIST, "GET", _list),
    CrossTenantCase(LIST, "POST", _list, body=_renamed),
    CrossTenantCase(DETAIL, "GET", _first),
    CrossTenantCase(DETAIL, "PATCH", _first, body=_renamed),
    CrossTenantCase(DETAIL, "DELETE", _first),
)
