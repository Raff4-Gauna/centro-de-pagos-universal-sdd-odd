"""Credential of the BFF (ADR-0004 §9, design.md §6.1, §7.5, RN-IDA-12).

The endpoints that hand out tokens (``auth/bff/*``) only answer the BFF, which sends
``X-Hub-Bff-Credential``; the catch-all proxy of the frontend never does. Their views extend
``BffAPIView``, which raises Django's ``Http404`` before DRF takes the request: any other caller
gets the very response of a route that does not exist (same handler, same bytes, no ``Allow``), so
nothing tells it the endpoint is there. ``IsBffCaller`` stays as the view's permission, a second
check; on a view of its own it still refuses with ``404``, but rendered by DRF (with ``Allow``).
``BffAPIView`` also authenticates nobody by ``Authorization`` (the BFF is the caller, not a user)
and answers an exceeded throttle with ``429 rate_limited`` (design.md §6.1, the ``/login?error=``
allowlist of §6.3), not the platform's ``throttled``.

``settings.IDENTITY_BFF_CREDENTIALS`` holds the current one and, during a rotation, the previous one
(``SecretStr``: masked wherever settings get rendered). Empty, the setting refuses every caller.
Each comparison is constant-time and all of them run, whichever matches. They compare bytes:
``hmac.compare_digest`` raises ``TypeError`` on non-ASCII ``str``, which a client could send.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, Any, NoReturn

from django.conf import settings
from django.http import Http404, HttpRequest
from rest_framework.exceptions import NotFound, Throttled
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

if TYPE_CHECKING:
    from django.http import HttpResponseBase
    from rest_framework.request import Request

BFF_CREDENTIAL_HEADER = "X-Hub-Bff-Credential"


def has_bff_credential(request: HttpRequest | Request) -> bool:
    """Whether the request carries a valid credential. Holds no state: each caller asks anew."""
    presented = request.headers.get(BFF_CREDENTIAL_HEADER, "").encode()
    matches = [
        hmac.compare_digest(presented, credential.get_secret_value().encode())
        for credential in settings.IDENTITY_BFF_CREDENTIALS
    ]
    return any(matches)


class RateLimited(Throttled):
    default_code = "rate_limited"


class IsBffCaller(BasePermission):
    """DRF checks permissions before throttles: a rejected caller spends nobody's quota."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not has_bff_credential(request):
            raise NotFound
        return True


class BffAPIView(APIView):
    """Base of every ``auth/bff/*`` view; each one still declares its ``throttle_classes``."""

    authentication_classes = ()
    permission_classes = (IsBffCaller,)

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # Raised to Django, not to DRF: DRF would render it and add Allow (finalize_response).
        if not has_bff_credential(request):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def throttled(self, request: Request, wait: float) -> NoReturn:
        raise RateLimited(wait)
