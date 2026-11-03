"""Glob matching for repo-relative POSIX paths, with ``**`` (stdlib only).

Used by the repo-level checks (``check_file_size.py`` exclusions, ``zona-roja`` path list).
``fnmatch`` is not enough: its ``*`` crosses ``/`` and it has no ``**``.

Syntax (paths are the ones ``git ls-files`` prints: relative to the repo root, ``/``-separated):

- ``*`` matches any run of characters inside one path segment (never ``/``).
- ``?`` matches exactly one character other than ``/``.
- ``**`` must be a whole segment and matches zero or more segments: ``**/x`` matches ``x`` and
  ``a/b/x``; ``a/**`` matches everything below ``a/``; ``**`` alone matches anything.
- ``{a,b}`` expands to alternatives (nesting allowed), e.g. ``frontend/{tsconfig.json,ruff.toml}``.
- Anything else is literal (``[`` included). Patterns are anchored at the repo root and are
  case-sensitive.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache


def expand_braces(pattern: str) -> list[str]:
    """Expand ``{a,b}`` alternatives into plain patterns, left to right."""
    start = pattern.find("{")
    if start == -1:
        if "}" in pattern:
            raise ValueError(f"unbalanced '}}' in glob {pattern!r}")
        return [pattern]
    depth = 0
    options: list[str] = []
    option_start = start + 1
    for index in range(start, len(pattern)):
        char = pattern[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                options.append(pattern[option_start:index])
                prefix, suffix = pattern[:start], pattern[index + 1 :]
                return [
                    expanded
                    for option in options
                    for expanded in expand_braces(prefix + option + suffix)
                ]
        elif char == "," and depth == 1:
            options.append(pattern[option_start:index])
            option_start = index + 1
    raise ValueError(f"unbalanced '{{' in glob {pattern!r}")


def _translate(pattern: str) -> str:
    """Translate one brace-free glob into a regex body (no anchors)."""
    if not pattern or pattern.startswith("/"):
        raise ValueError(f"glob must be a non-empty repo-relative path, got {pattern!r}")
    parts: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        if pattern.startswith("**", index):
            end = index + 2
            starts_segment = index == 0 or pattern[index - 1] == "/"
            ends_segment = end == length or pattern[end] == "/"
            if not (starts_segment and ends_segment):
                raise ValueError(f"'**' must be a whole path segment in glob {pattern!r}")
            if end == length:
                parts.append(".*")
                index = end
            else:
                parts.append("(?:[^/]+/)*")
                index = end + 1
            continue
        char = pattern[index]
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return "".join(parts)


@lru_cache(maxsize=256)
def compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile ``pattern`` (braces included) into a regex to use with ``fullmatch``."""
    alternatives = "|".join(_translate(expanded) for expanded in expand_braces(pattern))
    return re.compile(f"(?:{alternatives})", re.DOTALL)


def matches(path: str, pattern: str) -> bool:
    """True if the repo-relative POSIX ``path`` matches ``pattern``."""
    return compile_glob(pattern).fullmatch(path) is not None


def match_any(path: str, patterns: Iterable[str]) -> bool:
    """True if ``path`` matches at least one of ``patterns``."""
    return any(matches(path, pattern) for pattern in patterns)
