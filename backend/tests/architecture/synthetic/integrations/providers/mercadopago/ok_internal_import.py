"""AC-PLT-14 synthetic: the Mercado Pago adapter imports itself, absolute and relative (allowed).

Stands for ``apps/integrations/providers/mercadopago/ok_internal_import.py``. Parsed as AST by
test_AC_PLT_14_adapter_boundary.py, never imported (pytest ``norecursedirs``, mypy ``exclude``).
"""

import apps.integrations.providers.mercadopago  # noqa: F401
from apps.integrations.providers.mercadopago import client  # noqa: F401

from . import webhooks  # noqa: F401
from .client import Client  # noqa: F401
