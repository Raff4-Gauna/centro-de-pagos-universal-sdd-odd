"""``Part`` in step with its migrations, each of them reversible (AC-PLT-17).

``0004_part_code_index`` adds a database index through ``RunSQL`` only (no model state), so it
does not appear here and ``makemigrations --check`` stays clean.
"""

from __future__ import annotations

from django.db import models


class Part(models.Model):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, default="")

    def __str__(self) -> str:
        return self.name
