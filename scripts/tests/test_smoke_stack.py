"""AC-PLT-01/02/10 (RF-PLT-07, design.md §3.5): the checks of ``scripts/smoke_stack.py`` (T-PLT-38).

Docker and HTTP are replaced by ``FakeStack`` (``smoke_stack_fakes.py``), a healthy stack each test
breaks in one way. The real run is the last step of the CI ``build`` job; here the point is that
each check fails when it should, names what failed and never leaves the stack up. How the job calls
it, the real HTTP and subprocess helpers and the values copied from other files:
``test_smoke_stack_wiring.py``.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable

import pytest
import smoke_stack
from smoke_http import HttpResponse
from smoke_stack_fakes import (
    BACKEND,
    FRONTEND,
    REQUEST_ID,
    SHA,
    SMOKE_URL,
    FakeStack,
    json_response,
)


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch) -> FakeStack:
    fake = FakeStack()
    monkeypatch.setattr(smoke_stack, "run_command", fake.run)
    monkeypatch.setattr(smoke_stack, "http_get", fake.get)
    monkeypatch.setattr(smoke_stack.time, "sleep", lambda _: None)
    monkeypatch.setenv("GIT_SHA", SHA)
    return fake


def run_smoke(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = smoke_stack.main([])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def assert_fails(capsys: pytest.CaptureFixture[str], check: str, *details: str) -> None:
    code, output = run_smoke(capsys)
    assert code == 1
    assert f"smoke failed [{check}]" in output
    for detail in details:
        assert detail in output


def test_AC_PLT_01_smoke_passes_on_a_healthy_stack(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run_smoke(capsys)
    assert code == 0, output
    assert stack.verbs == ["up", "ps", "logs", "exec", "stop", "down"]
    up = stack.commands[0]
    assert up[up.index("up") :] == ["up", "-d", "--wait", "--wait-timeout", "180"]
    # Its own project: the `down -v` of a run on a dev machine never reaches the dev volumes.
    assert up[:4] == ["docker", "compose", "-p", "hub-smoke"]
    assert up.count("-f") == 2


@pytest.mark.parametrize("service", smoke_stack.SERVICES)
@pytest.mark.parametrize(
    "state",
    [("exited", ""), ("running", "unhealthy"), ("running", "starting"), ("running", "")],
)
def test_AC_PLT_01_smoke_requires_all_services_healthy(
    service: str,
    state: tuple[str, str],
    stack: FakeStack,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stack.states[service] = state
    assert_fails(capsys, "services", service)


def test_AC_PLT_01_missing_service_counts_as_down(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    del stack.states["beat"]
    assert_fails(capsys, "services", "beat: missing")


def test_AC_PLT_01_failed_up_names_the_service_and_keeps_the_compose_error(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.failing_commands["up"] = 1
    stack.states["worker"] = ("exited", "")
    assert_fails(capsys, "services", "worker: exited", "compose said no")


def test_AC_PLT_01_failed_up_with_healthy_services_still_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.failing_commands["up"] = 1
    assert_fails(capsys, "services", "up exited with 1")


def test_AC_PLT_01_unreadable_compose_ps_fails_closed(
    stack: FakeStack, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = stack.run

    def run(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        result = real_run(argv, timeout)
        if stack.verb(argv) == "ps":
            result.stdout = "not json"
        return result

    monkeypatch.setattr(smoke_stack, "run_command", run)
    assert_fails(capsys, "services", "unreadable")


@pytest.mark.parametrize(
    "failing",
    [
        lambda s: s.failing_commands.update(up=1),
        lambda s: s.routes.update({f"{BACKEND}/readyz": json_response(500, {})}),
        lambda s: s.routes.update({SMOKE_URL: json_response(502, {})}),
        lambda s: s.routes.update({"readyz-down": json_response(200, {"status": "ready"})}),
        lambda s: s.raising_commands.add("stop"),
    ],
)
def test_AC_PLT_01_smoke_always_tears_down(
    failing: Callable[[FakeStack], None],
    stack: FakeStack,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failing(stack)
    code, _ = run_smoke(capsys)
    assert code == 1
    assert stack.verbs[-1] == "down"
    down = stack.commands[-1]
    assert down[down.index("down") :] == ["down", "-v", "--remove-orphans"]


def test_AC_PLT_01_smoke_tears_down_on_an_interrupt(
    stack: FakeStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(_: str) -> HttpResponse:
        raise KeyboardInterrupt

    monkeypatch.setattr(smoke_stack, "http_get", interrupted)
    with pytest.raises(KeyboardInterrupt):
        smoke_stack.main([])
    assert stack.verbs[-1] == "down"


def test_AC_PLT_01_failed_teardown_fails_a_green_smoke(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.failing_commands["down"] = 1
    assert_fails(capsys, "teardown", "compose said no")


def test_AC_PLT_01_teardown_that_raises_fails_the_smoke(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.raising_commands.add("down")
    assert_fails(capsys, "command:down", "docker timed out")


def test_AC_PLT_01_failure_dumps_state_and_logs_before_the_volumes_go(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{FRONTEND}/api/health"] = json_response(500, {})
    code, _ = run_smoke(capsys)
    assert code == 1
    assert stack.verbs[-3:] == ["ps", "logs", "down"]


def test_AC_PLT_01_a_symbol_the_console_cannot_encode_does_not_break_the_dump(
    stack: FakeStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Next prints a triangle in its log; a Windows console is cp1252.
    stack.routes[f"{FRONTEND}/api/health"] = json_response(500, {})
    stack.backend_log = "\u25b2 Next.js"
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(smoke_stack.sys, "stdout", console)
    assert smoke_stack.main([]) == 1
    assert stack.verbs[-1] == "down"


def test_AC_PLT_01_a_failing_dump_does_not_hide_the_failure(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{FRONTEND}/api/health"] = json_response(500, {})
    stack.raising_commands.add("logs")
    assert_fails(capsys, "bff-health", "500")
    assert stack.verbs[-1] == "down"


@pytest.mark.parametrize("value", [None, "", "main", SHA[:7], SHA.upper(), SHA + "0"])
def test_AC_PLT_01_invalid_git_sha_exits_2_without_starting_the_stack(
    value: str | None, stack: FakeStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    if value is None:
        monkeypatch.delenv("GIT_SHA")
    else:
        monkeypatch.setenv("GIT_SHA", value)
    assert smoke_stack.main([]) == 2
    assert stack.commands == []


def test_AC_PLT_01_extra_compose_file_and_urls_are_honored(
    stack: FakeStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: list[str] = []

    def get(url: str) -> HttpResponse:
        requested.append(url)
        return stack.get(url.replace(":55480", ":8000").replace(":55481", ":3000"))

    monkeypatch.setattr(smoke_stack, "http_get", get)
    argv = [
        "--compose-file",
        "ports.yml",
        "--backend-url",
        "http://127.0.0.1:55480/",
        "--frontend-url",
        "http://127.0.0.1:55481",
    ]
    assert smoke_stack.main(argv) == 0
    assert "ports.yml" in stack.commands[0]
    assert "http://127.0.0.1:55480/readyz" in requested
    assert "http://127.0.0.1:55481/api/health" in requested


def test_AC_PLT_02_readyz_must_be_200_on_the_full_stack(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{BACKEND}/readyz"] = json_response(503, {"status": "unavailable"})
    assert_fails(capsys, "readyz", "503")


def test_AC_PLT_02_redirect_is_not_ready(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{BACKEND}/readyz"] = HttpResponse(301, {"location": "https://backend/"}, "")
    assert_fails(capsys, "readyz", "301")


def test_AC_PLT_02_smoke_expects_503_with_redis_stopped(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes["readyz-down"] = json_response(200, {"status": "ready"})
    assert_fails(capsys, "readyz-redis-down", "200")


@pytest.mark.parametrize(
    "body",
    [
        {"status": "unavailable", "host": "redis:6379"},
        {"status": "unavailable", "redis": "7.4.12"},
        {"status": "unavailable", "trace": "Traceback (most recent call last)"},
        {"status": "redis://redis:6379/0"},
    ],
)
def test_AC_PLT_02_smoke_rejects_internal_details_in_body(
    body: dict[str, str], stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes["readyz-down"] = json_response(503, body)
    assert_fails(capsys, "readyz-redis-down", "exact")


def test_AC_PLT_02_body_is_not_printed_when_rejected(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes["readyz-down"] = json_response(503, {"status": "postgres://u:p@db/hub"})
    _, output = run_smoke(capsys)
    assert "postgres://" not in output


def test_AC_PLT_02_non_json_503_is_rejected(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes["readyz-down"] = HttpResponse(503, {}, "<html>Traceback</html>")
    assert_fails(capsys, "readyz-redis-down", "not JSON")


def test_AC_PLT_02_failed_redis_stop_fails_the_smoke(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.failing_commands["stop"] = 1
    assert_fails(capsys, "redis-stop", "compose said no")


def test_AC_PLT_02_healthz_compares_the_short_sha_of_the_job(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{BACKEND}/healthz"] = json_response(200, {"status": "ok", "version": "0000000"})
    assert_fails(capsys, "healthz", "0000000", SHA[:7])


def test_AC_PLT_02_healthz_stays_up_with_redis_stopped(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes["healthz-down"] = json_response(500, {})
    assert_fails(capsys, "healthz-redis-down", "500")


def test_RF_PLT_07_bff_health_must_answer_ok(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.routes[f"{FRONTEND}/api/health"] = json_response(200, {"status": "degraded"})
    assert_fails(capsys, "bff-health", "exact")


def test_AC_PLT_10_smoke_matches_bff_request_id_in_backend_logs(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.backend_log = json.dumps({"request_id": str(REQUEST_ID[::-1]), "status": 404})
    assert_fails(capsys, "request-id", REQUEST_ID, "backend")


def test_AC_PLT_10_id_in_another_field_or_as_text_is_no_match(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.backend_log = "\n".join(
        [f"plain text {REQUEST_ID}", json.dumps({"note": REQUEST_ID}), "[1, 2]"]
    )
    assert_fails(capsys, "request-id", "backend")


def test_AC_PLT_10_id_on_a_request_with_another_status_is_no_match(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.backend_log = json.dumps({"request_id": REQUEST_ID, "status": 200})
    assert_fails(capsys, "request-id", "backend")


def test_AC_PLT_10_smoke_waits_for_the_log_line(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.log_appears_after = 3
    code, output = run_smoke(capsys)
    assert code == 0, output


def test_AC_PLT_10_failed_compose_logs_fails_the_check(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.failing_commands["logs"] = 1
    assert_fails(capsys, "request-id", "compose logs")


@pytest.mark.parametrize("value", ["", "not-a-uuid", "7F1C2F7E-3D7B-4A57-9B1E-1F6A4F6F8A10"])
def test_AC_PLT_10_response_without_a_valid_request_id_fails(
    value: str, stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    headers = {"content-type": "application/problem+json", "x-request-id": value}
    stack.routes[SMOKE_URL] = HttpResponse(404, headers, '{"status": 404}')
    assert_fails(capsys, "request-id", "X-Request-ID")


@pytest.mark.parametrize(
    ("response", "detail"),
    [
        (HttpResponse(301, {"x-request-id": REQUEST_ID}, ""), "301"),
        (HttpResponse(404, {"content-type": "text/html"}, "<html>"), "content type"),
        (
            HttpResponse(
                404,
                {"content-type": "application/problem+json", "x-request-id": REQUEST_ID},
                '{"status": 500}',
            ),
            "problem status",
        ),
    ],
)
def test_AC_PLT_10_bff_must_return_the_problem_of_the_backend(
    response: HttpResponse,
    detail: str,
    stack: FakeStack,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stack.routes[SMOKE_URL] = response
    assert_fails(capsys, "request-id", detail)
