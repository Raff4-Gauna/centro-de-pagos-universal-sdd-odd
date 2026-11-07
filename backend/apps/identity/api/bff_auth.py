"""Credential of the BFF (ADR-0004 §9, design.md §6.1, §7.5, RN-IDA-12).

The endpoints that hand out tokens (``auth/bff/*``) only answer the BFF, which sends
``X-Hub-Bff-Credential``; the catch-all proxy of the frontend never does. Any other caller gets the
``404 not_found`` of a route that does not exist, so nothing tells it the endpoint is there.

``settings.IDENTITY_BFF_CREDENTIALS`` holds the current one and, during a rotation, the previous one
(``SecretStr``: masked wherever settings get rendered). Empty, the setting refuses every caller.
Each comparison is constant-time and all of them run, whichever matches. They compare bytes:
``hmac.compare_digest`` raises ``TypeError`` on non-ASCII ``str``, which a client could send.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from django.conf import settings
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

BFF_CREDENTIAL_HEADER = "X-Hub-Bff-Credential"


def has_bff_credential(request: Request) -> bool:
    """Whether the request carries a valid credential. Holds no state: each caller asks anew."""
    presented = request.headers.get(BFF_CREDENTIAL_HEADER, "").encode()
    matches = [
        hmac.compare_digest(presented, credential.get_secret_value().encode())
        for credential in settings.IDENTITY_BFF_CREDENTIALS
    ]
    return any(matches)


class IsBffCaller(BasePermission):
    """DRF checks permissions before throttles: a rejected caller spends nobody's quota."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not has_bff_credential(request):
            raise NotFound
        return True
