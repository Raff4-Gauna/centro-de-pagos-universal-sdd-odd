from __future__ import annotations

from django.apps import AppConfig


class BadIrreversibleConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.bad_irreversible"
    label = "bad_irreversible"
    default_auto_field = "django.db.models.BigAutoField"
