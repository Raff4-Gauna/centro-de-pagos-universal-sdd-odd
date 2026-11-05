from __future__ import annotations

from django.apps import AppConfig


class BadMixedConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.bad_mixed"
    label = "bad_mixed"
    default_auto_field = "django.db.models.BigAutoField"
