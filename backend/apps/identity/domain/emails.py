"""Email comparison (RN-IDA-05, Q-107): exact after trimming and lowercasing.

Dots and ``+`` aliases are left alone: ``ana+1@x.com`` is another address, not a variant of Ana's.
"""

from __future__ import annotations


def normalize_email(email: str) -> str:
    return email.strip().lower()
