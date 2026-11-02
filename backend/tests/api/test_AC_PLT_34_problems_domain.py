"""AC-PLT-34 (RN-PLT-15): the pure ``problem+json`` envelope of ``api.problems`` (T-PLT-15).

``errors[]`` flattens nested validation details into dotted field paths; ``detail`` never survives
on a 5xx, whatever the caller passes; a ``code`` without a fixed title gets the HTTP phrase.
"""

from __future__ import annotations

from apps.common.api.problems import build_problem, validation_errors


class _Detail(str):
    code = "invalid_choice"


def test_AC_PLT_34_validation_errors_flatten_nested_and_non_field_details() -> None:
    nested = {"items": [{}, {"qty": [_Detail("bad")]}], "non_field_errors": ["both"]}
    assert validation_errors(nested, "non_field_errors") == [
        {"field": "items.1.qty", "code": "invalid_choice", "message": "bad"},
        {"field": "non_field_errors", "code": "invalid", "message": "both"},
    ]
    assert validation_errors([_Detail("x")], "general") == [
        {"field": "general", "code": "invalid_choice", "message": "x"}
    ]


def test_AC_PLT_34_any_5xx_drops_detail_and_unknown_codes_get_the_http_phrase() -> None:
    unavailable = build_problem(code="charges.down", status=503, request_id="r", detail="host x")
    assert "detail" not in unavailable
    assert unavailable["title"] == "Service Unavailable"
    assert build_problem(code="odd", status=599, request_id=None)["title"] == "Error"
