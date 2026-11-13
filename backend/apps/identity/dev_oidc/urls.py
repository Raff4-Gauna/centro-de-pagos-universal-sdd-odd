"""Routes of the fake OIDC provider (Q-122): only ``config.urls_dev`` includes them, and only with
``IDENTITY_OIDC_PROVIDER=fake``. Never in ``config.urls``, the URLconf of prod."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from apps.identity.dev_oidc import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("dev-oidc/authorize", views.authorize, name="dev-oidc-authorize"),
    path("dev-oidc/token", views.token, name="dev-oidc-token"),
    path("dev-oidc/jwks", views.jwks, name="dev-oidc-jwks"),
]
