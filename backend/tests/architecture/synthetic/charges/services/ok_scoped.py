"""AC-PLT-15 / AC-TEN-10 synthetic: a service of ``apps.charges`` opens the manager with a scope.

Stands for ``apps/charges/services/ok_scoped.py``. ``Charge.objects.for_tenant(ctx)`` fails closed
at runtime without it, so neither C-01 nor the tenant rule flags it. Parsed as AST by
test_AC_PLT_15_no_raw_objects_in_services.py and test_tenant_queries.py, never imported (pytest
``norecursedirs``, mypy ``exclude``).
"""

from apps.charges.models import Charge

from apps.common.tenancy.context import TenantContext


def pending_charges(ctx: TenantContext) -> object:
    return Charge.objects.for_tenant(ctx).filter(status="pending")
