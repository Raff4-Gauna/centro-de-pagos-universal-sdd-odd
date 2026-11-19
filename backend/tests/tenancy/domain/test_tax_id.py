"""The CUIT of an organization (RF-TEN-03, Q-209, design.md §5). Pure: no database.

``normalize_tax_id`` accepts 11 digits, with or without the hyphens of ``XX-XXXXXXXX-X``, and gives
back the 11 digits the database keeps (``org_tax_id_digits``); empty clears it. The check digit is
AFIP's modulo 11 with weights ``5 4 3 2 7 6 5 4 3 2``: ``11`` becomes ``0`` and ``10`` has no valid
digit. The valid numbers below were computed by hand with those weights.
"""

from __future__ import annotations

import pytest

from apps.tenancy.domain.tax_id import InvalidTaxIdError, is_valid_cuit, normalize_tax_id

VALID = ("20123456786", "30712345671", "20000000060")


@pytest.mark.parametrize("cuit", VALID)
def test_tax_id_check_digit(cuit: str) -> None:
    assert is_valid_cuit(cuit)
    wrong = (int(cuit[-1]) + 1) % 10
    assert not is_valid_cuit(f"{cuit[:-1]}{wrong}")


def test_tax_id_check_digit_eleven_is_zero() -> None:
    """``2000000006``: the remainder gives 11, so the check digit is 0 (and nothing else)."""
    assert [d for d in range(10) if is_valid_cuit(f"2000000006{d}")] == [0]


def test_tax_id_check_digit_ten_has_no_valid_number() -> None:
    """``2000000001``: the remainder gives 10, which is no digit: every number is rejected."""
    assert [d for d in range(10) if is_valid_cuit(f"2000000001{d}")] == []


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("20123456786", "20123456786"),
        ("20-12345678-6", "20123456786"),
        ("  30-71234567-1 ", "30712345671"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_tax_id_normalizes_to_eleven_digits(given: str, kept: str) -> None:
    assert normalize_tax_id(given) == kept


@pytest.mark.parametrize(
    "given",
    [
        "20123456785",  # wrong check digit
        "2012345678",  # 10 digits
        "201234567860",  # 12 digits
        "20-1234567-86",  # hyphens out of place
        "20--12345678-6",
        "2012345678-6",  # only one hyphen
        "20 12345678 6",
        "2O123456786",  # a letter O
        "٢٠١٢٣٤٥٦٧٨٦",  # Arabic-Indic digits: \d would take them, the database would not
    ],
)
def test_tax_id_rejects_what_is_not_a_cuit(given: str) -> None:
    with pytest.raises(InvalidTaxIdError):
        normalize_tax_id(given)


def test_tax_id_error_does_not_echo_the_input() -> None:
    with pytest.raises(InvalidTaxIdError) as raised:
        normalize_tax_id("20123456785")
    assert "20123456785" not in str(raised.value)
