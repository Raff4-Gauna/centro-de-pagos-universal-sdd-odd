"""``sanitize_return_path`` (RN-IDA-13, AC-IDA-19): the login never redirects off the Hub."""

from __future__ import annotations

import pytest

from apps.identity.domain.return_path import (
    DEFAULT_RETURN_PATH,
    MAX_RETURN_PATH_LENGTH,
    sanitize_return_path,
)

HOSTILE = [
    "https://evil.example/cobros",  # absolute
    "http://hub.test/cobros",  # absolute, even to a host that looks like ours
    "javascript:alert(1)",  # scheme
    "data:text/html,x",
    "mailto:a@evil.example",
    "//evil.example",  # //host
    "//evil.example/cobros",
    "///evil.example",
    "evil.example/cobros",  # another domain, no scheme
    "cobros",  # relative to wherever the browser is
    "/\\evil.example",  # browsers read "\" as "/"
    "\\\\evil.example",
    "/cobros\\..\\x",
    "/\t/evil.example",  # browsers drop tabs and line breaks
    "/\n/evil.example",
    "/cobros\r\nLocation: https://evil.example",
    "/cobros\x00",
    "/​/evil.example",  # invisible
    " /cobros",
    "",
]


@pytest.mark.parametrize("raw", HOSTILE)
def test_AC_IDA_19_hostile_return_path_goes_home(raw: str) -> None:
    assert sanitize_return_path(raw) == DEFAULT_RETURN_PATH == "/"


@pytest.mark.parametrize("raw", [None, 7, ["/cobros"], {"path": "/cobros"}, b"/cobros"])
def test_AC_IDA_19_non_text_return_path_goes_home(raw: object) -> None:
    assert sanitize_return_path(raw) == DEFAULT_RETURN_PATH


def test_AC_IDA_19_return_path_longer_than_the_column_goes_home() -> None:
    longest = "/" + "a" * (MAX_RETURN_PATH_LENGTH - 1)
    assert sanitize_return_path(longest) == longest
    assert sanitize_return_path(longest + "a") == DEFAULT_RETURN_PATH


@pytest.mark.parametrize(
    "raw", ["/", "/cobros", "/cobros/123?estado=paid&pagina=2#detalle", "/configuración/perfil"]
)
def test_AC_IDA_19_internal_path_is_kept_as_it_came(raw: str) -> None:
    assert sanitize_return_path(raw) == raw
