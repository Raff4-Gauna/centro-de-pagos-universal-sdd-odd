"""What the browser must not get from the running stack (AC-PLT-29, ``smoke_stack.py``, T-PLT-38).

A text search like the one of ``frontend/scripts/check-client-bundle.ts``, over what the stack
serves instead of the build output: the same names, plus the value the server has at runtime, which
no build holds. That hostname is an ordinary word, so alone it only counts in a page, whose text is
ours (``page_leaks_in``); in a chunk of a library it counts as part of a URL. The values copied from
other files are compared against them by a test (``test_smoke_stack_wiring.py``). Standard library
only.
"""

from __future__ import annotations

import json
import re

# What only the server may know. Each one is checked against its source by a test.
BACKEND_HOST = "backend"  # BACKEND_INTERNAL_URL in infra/docker-compose.yml
BACKEND_PORT = "8000"
BUNDLE_SENTINEL_HOST = "bundle-sentinel-backend-internal-url.invalid"  # frontend/Dockerfile
SERVER_ONLY_VARIABLES = ("BACKEND_INTERNAL_URL",)  # frontend/scripts/check-client-bundle.ts
ENV_REFERENCE = re.compile(
    r"""\benv(?:\.([A-Z][A-Z0-9_]*)\b|\[\s*["'`]([A-Z][A-Z0-9_]*)["'`]\s*\])"""
)
PUBLIC_ENV_PREFIX = "NEXT_PUBLIC_"
PUBLIC_ENV_NAMES = frozenset({"NODE_ENV"})
LEAKS = (
    # Also percent-encoded, in any case.
    (
        re.compile(rf"{BACKEND_HOST}(?::|%3a){BACKEND_PORT}|(?://|%2f%2f){BACKEND_HOST}\b", re.I),
        "the internal backend URL",
    ),
    (re.compile(re.escape(BUNDLE_SENTINEL_HOST), re.I), "the build sentinel"),
    *((re.compile(name), f"the name {name}") for name in SERVER_ONLY_VARIABLES),
)
STATIC_ASSET = re.compile(r"""/_next/static/[^"'\s\\<>?,;]+\.(?:js|css)""")


def leaks_in(text: str) -> list[str]:
    found = [label for pattern, label in LEAKS if pattern.search(text)]
    for match in ENV_REFERENCE.finditer(text):
        name = match.group(1) or match.group(2)
        if not name.startswith(PUBLIC_ENV_PREFIX) and name not in PUBLIC_ENV_NAMES:
            found.append("a non-public env reference")
    return found


def page_leaks_in(text: str) -> list[str]:
    bare_host = re.search(rf"\b{BACKEND_HOST}\b", text, re.I)
    return [*leaks_in(text), *(["the backend hostname"] if bare_host else [])]


def pages_in_manifest(manifest: str) -> list[str]:
    """The URL of every page of ``.next/app-path-routes-manifest.json``, without route handlers."""
    routes = json.loads(manifest)
    pages = {url for route, url in routes.items() if route.endswith("/page")}
    return sorted(url for url in pages if not url.startswith("/_"))


def static_assets(text: str) -> set[str]:
    """The ``/_next/static`` paths named in a page, its RSC payload or its ``Link`` header."""
    return set(STATIC_ASSET.findall(text))
