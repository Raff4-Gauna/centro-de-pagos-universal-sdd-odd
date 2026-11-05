"""``Gadget`` in step with its migrations: only the name of ``0002`` is wrong (AC-PLT-18).

Never rename ``0002_auto_20261105_1200``: ``lint_migrations`` failing on it is what the test
asserts.
"""

from __future__ import annotations

from django.db import models


class Gadget(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, default="")

    def __str__(self) -> str:
        return self.name
