"""AC-PLT-31 synthetic: a model of ``apps.charges`` stores an amount in a ``FloatField`` (C-02).

Stands for ``apps/charges/models.py``. Parsed as AST by test_AC_PLT_31_no_float_money.py, never
imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

from django.db import models


class Charge(models.Model):
    amount = models.FloatField()
    fee = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self) -> str:
        return str(self.fee)
