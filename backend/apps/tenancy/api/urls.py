"""Routes of the tenancy API, under ``/api/`` (``config.urls``), trailing slash (SPEC-00)."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from apps.tenancy.api.organizations import CurrentOrganizationViewSet, MyOrganizationsView

app_name = "tenancy"

urlpatterns: list[URLPattern | URLResolver] = [
    # Exempt from the active organization (design.md §3.5): the organizations a user can pick.
    path("organizations/", MyOrganizationsView.as_view(), name="organizations"),
    # Tenant-scoped: the organization of X-Organization-Id (design.md §6).
    path(
        "organizations/current/",
        CurrentOrganizationViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="organization-current",
    ),
]
