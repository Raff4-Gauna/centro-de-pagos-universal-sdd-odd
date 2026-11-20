"""Routes of the tenancy API, under ``/api/`` (``config.urls``), trailing slash (SPEC-00)."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import SimpleRouter

from apps.tenancy.api.branches import BranchViewSet
from apps.tenancy.api.invitations import (
    AcceptInvitationView,
    AcceptMyInvitationView,
    MyInvitationsView,
)
from apps.tenancy.api.organizations import CurrentOrganizationViewSet, MyOrganizationsView

app_name = "tenancy"

# Tenant-scoped: the organization of X-Organization-Id (design.md §6).
router = SimpleRouter()
router.register("branches", BranchViewSet, basename="branch")

urlpatterns: list[URLPattern | URLResolver] = [
    # Exempt from the active organization (design.md §3.5): the organizations a user can pick.
    path("organizations/", MyOrganizationsView.as_view(), name="organizations"),
    # Tenant-scoped: the organization of X-Organization-Id (design.md §6).
    path(
        "organizations/current/",
        CurrentOrganizationViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="organization-current",
    ),
    *router.urls,
    # The state of a branch changes only here (RN-TEN-19, AC-TEN-37); see ``api/branches.py``.
    path(
        "branches/<str:id>/deactivate/",
        BranchViewSet.as_view({"post": "deactivate"}),
        name="branch-deactivate",
    ),
    path(
        "branches/<str:id>/reactivate/",
        BranchViewSet.as_view({"post": "reactivate"}),
        name="branch-reactivate",
    ),
    # Exempt (design.md §3.5): the person has no membership in the invitation's organization yet.
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    # Exempt (design.md §3.5, Q-124): the invitations of the person's own email, and accepting one.
    path("invitations/mine/", MyInvitationsView.as_view(), name="invitation-mine"),
    path(
        "invitations/<uuid:invitation_id>/accept/",
        AcceptMyInvitationView.as_view(),
        name="invitation-accept-mine",
    ),
]
