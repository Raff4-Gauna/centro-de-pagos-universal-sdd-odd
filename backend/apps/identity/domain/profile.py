"""What is kept of Google's profile (RNF-IDA-05, Q-115; design.md §5 and §7.7).

A name or avatar that is missing, too long or unusable never rejects a login (spec §12): it is
stored cut or empty.
"""

from __future__ import annotations

from urllib.parse import urlsplit

MAX_DISPLAY_NAME = 150
MAX_AVATAR_URL = 500


def clamp_display_name(value: str | None) -> str:
    return (value or "")[:MAX_DISPLAY_NAME]


def clean_avatar_url(value: str | None) -> str:
    """``value`` if it is https and fits, otherwise empty: a URL cut short would point elsewhere."""
    if not value or len(value) > MAX_AVATAR_URL:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    return value if parts.scheme == "https" and parts.hostname else ""
