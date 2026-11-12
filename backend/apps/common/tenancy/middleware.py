"""``TenantContextMiddleware``: every request starts and ends without a tenant (design.md §3.1).

It resolves nothing: the organization is resolved by a DRF permission, which needs the user DRF
authenticated (ADR-0001, design.md §3.5). It only clears the tenant and the ``organization_id`` log
key before the view and again in ``finally``, so the tenant the permission activated
(``activate_tenant``) never reaches the next request served by the same thread. Second in
``MIDDLEWARE``, right after ``RequestIdMiddleware`` and before the access log, so the
``http.request`` event still carries the ``organization_id`` of the request.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase

from apps.common.tenancy.current import clear_tenant


class TenantContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        clear_tenant()
        try:
            return self.get_response(request)
        finally:
            clear_tenant()
