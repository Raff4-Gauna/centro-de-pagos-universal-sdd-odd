"""AC-PLT-21 synthetic (T-PLT-10): unannotated def in a domain/ (strict override), must fail.

Never imported nor collected: mypy's `exclude` skips synthetic/ on `mypy .`, and
test_AC_PLT_21_mypy_strict.py passes this file explicitly, named `apps.demo.domain.untyped`.
"""


def untyped(value):
    return value
