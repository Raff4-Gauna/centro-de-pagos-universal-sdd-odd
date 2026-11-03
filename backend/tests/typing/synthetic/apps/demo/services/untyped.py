"""AC-PLT-21 synthetic (T-PLT-10): unannotated def in a services/ (only check_untyped_defs), passes.

Never imported nor collected: mypy's `exclude` skips synthetic/ on `mypy .`, and
test_AC_PLT_21_mypy_strict.py passes this file explicitly, named `apps.demo.services.untyped`.
"""


def untyped(value):
    return value
