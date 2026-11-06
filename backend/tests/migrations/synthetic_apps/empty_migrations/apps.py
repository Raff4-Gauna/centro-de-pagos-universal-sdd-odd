from __future__ import annotations

from django.apps import AppConfig


class EmptyMigrationsConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.empty_migrations"
    label = "empty_migrations"
    default_auto_field = "django.db.models.BigAutoField"
