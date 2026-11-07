"""Who the person is and how their session lives (SPEC-01): ``users`` and, later, its sessions."""

from __future__ import annotations

from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "apps.identity"
    label = "identity"
