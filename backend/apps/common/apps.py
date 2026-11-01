"""Platform infrastructure shared by every module (logging, health, API errors). No models in 00."""

from __future__ import annotations

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "apps.common"
    label = "common"
