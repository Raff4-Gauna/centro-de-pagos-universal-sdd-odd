"""App config of ``apps.integrations`` (SPEC-04, design.md §3.1)."""

from __future__ import annotations

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    label = "integrations"
