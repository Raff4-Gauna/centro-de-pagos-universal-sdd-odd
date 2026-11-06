"""A healthy stack in memory for ``test_smoke_stack.py``: compose commands and URLs (T-PLT-38)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from typing import Any

import smoke_stack
from smoke_http import HttpResponse, SmokeError

SHA = "abcdef0" + "1" * 33
BACKEND = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:3000"
REQUEST_ID = "7f1c2f7e-3d7b-4a57-9b1e-1f6a4f6f8a10"
SMOKE_URL = f"{FRONTEND}/api/__smoke__"
CHUNK = "/_next/static/chunks/app.js"


def json_response(status: int, body: dict[str, Any], **headers: str) -> HttpResponse:
    return HttpResponse(status, headers, json.dumps(body))


class FakeStack:
    """A healthy stack: every command and URL answers what the real one does."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.states = dict.fromkeys(smoke_stack.SERVICES, ("running", "healthy"))
        self.failing_commands: dict[str, int] = {}
        self.raising_commands: set[str] = set()
        self.redis_stopped = False
        self.backend_log = json.dumps(
            {"event": "http.request", "request_id": REQUEST_ID, "status": 404}
        )
        self.log_appears_after = 0
        self.manifest = json.dumps(
            {
                "/page": "/",
                "/(dashboard)/inicio/page": "/inicio",
                "/(dashboard)/configuracion/page": "/configuracion",
            }
        )
        page = f'<html><script src="{CHUNK}"></script></html>'
        self.routes: dict[str, HttpResponse] = {
            f"{FRONTEND}/api/health": json_response(200, {"status": "ok"}),
            SMOKE_URL: json_response(
                404,
                {"type": "about:blank", "status": 404},
                **{"content-type": "application/problem+json", "x-request-id": REQUEST_ID},
            ),
            f"{FRONTEND}/": HttpResponse(307, {"location": "/inicio"}, page),
            f"{FRONTEND}/inicio": HttpResponse(200, {}, page),
            f"{FRONTEND}/configuracion": HttpResponse(200, {}, page),
            f"{FRONTEND}{CHUNK}": HttpResponse(200, {}, "console.log(1)"),
        }

    def verb(self, argv: Sequence[str]) -> str:
        return argv[argv.index("env.example") + 1]

    def run(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        self.commands.append(argv)
        verb = self.verb(argv)
        if verb in self.raising_commands:
            raise SmokeError(f"command:{verb}", "docker timed out")
        code = self.failing_commands.get(verb, 0)
        stdout = ""
        if verb == "ps":
            stdout = "\n".join(
                json.dumps({"Service": name, "State": state, "Health": health})
                for name, (state, health) in self.states.items()
            )
        elif verb == "logs":
            stdout = self.current_log()
        elif verb == "exec":
            stdout = self.manifest
        elif verb == "stop":
            self.redis_stopped = True
        return subprocess.CompletedProcess(argv, code, stdout, "compose said no" if code else "")

    def current_log(self) -> str:
        reads = sum(self.verb(argv) == "logs" for argv in self.commands)
        return self.backend_log if reads > self.log_appears_after else ""

    def get(self, url: str) -> HttpResponse:
        if url == f"{BACKEND}/readyz":
            if self.redis_stopped:
                return self.routes.get("readyz-down") or json_response(
                    503, {"status": "unavailable"}
                )
            return self.routes.get(url) or json_response(200, {"status": "ready"})
        if url == f"{BACKEND}/healthz":
            default = json_response(200, {"status": "ok", "version": SHA[:7]})
            down = self.routes.get("healthz-down") if self.redis_stopped else None
            return down or self.routes.get(url) or default
        return self.routes[url]

    @property
    def verbs(self) -> list[str]:
        return [self.verb(argv) for argv in self.commands]
