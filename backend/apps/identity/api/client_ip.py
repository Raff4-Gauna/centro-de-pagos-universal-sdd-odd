"""IP of the client behind the BFF (ADR-0004 §9, design.md §7.6, RN-IDA-15, AC-IDA-37).

Every browser reaches Django through the BFF, so ``REMOTE_ADDR`` alone would make them all share
one quota. The BFF works out the real IP and reports it in ``X-Hub-Client-IP``, which counts only
with a valid credential; anybody else gets ``REMOTE_ADDR``, so forging the header buys nothing.

``X-Forwarded-For`` is never read, not even through DRF's ``get_ident`` with
``TRUSTED_PROXY_COUNT``: the BFF is the only one that interprets it (``HUB_TRUSTED_PROXY_HOPS``).

The IP is canonicalised so one address has one spelling, hence one quota (``::ffff:203.0.113.7``,
upper-case IPv6). A value that is not an IP is a bug of the BFF: it falls back to ``REMOTE_ADDR``,
the shared quota, and logs the event without the value, which came from a header.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

from apps.common.logging import get_logger
from apps.identity.api.bff_auth import has_bff_credential

if TYPE_CHECKING:
    from rest_framework.request import Request

CLIENT_IP_HEADER = "X-Hub-Client-IP"
INVALID_CLIENT_IP_EVENT = "identity.client_ip_invalid"

logger = get_logger(__name__)


def _canonical(raw: str) -> str | None:
    """The address in its one spelling, or ``None`` if ``raw`` is not an IP."""
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return None
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    return str(mapped or address)


def client_ip_for(request: Request) -> str:
    """``X-Hub-Client-IP`` if a valid credential comes with it; otherwise ``REMOTE_ADDR``."""
    reported = request.headers.get(CLIENT_IP_HEADER)
    if reported is not None and has_bff_credential(request):
        canonical = _canonical(reported)
        if canonical is not None:
            return canonical
        logger.warning(INVALID_CLIENT_IP_EVENT)
    remote_addr: str = request.META.get("REMOTE_ADDR", "")
    return _canonical(remote_addr) or remote_addr
