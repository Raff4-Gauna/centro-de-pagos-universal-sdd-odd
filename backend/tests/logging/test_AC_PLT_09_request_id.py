"""AC-PLT-09 (RN-PLT-07, Q-041): the ``X-Request-ID`` of a request, in the log and the response.

A valid UUIDv4 is kept, normalised to lower case like the BFF does (T-PLT-33/34); anything else (not
a UUID, another version, a trailing newline, an oversized header) is replaced by a new UUIDv4, so a
client cannot inject text into the logs. ``RequestIdMiddleware`` is the first middleware and returns
the header on every response, errors included.
"""

from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from django.test import Client

from apps.common.domain.request_id import parse_request_id, resolve_request_id
from apps.common.logging import context, get_logger
from apps.common.middleware.access_log import ACCESS_EVENT
from apps.common.middleware.request_id import REQUEST_ID_HEADER
from tests.api.urls_test import STDLIB_EVENT, STRUCTLOG_EVENT
from tests.logging.conftest import CapturedLog, StdoutLog

VALID = "3f2b8c1e-9d4a-4b7e-8f21-6c0d5e9a7b13"

pytestmark = pytest.mark.urls("tests.api.urls_test")


def assert_is_new_uuid4(value: str, incoming: str) -> None:
    assert value != incoming
    parsed = uuid.UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value  # canonical, lower case


def logged_request_ids(log: CapturedLog) -> list[str]:
    """``request_id`` of the two events the test view logs (structlog and stdlib)."""
    events = [*log.find(STRUCTLOG_EVENT), *log.find(STDLIB_EVENT)]
    assert len(events) == 2, log.out
    return [event["request_id"] for event in events]


@pytest.mark.parametrize("incoming", [VALID, VALID.upper()])
def test_AC_PLT_09_valid_uuid4_is_kept_in_log_and_response(
    client: Client, stdout_log: StdoutLog, incoming: str
) -> None:
    response = client.get("/test/log", headers={REQUEST_ID_HEADER: incoming})
    assert response.status_code == 200
    # Kept, in lower case: the same string the BFF logs and returns.
    assert response[REQUEST_ID_HEADER] == VALID
    assert logged_request_ids(stdout_log.read()) == [VALID, VALID]


@pytest.mark.parametrize(
    "incoming",
    [
        "not-a-uuid",
        "",
        str(uuid.uuid1()),  # a UUID, but not version 4
        VALID.replace("-", ""),  # no dashes
        "{" + VALID[1:-1] + "}",  # 36 characters, braces
        VALID[:-1] + "g",  # not hex
        VALID[:19] + "c" + VALID[20:],  # RFC 4122 variant digit out of [89ab]
        '","level":"error","message":"forged',  # an attempt to inject JSON fields
        VALID[:-1] + chr(0x430),  # a non-ASCII last character (Cyrillic "a")
    ],
)
def test_AC_PLT_09_non_uuid_is_replaced_by_new_uuid4(
    client: Client, stdout_log: StdoutLog, incoming: str
) -> None:
    response = client.get("/test/log", headers={REQUEST_ID_HEADER: incoming})
    returned = response[REQUEST_ID_HEADER]
    assert_is_new_uuid4(returned, incoming)
    log = stdout_log.read()
    assert logged_request_ids(log) == [returned, returned]
    assert "forged" not in log.out


def test_AC_PLT_09_missing_header_gets_a_new_uuid4(client: Client, stdout_log: StdoutLog) -> None:
    response = client.get("/test/log")
    returned = response[REQUEST_ID_HEADER]
    assert_is_new_uuid4(returned, "")
    assert logged_request_ids(stdout_log.read()) == [returned, returned]


@pytest.mark.parametrize("suffix", ["\n", "\r\n", "\r"])
def test_AC_PLT_09_trailing_newline_is_replaced(
    client: Client, stdout_log: StdoutLog, suffix: str
) -> None:
    # fullmatch: a valid UUID followed by a line break is not valid (re.match with $ would be).
    response = client.get("/test/log", headers={REQUEST_ID_HEADER: VALID + suffix})
    returned = response[REQUEST_ID_HEADER]
    assert_is_new_uuid4(returned, VALID)
    log = stdout_log.read()
    assert logged_request_ids(log) == [returned, returned]
    assert VALID not in log.out


def test_AC_PLT_09_oversized_header_is_replaced(client: Client, stdout_log: StdoutLog) -> None:
    oversized = VALID + "-" + "a" * 8192
    response = client.get("/test/log", headers={REQUEST_ID_HEADER: oversized})
    returned = response[REQUEST_ID_HEADER]
    assert_is_new_uuid4(returned, VALID)
    log = stdout_log.read()
    assert logged_request_ids(log) == [returned, returned]
    assert "a" * 64 not in log.out


def test_AC_PLT_09_header_is_returned_on_an_error_response(
    stdout_log: StdoutLog,
) -> None:
    client = Client(raise_request_exception=False)
    response = client.get("/test/error", headers={REQUEST_ID_HEADER: VALID})
    assert response.status_code == 500
    assert response[REQUEST_ID_HEADER] == VALID
    # The access log (T-PLT-13) reports the failure; django.request is silenced (raw path).
    (access,) = stdout_log.read().find(ACCESS_EVENT)
    assert (access["level"], access["status"], access["request_id"]) == ("error", 500, VALID)


def test_AC_PLT_09_context_does_not_outlive_the_request(
    client: Client, stdout_log: StdoutLog
) -> None:
    client.get("/test/log", headers={REQUEST_ID_HEADER: VALID})
    assert context.current_request_id() is None
    get_logger("tests.after_request").info("test.after_request")
    (event,) = stdout_log.read().find("test.after_request")
    assert "request_id" not in event


def test_AC_PLT_09_request_id_middleware_is_first() -> None:
    assert settings.MIDDLEWARE[0] == "apps.common.middleware.request_id.RequestIdMiddleware"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (VALID, VALID),
        (VALID.upper(), VALID),
        (None, None),
        (VALID + "\n", None),
        (" " + VALID[1:], None),
        (VALID[:14] + "1" + VALID[15:], None),  # version 1
    ],
)
def test_AC_PLT_09_parse_request_id_accepts_only_canonical_uuid4(
    value: str | None, expected: str | None
) -> None:
    assert parse_request_id(value) == expected


def test_AC_PLT_09_resolve_request_id_generates_a_fresh_one_each_time() -> None:
    first, second = resolve_request_id("bad"), resolve_request_id("bad")
    assert first != second
    assert parse_request_id(first) == first
