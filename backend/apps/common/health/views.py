"""/healthz and /readyz (design.md §3.2.5, RN-PLT-17, AC-PLT-02).

Plain Django views (no DRF): no authentication, no throttling, no content negotiation. Fixed,
minimal bodies; only /healthz shows the version, as the short SHA (Q-039). ``no-store`` so no
proxy answers a probe from a cached state.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe

from apps.common.health.checks import failed_checks

SHORT_SHA_LENGTH = 7


def _no_store(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness: the process answers. Touches no database, cache or broker."""
    version = str(settings.APP_VERSION)[:SHORT_SHA_LENGTH]
    return _no_store(JsonResponse({"status": "ok", "version": version}))


@require_safe
def readyz(request: HttpRequest) -> JsonResponse:
    """Readiness: PostgreSQL and Redis answer. The cause of a 503 is only in the log."""
    if failed_checks():
        return _no_store(JsonResponse({"status": "unavailable"}, status=503))
    return _no_store(JsonResponse({"status": "ready"}))
