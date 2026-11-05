"""``Gizmo`` in step with its migrations: only the mixing in ``0002`` is wrong (AC-PLT-18).

Never split ``0002_add_slug_and_backfill``: ``lint_migrations`` failing on it is what the test
asserts; ``0003_backfill_slugs`` (``RunPython`` alone) must keep passing.
"""

from __future__ import annotations

from django.db import models


class Gizmo(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(default="")

    def __str__(self) -> str:
        return self.name
