"""The CUIT of an organization (RF-TEN-03, Q-209, design.md §5). Pure: no Django.

``normalize_tax_id(value)`` is what the services keep: surrounding spaces removed, then empty (the
CUIT is optional, Q-209) or 11 digits, written plain or as ``XX-XXXXXXXX-X``, with a valid check
digit. It returns the 11 digits without hyphens, the only form the database accepts
(``org_tax_id_digits``). Only ASCII digits: ``str.isdigit`` would take other scripts' digits.

The check digit is AFIP's modulo 11: the first ten digits times ``5 4 3 2 7 6 5 4 3 2``, summed;
the digit is ``11 - sum % 11``, ``11`` is written ``0`` and ``10`` gives no valid CUIT.
``InvalidTaxIdError`` never carries the value it rejected.
"""

from __future__ import annotations

import re

_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_FORMAT = re.compile(r"[0-9]{11}|[0-9]{2}-[0-9]{8}-[0-9]", re.ASCII)


class InvalidTaxIdError(ValueError):
    def __init__(self) -> None:
        super().__init__("not a valid CUIT")


def is_valid_cuit(digits: str) -> bool:
    """Whether ``digits`` (11 ASCII digits, no hyphens) has the right check digit."""
    if len(digits) != len(_WEIGHTS) + 1 or not digits.isascii() or not digits.isdigit():
        return False
    total = sum(int(digit) * weight for digit, weight in zip(digits[:-1], _WEIGHTS, strict=True))
    expected = 11 - total % 11
    if expected == 11:
        expected = 0
    return expected != 10 and int(digits[-1]) == expected


def normalize_tax_id(value: str) -> str:
    """The 11 digits to keep, or ``""``; ``InvalidTaxIdError`` for anything else."""
    value = value.strip()
    if not value:
        return ""
    if not _FORMAT.fullmatch(value):
        raise InvalidTaxIdError
    digits = value.replace("-", "")
    if not is_valid_cuit(digits):
        raise InvalidTaxIdError
    return digits
