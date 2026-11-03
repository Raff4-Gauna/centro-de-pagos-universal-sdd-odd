"""AC-PLT-15 synthetic: a service of ``apps.charges`` reads through ``Model.objects`` (C-01).

Stands for ``apps/charges/services/bad_objects.py``. Parsed as AST by
test_AC_PLT_15_no_raw_objects_in_services.py, never imported (pytest ``norecursedirs``, mypy
``exclude``).
"""

from apps.charges.models import Charge


def pending_charges() -> object:
    return Charge.objects.filter(status="pending")
