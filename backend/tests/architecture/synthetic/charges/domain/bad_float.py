"""AC-PLT-31 synthetic: the domain of ``apps.charges`` turns an amount into a float (C-02).

Stands for ``apps/charges/domain/bad_float.py``. Parsed as AST by test_AC_PLT_31_no_float_money.py,
never imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

from decimal import Decimal


def total(amount: Decimal) -> object:
    return float(amount)
