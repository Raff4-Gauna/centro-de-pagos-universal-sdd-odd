"""AC-PLT-31 synthetic: the Mercado Pago adapter reads the provider's float amount (allowed).

C-02 lets conversions happen only inside the adapter, which hands a Decimal to the core. Stands
for ``apps/integrations/providers/mercadopago/ok_float.py``. Parsed as AST by
test_AC_PLT_31_no_float_money.py, never imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

from decimal import Decimal


def amount(payload: dict[str, str]) -> Decimal:
    return Decimal(str(float(payload["transaction_amount"])))
