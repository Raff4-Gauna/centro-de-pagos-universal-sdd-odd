"""Redaction of log events (design.md §3.2.3, RN-PLT-06, AC-PLT-08, C-06). Pure: no Django, no I/O.

``redact_mapping(event)`` returns a JSON-safe copy of a log event, recursively:

- **Keys.** The value of a secret-like key becomes ``"[REDACTED]"``, whatever its type. Keys are
  compared without case, ``-`` nor ``_`` (``Set-Cookie``/``set_cookie``), and the WSGI form of a
  header (``HTTP_AUTHORIZATION``) is the header. Exact: ``authorization``, ``proxy-authorization``,
  ``cookie``, ``set-cookie``, ``x-api-key`` and ``location`` (a redirect target or a cache
  location, ``CACHES["default"]["LOCATION"]`` is the Redis URL; T-PLT-12 review). Containing:
  ``token``, ``secret``, ``password``, ``passwd``, ``api_key``/``apikey``, ``credential``,
  ``signature``.
- **Text** (every string, the message and a rendered traceback included): a URL loses its
  ``user:password@``, query string and fragment; ``<secret-like key>=value`` (a query string
  without a URL, a libpq DSN) loses the value; ``Bearer <credential>`` loses the credential.
  Best effort: a secret written into free text in any other shape is not recognised, which is why
  the rule stays "never log it" (RN-PLT-06) and this is the net under it.
- **Linear time** (T-PLT-14 review B-1): records are rendered inside ``Handler.emit``, under the
  handler's lock, so a slow pattern on one event stalls the logging of every thread (a ``Host``
  header of 8000 letters took 9.5 s). Every pattern starts at an anchored position (a lookbehind)
  and repeats a bounded number of times before its last, greedy run; a string longer than
  ``MAX_TEXT`` characters is cut before any pattern runs. The run of non-blank characters crossing
  the cut is dropped whole (half a URL or half a ``key=value`` would no longer be recognised), and
  ``"[TRUNCATED]"`` is appended.
- **Values that are not JSON** (N-3/N-4 of the T-PLT-12 review): ``UUID``/``Decimal`` become text,
  dates their ISO form, non-finite floats ``"NaN"``/``"Infinity"``/``"-Infinity"``, sets lists;
  anything else, ``bytes`` and exceptions included, becomes ``"<TypeName>"``. Never a ``repr``: a
  request's carries the raw path and the query string, an exception's its message.
- **Shape**: a container inside itself becomes ``"[CIRCULAR]"`` and one nested deeper than
  ``MAX_DEPTH`` ``"[TRUNCATED]"``, so rendering never fails on them.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

REDACTED = "[REDACTED]"
CIRCULAR = "[CIRCULAR]"
TRUNCATED = "[TRUNCATED]"
MAX_DEPTH = 10
MAX_TEXT = 8192  # characters of one string kept before redaction (B-1)

# Compact form: lower case, no "-" nor "_".
_EXACT_KEYS = frozenset(
    {"authorization", "proxyauthorization", "cookie", "setcookie", "xapikey", "location"}
)
_KEY_PARTS = ("token", "secret", "password", "passwd", "apikey", "credential", "signature")
_WSGI_HEADER_PREFIX = "http"

# Linear by construction (B-1): each pattern can only start where the previous character cannot
# be part of its first run (lookbehind), its leading runs are bounded, and only its last run is
# unbounded and greedy (nothing after it can fail, so it never backtracks).
# scheme://... up to whitespace, a quote or an angle bracket. RFC 3986 schemes are short.
_URL = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]{0,31}://[^\s\"'<>]+")
# key=value where the key is secret-like; the value runs to a separator of query strings/DSNs.
_SECRET_PAIR = re.compile(
    r"(?i)(?<![\w.\-])"
    r"([\w.\-]{0,64}?(?:token|secret|password|passwd|api[_\-]?key|credential|signature)"
    r"[\w.\-]{0,64}?=)"
    r"[^\s&;,\"']+"
)
_BEARER = re.compile(r"(?i)(?<!\w)(bearer\s{1,16})[A-Za-z0-9\-._~+/]+=*")
_NON_FINITE = {math.inf: "Infinity", -math.inf: "-Infinity"}

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def is_secret_key(key: str) -> bool:
    compact = key.lower().replace("-", "").replace("_", "")
    if compact in _EXACT_KEYS:
        return True
    if (
        compact.startswith(_WSGI_HEADER_PREFIX)
        and compact[len(_WSGI_HEADER_PREFIX) :] in _EXACT_KEYS
    ):
        return True
    return any(part in compact for part in _KEY_PARTS)


def _redact_url(match: re.Match[str]) -> str:
    scheme, rest = match.group(0).split("://", 1)
    # Userinfo: up to the last "@" before the query/fragment (an unencoded "@" in a password).
    before_query = re.split(r"[?#]", rest, maxsplit=1)[0]
    if "@" in before_query:
        rest = REDACTED + rest[before_query.rindex("@") :]
    rest, has_fragment, _ = rest.partition("#")
    rest, has_query, _ = rest.partition("?")
    return (
        f"{scheme}://{rest}"
        + (f"?{REDACTED}" if has_query else "")
        + (f"#{REDACTED}" if has_fragment else "")
    )


def _cut(text: str) -> str:
    """``text`` up to ``MAX_TEXT`` characters, without the run of non-blanks crossing the cut."""
    if len(text) <= MAX_TEXT:
        return text
    head = text[:MAX_TEXT]
    if not text[MAX_TEXT].isspace():
        end = len(head)
        while end and not head[end - 1].isspace():
            end -= 1
        head = head[:end]
    return head + TRUNCATED


def redact_text(text: str) -> str:
    text = _URL.sub(_redact_url, _cut(text))
    text = _SECRET_PAIR.sub(lambda match: match.group(1) + REDACTED, text)
    return _BEARER.sub(lambda match: match.group(1) + REDACTED, text)


def _placeholder(value: object) -> str:
    return f"<{type(value).__name__}>"


def _key(key: object) -> str:
    if isinstance(key, str):
        return redact_text(key)
    if isinstance(key, int | float) or key is None:  # what json.dumps would turn into text
        return str(key)
    return _placeholder(key)


def _clean(value: object, depth: int, ancestors: frozenset[int]) -> JsonValue:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bool | int) or value is None:
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return _NON_FINITE.get(value, value)
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, dt.date | dt.time):  # datetime is a date
        return value.isoformat()
    if not isinstance(value, Mapping | list | tuple | set | frozenset):
        return _placeholder(value)
    if id(value) in ancestors:
        return CIRCULAR
    if depth >= MAX_DEPTH:
        return TRUNCATED
    inside = ancestors | {id(value)}
    if isinstance(value, Mapping):
        cleaned: dict[str, JsonValue] = {}
        for raw_key, item in value.items():
            key = _key(raw_key)
            secret = isinstance(raw_key, str) and is_secret_key(raw_key)
            cleaned[key] = REDACTED if secret else _clean(item, depth + 1, inside)
        return cleaned
    return [_clean(item, depth + 1, inside) for item in value]


def redact(value: object) -> JsonValue:
    """A JSON-safe copy of ``value`` with secrets redacted (see the module docstring)."""
    return _clean(value, 0, frozenset())


def redact_mapping(event: Mapping[Any, object]) -> dict[str, JsonValue]:
    """``redact`` for a log event: always a dict."""
    cleaned = redact(event)
    if not isinstance(cleaned, dict):  # unreachable: a Mapping at depth 0 is never cut
        raise TypeError("a log event must be a mapping")
    return cleaned
