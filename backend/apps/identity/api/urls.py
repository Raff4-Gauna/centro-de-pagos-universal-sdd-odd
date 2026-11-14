"""Routes of the identity API, under ``/api/`` (``config.urls``), trailing slash (SPEC-00)."""

from __future__ import annotations

from django.db import transaction
from django.urls import URLPattern, URLResolver, path

from apps.identity.api.views_bff import (
    LoginCompleteView,
    LoginStartView,
    LogoutView,
    RefreshView,
)
from apps.identity.api.views_me import MeView

app_name = "identity"

urlpatterns: list[URLPattern | URLResolver] = [
    path("me/", MeView.as_view(), name="me"),
    # Only the BFF (X-Hub-Bff-Credential): for anybody else these routes do not exist.
    path("auth/bff/login/start/", LoginStartView.as_view(), name="bff-login-start"),
    # Never inside a request-wide transaction (ATOMIC_REQUESTS): a refused login keeps its attempt
    # consumed and its audit event (services/login_complete.py); a refused refresh still commits
    # the expiry or the revocation it found (services/refresh.py).
    path(
        "auth/bff/login/complete/",
        transaction.non_atomic_requests(LoginCompleteView.as_view()),
        name="bff-login-complete",
    ),
    path(
        "auth/bff/refresh/",
        transaction.non_atomic_requests(RefreshView.as_view()),
        name="bff-refresh",
    ),
    path("auth/bff/logout/", LogoutView.as_view(), name="bff-logout"),
]
