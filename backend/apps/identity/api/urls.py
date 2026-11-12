"""Routes of the identity API, under ``/api/`` (``config.urls``), trailing slash (SPEC-00)."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from apps.identity.api.views_me import MeView

app_name = "identity"

urlpatterns: list[URLPattern | URLResolver] = [
    path("me/", MeView.as_view(), name="me"),
]
