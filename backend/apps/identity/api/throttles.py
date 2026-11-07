"""Throttles of login and refresh (ADR-0004 §9, design.md §7.6, RN-IDA-15, AC-IDA-20, Q-111).

``login_start_ip`` and ``login_complete_ip`` allow 10/min per client IP (each its own quota; the key
holds ``sha256(ip)[:16]``, never the IP) and ``refresh_session`` 30/min per session. The limits are
fixed by the spec, so no environment variable moves them. DRF runs throttles before the view, so an
excess never reaches Google, and answers ``429 throttled`` with ``Retry-After``.

They extend the platform's throttle for its fail-open on Redis errors (D-06, which SPEC-01 does not
change); setting ``rate`` keeps its ``get_rate``, which is the anonymous one, from running.

The refresh key is the ``<sid>`` of ``rt1.<sid>.<secret>``, read without the database and never the
secret. A body with no such token has no session to count against: the throttle does not apply and
the view rejects it (``token_invalid``, design.md §4.5).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING

from apps.common.api.throttling import HubAnonRateThrottle
from apps.identity.api.client_ip import client_ip_for

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

REFRESH_TOKEN_FIELD = "refresh_token"  # noqa: S105 - the name of a body field, not a token
REFRESH_TOKEN_PREFIX = "rt1"  # noqa: S105 - the format marker, not a token
IP_DIGEST_LENGTH = 16


def _session_id(request: Request) -> str | None:
    """The canonical ``<sid>`` of the refresh token in the body, ``None`` if there is none."""
    body = request.data
    token = body.get(REFRESH_TOKEN_FIELD) if isinstance(body, Mapping) else None
    if not isinstance(token, str):
        return None
    prefix, _, rest = token.partition(".")
    sid, separator, _ = rest.partition(".")
    if prefix != REFRESH_TOKEN_PREFIX or not separator:
        return None
    try:
        return str(uuid.UUID(sid))
    except ValueError:
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


class RefreshSessionThrottle(HubAnonRateThrottle):
    scope = "refresh_session"
    rate = "30/min"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        session_id = _session_id(request)
        if session_id is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": session_id}
