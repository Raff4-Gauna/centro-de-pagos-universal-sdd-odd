"""The error and the HTTP client of ``smoke_stack.py`` (T-PLT-38). Standard library only."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

HTTP_TIMEOUT_SECONDS = 10
USER_AGENT = "hub-smoke"


class SmokeError(Exception):
    """A check that did not pass; ``check`` names it, or the service."""

    def __init__(self, check: str, detail: str) -> None:
        super().__init__(f"{check}: {detail}")
        self.check = check
        self.detail = detail


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


# No proxy from the environment: every URL here is the loopback of this machine.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def http_get(url: str) -> HttpResponse:
    """The response as it came, error statuses and redirects included."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - http(s) only
    try:
        try:
            with _OPENER.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return _read(response.status, response)
        except urllib.error.HTTPError as error:
            with error:
                return _read(error.code, error)
    except (OSError, http.client.HTTPException) as error:
        raise SmokeError("http", f"GET {url}: {type(error).__name__}") from error


def _read(status: int, response: Any) -> HttpResponse:
    headers = {name.lower(): value for name, value in response.headers.items()}
    return HttpResponse(status, headers, response.read().decode("utf-8", errors="replace"))
