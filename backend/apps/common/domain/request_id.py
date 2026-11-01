"""``X-Request-ID`` parsing (design.md §3.2.3, RN-PLT-07, Q-041). Pure: no Django, no I/O.

An incoming value is kept only when it is a canonical UUIDv4: 36 ASCII characters, 8-4-4-4-12 hex
digits, version 4 and the RFC 4122 variant. It comes back in lower case, the same normalisation as
the BFF (T-PLT-33/34), so browser, BFF, backend and logs carry the same string. Anything else
(another UUID version, no dashes, braces, a trailing newline, an oversized or non-ASCII header) is
dropped for a new UUIDv4: a client cannot inject text into the logs through this header.
"""

from __future__ import annotations

import re
import uuid

REQUEST_ID_LENGTH = 36
# fullmatch, not match/search with "$": "$" also matches before a final "\n".
_UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def parse_request_id(value: str | None) -> str | None:
    """The lower-case UUIDv4 in ``value``, or ``None`` when it is not exactly one."""
    # Length first: an oversized header is rejected before any other work on it.
    if value is None or len(value) != REQUEST_ID_LENGTH:
        return None
    # No non-ASCII character lower-cases to [0-9a-f-], so the pattern also rejects those.
    normalized = value.lower()
    return normalized if _UUID4.fullmatch(normalized) else None


def new_request_id() -> str:
    return str(uuid.uuid4())


def resolve_request_id(value: str | None) -> str:
    """The incoming id when valid (lower case); a new UUIDv4 otherwise."""
    return parse_request_id(value) or new_request_id()
