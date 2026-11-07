"""AC-IDA-31 (RN-IDA-05, Q-107): the email is compared exactly after trimming and lowercasing.

Only the normalization: the login that applies it arrives with T-IDA-12. Pure, no database.
"""

from __future__ import annotations

import pytest

from apps.identity.domain.emails import normalize_email


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Ana@X.com ", "ana@x.com"),
        ("ana@x.com", "ana@x.com"),
        ("\tANA@X.COM\n", "ana@x.com"),
    ],
)
def test_AC_IDA_31_normalize_email_trims_and_lowers(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("variant", ["ana+1@x.com", "a.na@x.com", "ana.@x.com"])
def test_AC_IDA_31_dots_and_alias_are_not_equivalent(variant: str) -> None:
    assert normalize_email(variant) == variant
    assert normalize_email(variant) != normalize_email(" Ana@X.com ")
