"""AC-PLT-14 synthetic: the Clover adapter imports the Mercado Pago one (C-09, cross-provider).

Stands for ``apps/integrations/providers/clover/bad_cross_provider.py``. Parsed as AST by
test_AC_PLT_14_adapter_boundary.py, never imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

from apps.integrations.providers.mercadopago.client import Client  # noqa: F401

from .. import mercadopago  # noqa: F401
