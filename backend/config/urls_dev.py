"""URLs of dev and test: the public ones plus dev-only routes (D-14).

``/api/dev/*`` and the Swagger UI live only here, so they never exist in prod (Q-056,
``test_Q056_dev_routes_absent_in_prod``). The error handlers are the public ones (problem+json under
/api/, T-PLT-15). The schema served here is the public contract (``SERVE_URLCONF``), never these
dev routes (ADR-0005).
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.api.dev_views import DiagnosticTaskView
from config import urls as public_urls

handler404 = public_urls.handler404
handler500 = public_urls.handler500

urlpatterns: list[URLPattern | URLResolver] = [
    *public_urls.urlpatterns,
    # T-PLT-17, AC-PLT-11: enqueues the diagnostic task.
    path("api/dev/diagnostic-task/", DiagnosticTaskView.as_view(), name="dev-diagnostic-task"),
    # T-PLT-18, ADR-0005: the OpenAPI YAML and its Swagger UI.
    path("api/dev/schema/", SpectacularAPIView.as_view(), name="dev-schema"),
    path("api/dev/docs/", SpectacularSwaggerView.as_view(url_name="dev-schema"), name="dev-docs"),
]
