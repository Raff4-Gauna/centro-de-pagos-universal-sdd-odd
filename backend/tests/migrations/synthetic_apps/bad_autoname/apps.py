from __future__ import annotations

from django.apps import AppConfig


class BadAutonameConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.bad_autoname"
    label = "bad_autoname"
    default_auto_field = "django.db.models.BigAutoField"
