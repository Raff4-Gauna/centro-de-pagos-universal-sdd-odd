from __future__ import annotations

from django.apps import AppConfig


class MissingMigrationConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.missing_migration"
    label = "missing_migration"
    default_auto_field = "django.db.models.BigAutoField"
