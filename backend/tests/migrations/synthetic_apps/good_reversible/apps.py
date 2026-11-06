from __future__ import annotations

from django.apps import AppConfig


class GoodReversibleConfig(AppConfig):
    name = "tests.migrations.synthetic_apps.good_reversible"
    label = "good_reversible"
    default_auto_field = "django.db.models.BigAutoField"
