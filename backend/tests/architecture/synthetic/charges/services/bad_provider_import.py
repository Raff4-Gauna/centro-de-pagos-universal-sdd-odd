"""AC-PLT-14 synthetic: a service of ``apps.charges`` imports the Mercado Pago adapter (C-09).

Stands for ``apps/charges/services/bad_provider_import.py``. Parsed as AST by
test_AC_PLT_14_adapter_boundary.py, never imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

import apps.integrations.providers.mercadopago  # noqa: F401 - the violation under test
