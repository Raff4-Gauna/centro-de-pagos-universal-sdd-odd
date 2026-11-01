"""Public URLs, the only ones in prod (``config.settings.prod``).

/healthz and /readyz have no trailing slash (prod's SSL-redirect exemption matches them exactly,
design.md §3.2.2); business modules add their routes here.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from apps.common.health import views as health_views

urlpatterns: list[URLPattern | URLResolver] = [
    path("healthz", health_views.healthz, name="healthz"),
    path("readyz", health_views.readyz, name="readyz"),
]
