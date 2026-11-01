"""AC-PLT-08 / C-06 (T-PLT-14 review B-1): the redaction runs in linear time on hostile input.

Every log record is rendered inside ``Handler.emit``, which holds the handler's lock: a slow regex
on one event stalls the logging of every thread. A ``Host`` header of 8000 letters (logged by
``DisallowedHost``) took 9.5 s with the first version of the patterns. Now every pattern has an
anchored start (a lookbehind) and bounded repetitions, and each string is cut to ``MAX_TEXT``
characters before any pattern runs.

Budget: each case takes well under 100 ms on a developer machine; the assertion allows
``BUDGET_SECONDS`` (250 ms) so a slow, shared CI runner does not flake, and keeps the best of
``RUNS`` runs (the first one pays for warm-up and the scheduler). The quadratic patterns took
seconds on these inputs, so the margin still catches them.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.domain.redaction import MAX_TEXT, REDACTED, TRUNCATED, redact_text
from tests.logging.conftest import StdoutLog

BUDGET_SECONDS = 0.25
RUNS = 3
SIZE = 100_000


def best_time(action: Callable[[], object]) -> float:
    timings = []
    for _ in range(RUNS):
        started = time.perf_counter()
        action()
        timings.append(time.perf_counter() - started)
    return min(timings)


HOSTILE = {
    "letters": "a" * SIZE,
    "dots": "." * SIZE,
    "token_words": "token" * (SIZE // 5),
    "scheme_like": "a1+." * (SIZE // 4),
    "long_url": "http://" + "a" * SIZE,
    "at_signs": "http://" + "@" * SIZE,
    "bearer_words": "bearer " * (SIZE // 7),
    "token_and_spaces": "token " * (SIZE // 6),
    "key_separators": "token:" * (SIZE // 6),
}


@pytest.mark.parametrize("name", HOSTILE)
def test_AC_PLT_08_redaction_is_fast_on_hostile_text(name: str) -> None:
    text = HOSTILE[name]
    assert best_time(lambda: redact_text(text)) < BUDGET_SECONDS


@pytest.mark.parametrize("name", ["letters", "token_words", "key_separators", "scheme_like"])
def test_AC_PLT_08_patterns_are_linear_even_without_the_cut(name: str) -> None:
    # The cut alone would hide a quadratic pattern on 8 KB strings: time a string just under it.
    text = HOSTILE[name][: MAX_TEXT - 1]
    assert best_time(lambda: redact_text(text)) < BUDGET_SECONDS


def test_AC_PLT_08_long_text_is_cut_before_redaction() -> None:
    cleaned = redact_text("x" * (MAX_TEXT - 10) + " password=" + "p" * 50)
    assert cleaned.endswith(TRUNCATED)
    assert len(cleaned) <= MAX_TEXT + len(TRUNCATED)
    # The run cut in half is dropped whole, so half a secret never survives the cut.
    assert "password=" not in cleaned
    assert "p" * 10 not in cleaned
    # A URL crossing the cut: its "@" falls off, so the userinfo rule could not see it.
    cut_url = redact_text("y " * (MAX_TEXT // 2 - 4) + "redis://:pw-secret@host/0")
    assert cut_url.endswith(TRUNCATED)
    assert "pw-s" not in cut_url


def test_AC_PLT_08_short_text_is_not_cut() -> None:
    text = "token=abc " + "z" * 100
    assert redact_text(text) == f"token={REDACTED} " + "z" * 100


@pytest.mark.parametrize("host", ["a" * SIZE, "token" * (SIZE // 5), "a1+." * (SIZE // 4)])
def test_AC_PLT_08_request_with_huge_host_is_fast_end_to_end(
    settings: SettingsWrapper, stdout_log: StdoutLog, host: str
) -> None:
    # DisallowedHost logs the whole header (message and traceback) through the renderer.
    settings.ALLOWED_HOSTS = ["localhost"]
    client = Client()
    started = time.perf_counter()
    response = client.get("/healthz", HTTP_HOST=host)
    elapsed = time.perf_counter() - started
    assert response.status_code == 400
    assert elapsed < BUDGET_SECONDS * 2  # two events: django.security and the access log
    assert stdout_log.read().events  # still valid JSON lines
