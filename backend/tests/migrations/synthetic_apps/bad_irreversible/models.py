"""``Item`` in step with its migrations: only the missing reverses are wrong (AC-PLT-17).

Never give ``0002``-``0004`` a reverse: ``lint_migrations`` reporting the three and
``check_migrations_roundtrip`` failing to revert ``0004`` is what the tests assert.
"""

from __future__ import annotations

from django.db import models


class Item(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self) -> str:
        return self.name
