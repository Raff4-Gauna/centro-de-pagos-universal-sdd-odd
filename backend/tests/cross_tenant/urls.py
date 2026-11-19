"""The URLconf the suite walks: the test ROOT_URLCONF plus ``tenant_probe``'s routes.

``BASE_URLCONF`` is ``config.settings.test``'s ``ROOT_URLCONF`` (a test checks it), named here
rather than read from the settings: under ``pytest.mark.urls`` the setting is this very module.
It includes ``config.urls``, the one of prod, so every real route is walked.
"""

from __future__ import annotations

from importlib import import_module

from django.urls import URLPattern, URLResolver

from tests.cross_tenant.cases import tenant_probe

BASE_URLCONF = "config.urls_dev"
SUITE_URLCONF = __name__

_base = import_module(BASE_URLCONF)
handler404 = _base.handler404
handler500 = _base.handler500

urlpatterns: list[URLPattern | URLResolver] = [*_base.urlpatterns, *tenant_probe.router.urls]
