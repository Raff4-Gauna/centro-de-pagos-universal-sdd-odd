"""Smoke of the running stack, the last step of the CI ``build`` job (T-PLT-38, design.md §3.5).

Usage, with the images ``hub-backend:<sha>`` and ``hub-frontend:<sha>`` already built:
    GIT_SHA=<40 hex> python3 scripts/smoke_stack.py
        [--compose-file PATH]... [--backend-url URL] [--frontend-url URL]

It raises the six services with the CI override and proves, in this order:

- AC-PLT-01: ``up --wait`` and every service ``running`` and ``healthy``.
- AC-PLT-02: ``/readyz`` 200 and ``/healthz`` 200 with the short SHA of ``GIT_SHA``.
- RF-PLT-07: ``/api/health`` of the BFF 200.
- AC-PLT-10: ``GET /api/__smoke__`` on the BFF, without ``X-Request-ID``: a 404 ``problem+json``
  from Django, whose UUIDv4 ``X-Request-ID`` is the ``request_id`` of the backend access log.
- AC-PLT-29: every page of the image (its routes manifest) and every ``/_next/static`` asset they
  name, as the browser gets them, carry no value, hostname nor name of a server-only variable. A
  page rendered on request exists only at this point, and a cached ``builder`` stage prints nothing
  to rely on. Limits: a chunk no page names is left to that stage, and a transformed value (base64,
  escapes, a split string) is not found, as there.
- AC-PLT-02, with Redis stopped: ``/readyz`` 503 with the exact body, ``/healthz`` still 200.

Health bodies are compared whole, so a host, a version or a trace fails, and they are never
printed. Redirects are not followed: a 301 from ``SECURE_SSL_REDIRECT`` is a failure, not a page.

``down -v`` always runs, on Ctrl-C too, after printing the state and the last logs: the only trace
a failed job leaves. The Compose project is its own (``hub-smoke``), so a run on a dev machine never
removes the dev volumes; ``--compose-file`` and the two URLs are for when ports 8000 or 3000 are
taken.

Each failure prints ``smoke failed [<check>]: <detail>``, naming the check or service. Exit 0 ok,
1 failed, 2 invalid ``GIT_SHA`` or arguments (nothing started). Standard library only: the job
installs no Python environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smoke_http import HttpResponse, SmokeError, http_get
from smoke_leaks import leaks_in, page_leaks_in, pages_in_manifest, static_assets

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = ("infra/docker-compose.yml", "infra/docker-compose.ci.yml")
# Not where the values come from: see infra/docker-compose.ci.yml.
ENV_FILE = "env.example"
PROJECT = "hub-smoke"
SERVICES = ("db", "redis", "backend", "worker", "beat", "frontend")

GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
SHORT_SHA_LENGTH = 7  # backend/apps/common/health/views.py

WAIT_TIMEOUT_SECONDS = 180
# On top of --wait-timeout: the pull of db and redis happens before that wait starts.
UP_TIMEOUT_SECONDS = WAIT_TIMEOUT_SECONDS + 120
COMMAND_TIMEOUT_SECONDS = 60
TEARDOWN_TIMEOUT_SECONDS = 120
# Gunicorn writes the access line after answering: it can reach `compose logs` a moment later.
LOG_ATTEMPTS = 20
LOG_PAUSE_SECONDS = 0.5
TAIL_LINES = 5
DUMP_LOG_LINES = "40"

SMOKE_PATH = "/api/__smoke__"
ROUTES_MANIFEST = ".next/app-path-routes-manifest.json"
PROBLEM_CONTENT_TYPE = "application/problem+json"


@dataclass(frozen=True)
class Config:
    git_sha: str
    backend_url: str
    frontend_url: str
    extra_files: tuple[str, ...]

    @property
    def short_sha(self) -> str:
        return self.git_sha[:SHORT_SHA_LENGTH]


def run_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    verb = argv[argv.index(ENV_FILE) + 1]
    try:
        return subprocess.run(  # noqa: S603 - fixed argv
            argv,
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SmokeError(f"command:{verb}", type(error).__name__) from error


def compose(
    config: Config, *args: str, timeout: float = COMMAND_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    files = [flag for path in (*COMPOSE_FILES, *config.extra_files) for flag in ("-f", path)]
    base = ["docker", "compose", "-p", PROJECT, *files, "--env-file", ENV_FILE]
    return run_command([*base, *args], timeout)


def tail(text: str) -> str:
    return " | ".join(text.strip().splitlines()[-TAIL_LINES:])


def service_problems(config: Config) -> list[str]:
    """``<service>: <state>`` for each service that is not running and healthy."""
    result = compose(config, "ps", "--all", "--format", "json")
    try:
        if result.returncode != 0:
            raise ValueError
        containers = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        states = {c["Service"]: (c["State"], c["Health"]) for c in containers}
    except (ValueError, KeyError, TypeError) as error:
        raise SmokeError("services", "compose ps output is unreadable") from error
    problems = []
    for name in SERVICES:
        if name not in states:
            problems.append(f"{name}: missing")
        elif states[name] != ("running", "healthy"):
            state, health = states[name]
            problems.append(f"{name}: {state} {health}".rstrip())
    return problems


def check_services_healthy(config: Config) -> None:
    wait = ("--wait", "--wait-timeout", str(WAIT_TIMEOUT_SECONDS))
    result = compose(config, "up", "-d", *wait, timeout=UP_TIMEOUT_SECONDS)
    problems = service_problems(config)
    if result.returncode != 0:
        problems.append(f"up exited with {result.returncode}: {tail(result.stderr)}")
    if problems:
        raise SmokeError("services", "; ".join(problems))


def expect_status(check: str, response: HttpResponse, expected: int, path: str = "") -> None:
    if response.status != expected:
        raise SmokeError(check, f"{path} answered {response.status}, expected {expected}".strip())


def json_body(check: str, response: HttpResponse) -> Any:
    try:
        return json.loads(response.body)
    except ValueError as error:
        raise SmokeError(check, "body is not JSON") from error


def expect_exact_json(check: str, url: str, status: int, expected: dict[str, str]) -> None:
    """Status and whole body. The body is not printed: it may hold what it must not."""
    response = http_get(url)
    expect_status(check, response, status)
    if json_body(check, response) != expected:
        raise SmokeError(check, f"body is not the exact one, {sorted(expected)} only")


def check_healthz(check: str, config: Config) -> None:
    response = http_get(f"{config.backend_url}/healthz")
    expect_status(check, response, 200)
    body = json_body(check, response)
    if not isinstance(body, dict) or set(body) != {"status", "version"} or body["status"] != "ok":
        raise SmokeError(check, "body is not the exact one, status and version only")
    if body["version"] != config.short_sha:
        raise SmokeError(check, f"version {body['version']}, expected {config.short_sha}")


def is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def backend_logged(config: Config, request_id: str) -> bool:
    """A JSON line of the backend for this request: same id, and it answered the 404."""
    wanted = (request_id, 404)
    result = compose(config, "logs", "--no-color", "--no-log-prefix", "backend")
    if result.returncode != 0:
        raise SmokeError("request-id", f"compose logs failed: {tail(result.stderr)}")
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and (event.get("request_id"), event.get("status")) == wanted:
            return True
    return False


def check_request_id(config: Config) -> None:
    check = "request-id"
    response = http_get(f"{config.frontend_url}{SMOKE_PATH}")
    expect_status(check, response, 404)
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith(PROBLEM_CONTENT_TYPE):
        raise SmokeError(check, f"content type {content_type!r}, expected problem+json")
    request_id = response.headers.get("x-request-id", "")
    if not is_uuid4(request_id):
        raise SmokeError(check, "the BFF returned no valid X-Request-ID")
    body = json_body(check, response)
    if not isinstance(body, dict) or body.get("status") != 404:
        raise SmokeError(check, "problem status is not 404: not the problem of the backend")
    for attempt in range(LOG_ATTEMPTS):
        if attempt:
            time.sleep(LOG_PAUSE_SECONDS)
        if backend_logged(config, request_id):
            return
    raise SmokeError(check, f"no 404 with request_id {request_id} in the backend log")


def page_paths(config: Config) -> list[str]:
    """The pages the image really has: a fixed list would miss the next dynamic one."""
    check = "client-bundle"
    result = compose(config, "exec", "-T", "frontend", "cat", ROUTES_MANIFEST)
    try:
        if result.returncode != 0:
            raise ValueError
        pages = pages_in_manifest(result.stdout)
    except (ValueError, AttributeError) as error:
        raise SmokeError(check, f"{ROUTES_MANIFEST} is unreadable") from error
    parametrized = [path for path in pages if "[" in path]
    if parametrized:
        raise SmokeError(check, f"no URL to render {parametrized}: give the smoke a sample one")
    if not pages:
        raise SmokeError(check, "no page in the manifest: nothing was checked")
    return pages


def page_text(response: HttpResponse) -> str:
    return "\n".join([response.body, *response.headers.values()])


def fail_on_leaks(path: str, found: list[str]) -> None:
    if found:
        raise SmokeError("client-bundle", f"{path} carries {', '.join(sorted(set(found)))}")


def check_client_bundle(frontend_url: str, pages: Sequence[str]) -> None:
    """A redirect is fine for a page (``/`` has no screen); what it sends is checked too."""
    check = "client-bundle"
    assets: set[str] = set()
    rendered_on_request = 0
    for path in pages:
        response = http_get(f"{frontend_url}{path}")
        if not 200 <= response.status < 400:
            raise SmokeError(check, f"{path} answered {response.status}, expected a page")
        rendered_on_request += "x-nextjs-prerender" not in response.headers
        text = page_text(response)
        fail_on_leaks(path, page_leaks_in(text))
        assets.update(static_assets(text))
    if not any(asset.endswith(".js") for asset in assets):
        raise SmokeError(check, "no client chunk in the pages: nothing was checked")
    for path in sorted(assets):
        response = http_get(f"{frontend_url}{path}")
        expect_status(check, response, 200, path)
        fail_on_leaks(path, leaks_in(page_text(response)))
    print(
        f"ok: client bundle clean over HTTP: {len(pages)} pages "
        f"({rendered_on_request} rendered on request), {len(assets)} assets"
    )


def check_redis_down(config: Config) -> None:
    result = compose(config, "stop", "redis")
    if result.returncode != 0:
        raise SmokeError("redis-stop", tail(result.stderr))
    readyz = f"{config.backend_url}/readyz"
    expect_exact_json("readyz-redis-down", readyz, 503, {"status": "unavailable"})
    check_healthz("healthz-redis-down", config)


def run_checks(config: Config) -> None:
    backend, frontend = config.backend_url, config.frontend_url
    check_services_healthy(config)
    print(f"ok: {len(SERVICES)} services healthy")
    expect_exact_json("readyz", f"{backend}/readyz", 200, {"status": "ready"})
    check_healthz("healthz", config)
    print(f"ok: readyz 200, healthz 200 with version {config.short_sha}")
    expect_exact_json("bff-health", f"{frontend}/api/health", 200, {"status": "ok"})
    print("ok: BFF health 200")
    check_request_id(config)
    print("ok: X-Request-ID of the BFF in the backend log")
    check_client_bundle(frontend, page_paths(config))
    check_redis_down(config)
    print("ok: redis stopped, readyz 503 with no details, healthz 200")


def show(text: str) -> None:
    """Compose prints symbols a legacy console cannot encode: never a crash over a log line."""
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def report(error: SmokeError) -> None:
    print(f"smoke failed [{error.check}]: {error.detail}", file=sys.stderr, flush=True)


def dump_stack(config: Config) -> None:
    """State and last logs, before ``down -v`` removes them. It never replaces the failure."""
    try:
        for args in (("ps", "--all"), ("logs", "--no-color", "--tail", DUMP_LOG_LINES)):
            show(compose(config, *args).stdout)
    except SmokeError as error:
        report(error)


def teardown(config: Config) -> int:
    try:
        result = compose(config, "down", "-v", "--remove-orphans", timeout=TEARDOWN_TIMEOUT_SECONDS)
    except SmokeError as error:
        report(error)
        return 1
    if result.returncode != 0:
        report(SmokeError("teardown", tail(result.stderr)))
        return 1
    return 0


def http_url(value: str) -> str:
    if not re.fullmatch(r"https?://[^/\s]+/?", value):
        raise argparse.ArgumentTypeError(f"not an http(s) origin: {value}")
    return value.rstrip("/")


def load_config(argv: Sequence[str] | None) -> Config:
    parser = argparse.ArgumentParser(description="Smoke of the running stack (design.md §3.5).")
    parser.add_argument("--compose-file", action="append", default=[], dest="extra_files")
    parser.add_argument("--backend-url", type=http_url, default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", type=http_url, default="http://127.0.0.1:3000")
    args = parser.parse_args(argv)
    git_sha = os.environ.get("GIT_SHA", "")
    if not GIT_SHA_RE.fullmatch(git_sha):
        raise SmokeError("git-sha", "GIT_SHA must be the 40-hex commit of the images")
    return Config(git_sha, args.backend_url, args.frontend_url, tuple(args.extra_files))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = load_config(argv)
    except SmokeError as error:
        report(error)
        return 2
    status = 0
    try:
        run_checks(config)
    except SmokeError as error:
        report(error)
        dump_stack(config)
        status = 1
    finally:
        # Also on an interrupt, which goes on after this.
        status = teardown(config) or status
    if status == 0:
        print("smoke passed")
    return status


if __name__ == "__main__":
    sys.exit(main())
