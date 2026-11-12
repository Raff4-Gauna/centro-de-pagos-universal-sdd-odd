"""Public URLs, the only ones in prod (``config.settings.prod``).

/healthz and /readyz have no trailing slash (prod's SSL-redirect exemption matches them exactly,
design.md §3.2.2); business modules add their routes here. Under /api/, a 404 or 500 answered by
Django (an unknown route, a plain view that fails) is problem+json too (T-PLT-15, AC-PLT-34); every
urlconf used as ROOT_URLCONF re-exports these two handlers.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path

from apps.common.health import views as health_views

handler404 = "apps.common.api.exceptions.not_found"
handler500 = "apps.common.api.exceptions.server_error"

urlpatterns: list[URLPattern | URLResolver] = [
    path("healthz", health_views.healthz, name="healthz"),
    path("readyz", health_views.readyz, name="readyz"),
    # SPEC-01: /api/me/ (T-IDA-07); the sessions and auth/bff/* routes join it in the same urlconf.
    path("api/", include("apps.identity.api.urls")),
]
