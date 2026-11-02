"""URLs of dev and test: the public ones plus dev-only routes (D-14).

``/api/dev/*`` (T-PLT-17) and the Swagger UI live only here, so they never exist in prod. The error
handlers are the public ones (problem+json under /api/, T-PLT-15).
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver

from config import urls as public_urls

handler404 = public_urls.handler404
handler500 = public_urls.handler500

urlpatterns: list[URLPattern | URLResolver] = [*public_urls.urlpatterns]
