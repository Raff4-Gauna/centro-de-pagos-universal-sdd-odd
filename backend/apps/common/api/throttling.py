"""Global throttle of the API (design.md §3.2.4, RN-PLT-19, RF-PLT-17, Q-038).

00 only has the mechanism and one generous default for anonymous clients
(``API_THROTTLE_ANON_RATE``, ``300/min`` unless the environment says otherwise); modules 01, 07 and
11 set the limits of login, webhooks and API keys. The history lives in the default cache (Redis,
``KEY_PREFIX="hub"``) under ``throttle_anon_<ident>``; the ident is ``REMOTE_ADDR`` unless
``TRUSTED_PROXY_COUNT`` (DRF's ``NUM_PROXIES``) trusts that many proxies in ``X-Forwarded-For``.

Exceeding it raises DRF's ``Throttled``: ``429 throttled`` problem+json with ``Retry-After``
(``exceptions.py``). DRF reads ``DEFAULT_THROTTLE_RATES`` once, at import; ``get_rate()`` reads the
setting on every request instead, so the value of the running settings is the one that counts.

Fail-open (D-06): if Redis fails, the request goes through and ``throttle.cache_unavailable`` is
logged as a WARNING with the exception *type* only (a driver message can carry the Redis URL with
its password, C-06); ``/readyz`` already reports Redis down. The health views are plain Django
views, so no throttle applies to them (RN-PLT-17).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from redis.exceptions import RedisError
from rest_framework.throttling import AnonRateThrottle

if TYPE_CHECKING:
    # rest_framework.views reads DEFAULT_THROTTLE_CLASSES, i.e. this module, when imported.
    from rest_framework.request import Request
    from rest_framework.views import APIView

logger = logging.getLogger(__name__)

CACHE_UNAVAILABLE_EVENT = "throttle.cache_unavailable"
# What a failing Redis raises through Django's RedisCache (socket errors may arrive unwrapped).
CACHE_ERRORS: tuple[type[Exception], ...] = (RedisError, OSError)


class HubAnonRateThrottle(AnonRateThrottle):
    """``AnonRateThrottle`` with its rate read at runtime and fail-open on cache errors."""

    def get_rate(self) -> str:
        rate: str = settings.API_THROTTLE_ANON_RATE
        return rate

    def allow_request(self, request: Request, view: APIView) -> bool:
        try:
            return super().allow_request(request, view)
        except CACHE_ERRORS as error:
            logger.warning(
                CACHE_UNAVAILABLE_EVENT,
                extra={"scope": self.scope, "error_type": type(error).__name__},
            )
            return True
