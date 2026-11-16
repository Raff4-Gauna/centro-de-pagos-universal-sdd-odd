"""A URLconf of broken endpoints: proof that the walker and the harness catch them (AC-TEN-12).

Real routes are few yet, so the net is tested here. ``GoodViewSet`` is the control: it must pass
everything. The rest get past ``TenantViewSet.__init_subclass__`` and its runtime re-check
(T-TEN-08) and still reach their handler without a tenant:

- ``initkwargs``: ``as_view(get_permissions=...)`` puts an instance attribute over the method;
- ``reassigned``: ``check_permissions`` replaced on the class after it was created;
- ``initial`` and ``dispatch``: their own versions that never call ``check_permissions``;
- ``uncased``: a correct ``TenantViewSet`` nobody wrote a ``CrossTenantCase`` for;
- ``plain-drf`` and ``plain-django``: views that are not tenant-aware and are not exempt;
- ``mine`` and ``everyone``: exempt ``GET`` routes of the person; ``everyone`` lists every
  organization, which ``harness.check_exempt`` must catch.

Each handler answers ``200`` with nothing of the tenant: a bypass shows up as that ``200``.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, path
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.tenancy.querysets import UnscopedReason
from apps.tenancy.api.base import TenantViewSet
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.models import Organization
from tests.cross_tenant.registry import CrossTenantCase, Exemption, Registry

READ = {"list": TENANCY_ACTIONS[TenancyAction.BRANCH_READ]}


def _list() -> dict[str, Any]:
    """A fresh map per route: DRF adds ``head`` to it on the first request."""
    return {"get": "list"}


class GoodViewSet(TenantViewSet):
    action_specs = READ

    def list(self, request: Request) -> Response:
        return Response({"organization_id": str(self.tenant.organization_id)})


class LeakyViewSet(TenantViewSet):
    action_specs = READ

    def list(self, request: Request) -> Response:
        return Response({"reached": "the handler"})


class ReassignedViewSet(LeakyViewSet):
    pass


def _no_check(self: Any, request: Request) -> None:
    return None


ReassignedViewSet.check_permissions = _no_check  # type: ignore[method-assign]


class OwnInitialViewSet(LeakyViewSet):
    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        self.format_kwarg = self.get_format_suffix(**kwargs)
        request.accepted_renderer, request.accepted_media_type = self.perform_content_negotiation(
            request
        )
        self.perform_authentication(request)  # and no check_permissions


class OwnDispatchViewSet(LeakyViewSet):
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        self.args, self.kwargs = args, kwargs
        self.format_kwarg = self.get_format_suffix(**kwargs)
        drf_request = self.initialize_request(request, *args, **kwargs)
        self.request = drf_request
        self.headers = self.default_response_headers
        drf_request.accepted_renderer, drf_request.accepted_media_type = (
            self.perform_content_negotiation(drf_request)
        )
        response = self.list(drf_request)
        self.response = self.finalize_response(drf_request, response, *args, **kwargs)
        return self.response


class UncasedViewSet(GoodViewSet):
    pass


class PlainDrfView(APIView):
    def get(self, request: Request) -> Response:
        return Response({"reached": "the handler"})


class MineView(APIView):
    def get(self, request: Request) -> Response:
        return Response({"user_id": str(request.user.pk)})


class EveryoneView(APIView):
    def get(self, request: Request) -> Response:
        everyone = Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND)
        return Response([str(pk) for pk in everyone.values_list("id", flat=True)])


def plain_django(request: HttpRequest) -> HttpResponse:
    return HttpResponse("reached the handler")


def _no_permissions() -> list[Any]:
    return []


GOOD = "synthetic/good/"
INITKWARGS = "synthetic/initkwargs/"
REASSIGNED = "synthetic/reassigned/"
INITIAL = "synthetic/initial/"
DISPATCH = "synthetic/dispatch/"
UNCASED = "synthetic/uncased/"
PLAIN_DRF = "synthetic/plain-drf/"
PLAIN_DJANGO = "synthetic/plain-django/"
MINE = "synthetic/mine/"
EVERYONE = "synthetic/everyone/"
BYPASSES = (INITKWARGS, REASSIGNED, INITIAL, DISPATCH)

urlpatterns: list[URLPattern] = [
    path(GOOD, GoodViewSet.as_view(_list())),
    path(INITKWARGS, LeakyViewSet.as_view(_list(), get_permissions=_no_permissions)),
    path(REASSIGNED, ReassignedViewSet.as_view(_list())),
    path(INITIAL, OwnInitialViewSet.as_view(_list())),
    path(DISPATCH, OwnDispatchViewSet.as_view(_list())),
    path(UNCASED, UncasedViewSet.as_view(_list())),
    path(PLAIN_DRF, PlainDrfView.as_view()),
    path(PLAIN_DJANGO, plain_django),
    path(MINE, MineView.as_view()),
    path(EVERYONE, EveryoneView.as_view()),
]


def _path_of(route: str) -> Any:
    def build(organization: Organization) -> str:
        return f"/{route}"

    return build


# Every tenant route but ``UNCASED`` has its case: what fails is the view, not a missing entry.
REGISTRY = Registry(
    cases=tuple(CrossTenantCase(route, "GET", _path_of(route)) for route in (GOOD, *BYPASSES)),
    exemptions=tuple(
        Exemption(route, "de la persona", read=_path_of(route)) for route in (MINE, EVERYONE)
    ),
)
