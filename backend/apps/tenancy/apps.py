"""App config of ``apps.tenancy`` (SPEC-02, design.md §3.2)."""

from __future__ import annotations

from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = "apps.tenancy"
    label = "tenancy"
