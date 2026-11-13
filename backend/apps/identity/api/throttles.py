"""Throttles of login and refresh (ADR-0004 §9, design.md §7.6, RN-IDA-15, AC-IDA-20, Q-111).

``login_start_ip`` and ``login_complete_ip`` allow 10/min per client IP (each its own quota; the key
holds ``sha256(ip)[:16]``, never the IP) and ``refresh_session`` 30/min per session. The spec fixes
those, so no environment variable moves them. DRF runs throttles before the view, so an
excess never reaches Google; ``BffAPIView`` answers it ``429 rate_limited`` with ``Retry-After``.

``refresh_ip`` is the refresh's second quota, per client IP (planner's decision in T-IDA-14): a
``sid`` with a valid shape is easy to make up, and each new one would start a fresh 30/min, so the
session quota alone puts no ceiling on one client. Its rate is ``IDENTITY_REFRESH_IP_RATE``
(``60/min`` unless the settings say otherwise), read on every request like the platform's; generous
so that a browser with many tabs, or a few people behind one NAT, never meets it.

They extend the platform's throttle for its fail-open on Redis errors (D-06, which SPEC-01 does not
change); setting ``rate`` keeps its ``get_rate``, which is the anonymous one, from running.

The refresh key is the ``<sid>`` of ``rt1.<sid>.<secret>``, parsed by ``domain/secrets_format.py``
(the one reading of the format) without the database and never the secret. A body with no such
token has no session to count against: that throttle does not apply and the view rejects it
(``token_invalid``, design.md §4.5); the IP quota still counts it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

from django.conf import settings

from apps.common.api.throttling import HubAnonRateThrottle
from apps.identity.api.client_ip import client_ip_for
from apps.identity.domain.errors import MalformedRefreshTokenError
from apps.identity.domain.secrets_format import parse_refresh_token

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

REFRESH_TOKEN_FIELD = "refresh_token"  # noqa: S105 - the name of a body field, not a token
IP_DIGEST_LENGTH = 16


def _session_id(request: Request) -> str | None:
    """The canonical ``<sid>`` of the refresh token in the body, ``None`` if there is none."""
    body = request.data
    token = body.get(REFRESH_TOKEN_FIELD) if isinstance(body, Mapping) else None
    if not isinstance(token, str):
        return None
    try:
        return str(parse_refresh_token(token))
    except MalformedRefreshTokenError:
        return None


class _ClientIpThrottle(HubAnonRateThrottle):
    rate = "10/min"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        digest = hashlib.sha256(client_ip_for(request).encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest[:IP_DIGEST_LENGTH]}


class LoginStartIpThrottle(_ClientIpThrottle):
    scope = "login_start_ip"


class LoginCompleteIpThrottle(_ClientIpThrottle):
    scope = "login_complete_ip"


class RefreshIpThrottle(_ClientIpThrottle):
    scope = "refresh_ip"

    def __init__(self) -> None:
        # Read per request, as the platform's: a test or a settings change needs no re-import.
        self.rate = settings.IDENTITY_REFRESH_IP_RATE
        super().__init__()


class RefreshSessionThrottle(HubAnonRateThrottle):
    scope = "refresh_session"
    rate = "30/min"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        session_id = _session_id(request)
        if session_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": session_id}
