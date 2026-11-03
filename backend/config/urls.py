"""Public URLs, the only ones in prod (``config.settings.prod``).

/healthz and /readyz arrive with T-PLT-11; business modules add their routes here.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = []
