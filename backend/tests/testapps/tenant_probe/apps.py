from __future__ import annotations

from django.apps import AppConfig


class TenantProbeConfig(AppConfig):
    name = "tests.testapps.tenant_probe"
    label = "tenant_probe"
