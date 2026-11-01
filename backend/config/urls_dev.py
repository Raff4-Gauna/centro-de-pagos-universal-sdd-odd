"""URLs of dev and test: the public ones plus dev-only routes (D-14).

``/api/dev/*`` (T-PLT-17) and the Swagger UI live only here, so they never exist in prod.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver

from config.urls import urlpatterns as public_urlpatterns

urlpatterns: list[URLPattern | URLResolver] = [*public_urlpatterns]
