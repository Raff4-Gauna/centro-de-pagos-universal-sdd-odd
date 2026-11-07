"""How ``scripts/smoke_stack.py`` plugs in (T-PLT-38).

The two real I/O helpers (a local HTTP server, a fake ``subprocess.run``), the CI step, the values
of the override the smoke relies on, and the constants copied from other files, compared against
their source so that they cannot drift apart. The checks: ``test_smoke_stack.py``,
``test_smoke_client_bundle.py`` and ``test_smoke_pages.py``.
"""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import smoke_http
import smoke_leaks
import smoke_stack
import yaml
from smoke_http import SmokeError

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "abcdef0" + "1" * 33


def test_AC_PLT_01_internal_url_matches_the_compose_file() -> None:
    compose = (REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    url = f"http://{smoke_leaks.BACKEND_HOST}:{smoke_leaks.BACKEND_PORT}"
    assert f"BACKEND_INTERNAL_URL: {url}" in compose


@pytest.fixture
def local_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(301)
                self.send_header("Location", "/never-followed")
                self.end_headers()
                return
            status = 404 if self.path == "/missing" else 200
            self.send_response(status)
            self.send_header("X-Request-ID", "abc")
            self.end_headers()
            self.wfile.write(b"caf\xc3\xa9")

        def log_message(self, *_: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_AC_PLT_02_http_get_reads_status_lowercase_headers_and_body(local_server: str) -> None:
    response = smoke_http.http_get(f"{local_server}/ok")
    assert (response.status, response.body) == (200, "café")
    assert response.headers["x-request-id"] == "abc"


def test_AC_PLT_02_http_get_returns_an_error_status_instead_of_raising(local_server: str) -> None:
    assert smoke_http.http_get(f"{local_server}/missing").status == 404


def test_AC_PLT_02_http_get_never_follows_a_redirect(local_server: str) -> None:
    # The 301 of SECURE_SSL_REDIRECT, answered as what it is: a followed one would hide it.
    response = smoke_http.http_get(f"{local_server}/redirect")
    assert response.status == 301
    assert response.headers["location"] == "/never-followed"


def test_AC_PLT_02_http_get_failure_names_the_url() -> None:
    with pytest.raises(SmokeError) as caught:
        smoke_http.http_get("http://127.0.0.1:1/readyz")
    assert caught.value.check == "http"
    assert "127.0.0.1:1/readyz" in caught.value.detail


def test_AC_PLT_01_run_command_timeout_names_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*_: Any, **__: Any) -> None:
        raise subprocess.TimeoutExpired("docker", 1)

    monkeypatch.setattr(smoke_stack.subprocess, "run", timeout)
    with pytest.raises(SmokeError) as caught:
        smoke_stack.run_command(["docker", "compose", "--env-file", "env.example", "up"], 1)
    assert caught.value.check == "command:up"


def test_AC_PLT_01_run_command_without_docker_fails_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*_: Any, **__: Any) -> None:
        raise FileNotFoundError("docker")

    monkeypatch.setattr(smoke_stack.subprocess, "run", missing)
    with pytest.raises(SmokeError) as caught:
        smoke_stack.run_command(["docker", "compose", "--env-file", "env.example", "ps"], 1)
    assert caught.value.check == "command:ps"


def test_AC_PLT_01_run_command_runs_from_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "out", "")

    monkeypatch.setattr(smoke_stack.subprocess, "run", fake_run)
    argv = ["docker", "compose", "--env-file", "env.example", "ps"]
    assert smoke_stack.run_command(argv, 5).stdout == "out"
    assert seen["cwd"] == smoke_stack.REPO_ROOT
    assert seen["timeout"] == 5


def test_AC_PLT_01_url_argument_must_be_http(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        smoke_stack.main(["--backend-url", "file:///etc/passwd"])
    assert caught.value.code == 2
    assert "--backend-url" in capsys.readouterr().err


def ci_build_steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["build"]["steps"]


def test_AC_PLT_01_smoke_is_the_last_step_of_the_build_job() -> None:
    step = ci_build_steps()[-1]
    # GIT_SHA comes from the job env: github.sha, what was built (on a PR, the merge commit).
    assert step["run"].strip() == "python3 scripts/smoke_stack.py"
    assert "continue-on-error" not in step
    assert "if" not in step


@pytest.mark.parametrize(
    "script", ["smoke_stack.py", "smoke_http.py", "smoke_leaks.py", "smoke_pages.py"]
)
def test_AC_PLT_01_smoke_uses_only_the_standard_library(script: str) -> None:
    # The `build` job installs no Python environment: it runs on the runner's python3.
    source = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import) ([a-z_]+)", source, flags=re.M))
    allowed = {
        "__future__",
        "argparse",
        "collections",
        "dataclasses",
        "http",
        "json",
        "os",
        "pathlib",
        "re",
        "smoke_http",
        "smoke_leaks",
        "smoke_pages",
        "subprocess",
        "sys",
        "time",
        "typing",
        "urllib",
        "uuid",
    }
    assert imported <= allowed


def test_AC_PLT_10_ci_override_fixes_what_the_smoke_relies_on() -> None:
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!reset", lambda *_: None)
    text = (REPO_ROOT / "infra" / "docker-compose.ci.yml").read_text(encoding="utf-8")
    services = yaml.load(text, Loader=Loader)["services"]  # noqa: S506 - a SafeLoader subclass
    for name in ("backend", "worker", "beat"):
        env = services[name]["environment"]
        # INFO: the access log the AC-PLT-10 check reads. Not left to env.example, where a change
        # for development would silence that line in the smoke.
        assert env["LOG_LEVEL"] == "INFO"
        assert env["API_THROTTLE_ANON_RATE"] == "300/min"
        assert env["TRUSTED_PROXY_COUNT"] == "0"


def test_AC_PLT_01_smoke_expects_the_services_of_the_compose_file() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    )
    assert set(smoke_stack.SERVICES) == set(compose["services"])


def test_AC_PLT_02_short_sha_length_matches_the_backend() -> None:
    views = (REPO_ROOT / "backend" / "apps" / "common" / "health" / "views.py").read_text(
        encoding="utf-8"
    )
    assert f"SHORT_SHA_LENGTH = {smoke_stack.SHORT_SHA_LENGTH}" in views


def test_AC_PLT_01_sha_is_the_full_commit_of_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", SHA)
    config = smoke_stack.load_config([])
    assert config.short_sha == SHA[:7]
