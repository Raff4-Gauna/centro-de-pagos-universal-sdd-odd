"""AC-PLT-08 (RN-PLT-06, C-06): the pure redaction of ``apps.common.domain.redaction`` (T-PLT-14).

Keys of design.md §3.2.3 (plus ``location`` and ``proxy-authorization``, T-PLT-12 review) are
compared without case, ``-`` nor ``_``, so headers in any spelling and their WSGI form
(``HTTP_AUTHORIZATION``) match. Strings keep their text but lose URL credentials, query strings,
fragments, ``<secret-like key>=value`` pairs and ``Bearer`` credentials. Anything that is not a JSON
value becomes JSON-safe without its ``repr`` (N-3, N-4 of the T-PLT-12 review).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest

from apps.common.domain.redaction import (
    CIRCULAR,
    MAX_DEPTH,
    REDACTED,
    TRUNCATED,
    is_secret_key,
    redact,
    redact_mapping,
    redact_text,
)

SENTINEL = "sentinel-c0ffee"


@pytest.mark.parametrize(
    "key",
    [
        "authorization",
        "Authorization",
        "HTTP_AUTHORIZATION",
        "proxy-authorization",
        "cookie",
        "HTTP_COOKIE",
        "Set-Cookie",
        "set_cookie",
        "X-API-Key",
        "HTTP_X_API_KEY",
        "location",
        "LOCATION",
        "access_token",
        "refreshToken",
        "client_secret",
        "DB_PASSWORD",
        "passwd",
        "api_key",
        "apiKey",
        "mp-api-key",
        "credentials",
        "webhook_signature",
    ],
)
def test_AC_PLT_08_secret_like_keys_match_in_any_spelling(key: str) -> None:
    assert is_secret_key(key)


@pytest.mark.parametrize(
    "key",
    ["route", "status", "request_id", "organization_id", "message", "allocation", "cookies_ok"],
)
def test_AC_PLT_08_ordinary_keys_are_kept(key: str) -> None:
    assert not is_secret_key(key)


def test_AC_PLT_08_redacts_nested_secret_like_keys_at_any_depth() -> None:
    event = {
        "message": "demo",
        "headers": {"Authorization": f"Bearer {SENTINEL}", "Accept": "application/json"},
        "attempts": [{"provider": {"client_secret": SENTINEL, "name": "mp"}}],
        "cache": ({"LOCATION": f"redis://:{SENTINEL}@redis.example:6379/0"},),
        "password": {"nested": "whole value goes, whatever its type"},
    }
    cleaned = redact_mapping(event)
    assert SENTINEL not in repr(cleaned)
    assert cleaned["headers"] == {"Authorization": REDACTED, "Accept": "application/json"}
    assert cleaned["attempts"] == [{"provider": {"client_secret": REDACTED, "name": "mp"}}]
    assert cleaned["cache"] == [{"LOCATION": REDACTED}]
    assert cleaned["password"] == REDACTED
    assert cleaned["message"] == "demo"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("redis://:pw-1@redis.example:6379/0", f"redis://{REDACTED}@redis.example:6379/0"),
        ("postgres://hub:pw-2@db.example/hub", f"postgres://{REDACTED}@db.example/hub"),
        # An unencoded "@" in the password: everything up to the last "@" of the authority goes.
        ("redis://:p@ss@redis.example/0", f"redis://{REDACTED}@redis.example/0"),
        (
            "https://api.example/v1/items?access_token=t1&x=1",
            f"https://api.example/v1/items?{REDACTED}",
        ),
        ("https://app.example/cb#access_token=t2", f"https://app.example/cb#{REDACTED}"),
        ("https://api.example/v1?q=1#frag", f"https://api.example/v1?{REDACTED}#{REDACTED}"),
        ("https://api.example/v1/items", "https://api.example/v1/items"),
        (
            "connect to redis://u:pw@h:1/0 failed, retry https://x.example/?a=b",
            f"connect to redis://{REDACTED}@h:1/0 failed, retry https://x.example/?{REDACTED}",
        ),
        ("host=db password=pw-3 dbname=hub", f"host=db password={REDACTED} dbname=hub"),
        ("/items?access_token=t3&page=2", f"/items?access_token={REDACTED}&page=2"),
        ("api_key=k1; client_secret=s1", f"api_key={REDACTED}; client_secret={REDACTED}"),
        ("Authorization: Bearer abc.def-ghi_123", f"Authorization: Bearer {REDACTED}"),
        ("no secrets here: 3 items", "no secrets here: 3 items"),
    ],
)
def test_AC_PLT_08_text_loses_url_credentials_queries_and_secret_pairs(
    text: str, expected: str
) -> None:
    assert redact_text(text) == expected


class Opaque:
    def __repr__(self) -> str:
        return f"<Opaque /raw/path?token={SENTINEL}>"

    def __str__(self) -> str:
        return repr(self)


def test_AC_PLT_08_objects_become_their_type_name_never_their_repr() -> None:
    # N-3 (T-PLT-12 review): a request passed as a kwarg renders "<WSGIRequest: GET '/raw?q=…'>".
    error = ValueError(f"input_value={SENTINEL}")
    cleaned = redact_mapping(
        {"request": Opaque(), "error": error, "raw": SENTINEL.encode(), "items": [Opaque()]}
    )
    assert cleaned == {
        "request": "<Opaque>",
        "error": "<ValueError>",
        "raw": "<bytes>",
        "items": ["<Opaque>"],
    }


def test_AC_PLT_08_json_values_keep_their_type_and_known_types_become_text() -> None:
    org = uuid.UUID("3f2b8c1e-9d4a-4b7e-8f21-6c0d5e9a7b13")
    when = dt.datetime(2026, 11, 1, 12, 30, tzinfo=dt.UTC)
    cleaned = redact_mapping(
        {
            "count": 3,
            "ok": True,
            "none": None,
            "ms": 1.5,
            "org": org,
            "amount": Decimal("10.50"),
            "at": when,
            "day": dt.date(2026, 11, 1),
            "tags": {"only"},
            1: "int key",
        }
    )
    assert cleaned == {
        "count": 3,
        "ok": True,
        "none": None,
        "ms": 1.5,
        "org": str(org),
        "amount": "10.50",
        "at": "2026-11-01T12:30:00+00:00",
        "day": "2026-11-01",
        "tags": ["only"],
        "1": "int key",
    }


def test_AC_PLT_08_object_keys_never_show_their_repr() -> None:
    assert redact_mapping({Opaque(): "value"}) == {"<Opaque>": "value"}


def test_RN_PLT_05_non_finite_floats_become_strings() -> None:
    # N-4 (T-PLT-12 review): NaN and Infinity are not JSON.
    values = [float("nan"), float("inf"), float("-inf")]
    assert redact(values) == ["NaN", "Infinity", "-Infinity"]


def test_RN_PLT_05_cycles_are_cut_and_depth_is_capped() -> None:
    # N-2 (T-PLT-12 review): a circular dict made json.dumps fail and logging print a traceback.
    circular: dict[str, Any] = {"name": "loop"}
    circular["self"] = circular
    looped: list[Any] = []
    looped.append(looped)
    assert redact_mapping({"data": circular, "list": looped}) == {
        "data": {"name": "loop", "self": CIRCULAR},
        "list": [CIRCULAR],
    }
    deep: dict[str, Any] = {}
    node = deep
    for _ in range(MAX_DEPTH + 5):
        node["next"] = {}
        node = node["next"]
    flattened = repr(redact(deep))
    assert TRUNCATED in flattened
    assert flattened.count("next") == MAX_DEPTH


def test_RN_PLT_05_shared_references_are_not_cycles() -> None:
    shared = {"a": 1}
    assert redact_mapping({"x": shared, "y": shared}) == {"x": {"a": 1}, "y": {"a": 1}}
