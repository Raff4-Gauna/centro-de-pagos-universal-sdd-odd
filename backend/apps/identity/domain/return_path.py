"""Where the browser lands after the login (RN-IDA-13, AC-IDA-19): never an open redirect.

Only an internal path survives: it starts with one ``/`` and names no host. Anything else (an
absolute URL, a scheme, ``//host``, another domain, a backslash a browser reads as ``/``, a control
or invisible character a browser drops, more than the column holds) becomes "Inicio". The value is
never repaired: a hostile path is replaced whole. The BFF checks it again before redirecting.
"""

from __future__ import annotations

DEFAULT_RETURN_PATH = "/"
MAX_RETURN_PATH_LENGTH = 512


def sanitize_return_path(raw: object) -> str:
    """``raw`` if it is a safe internal path, else ``DEFAULT_RETURN_PATH``."""
    if not isinstance(raw, str) or not 0 < len(raw) <= MAX_RETURN_PATH_LENGTH:
        return DEFAULT_RETURN_PATH
    if not raw.startswith("/") or raw.startswith("//"):
        return DEFAULT_RETURN_PATH
    # Browsers read "\" as "/" and drop tabs and line breaks: "/\host" and "/<tab>/host" are
    # "//host" to them.
    if "\\" in raw or not all(char.isprintable() for char in raw):
        return DEFAULT_RETURN_PATH
    return raw
