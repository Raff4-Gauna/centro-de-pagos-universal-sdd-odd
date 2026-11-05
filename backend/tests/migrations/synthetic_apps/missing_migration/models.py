"""``Widget`` ahead of ``0001_initial``: ``code`` has no migration (AC-PLT-16).

Never add the migration: ``makemigrations --check`` failing on this app is what the test asserts.
"""

from __future__ import annotations

from django.db import models


class Widget(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, default="")

    def __str__(self) -> str:
        return self.name
