"""Platform infrastructure shared by every module (logging, health, API errors). No models in 00."""

from __future__ import annotations

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "apps.common"
    label = "common"

    def ready(self) -> None:
        # Connects the Celery handlers (request_id header, task log) in every process: the web
        # publishes, the worker runs (T-PLT-17).
        from apps.common import celery_signals  # noqa: F401
