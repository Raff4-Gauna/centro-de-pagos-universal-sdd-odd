"""Minimal read-only GitHub REST client (T-PLT-07, used by ``check_zona_roja.py``).

Stdlib only (``urllib``). Fails closed: an HTTP status other than 200, a redirect, a transport
error, a body that is not JSON, a payload of the wrong shape, or a pagination ``Link`` that leaves
the API host all raise ``GitHubAPIError``. The token is only sent to ``api_url`` and never appears
in an error message.

The transport is injectable so tests run without network (``Transport``).
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT_SECONDS = 30.0
PER_PAGE = 100
MAX_PAGES = 100

_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


class GitHubAPIError(Exception):
    """The API could not be read, or answered something unexpected."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        return next((v for k, v in self.headers.items() if k.lower() == wanted), None)


# (url, headers, timeout) -> Response. Raises OSError & co. on transport errors.
Transport = Callable[[str, Mapping[str, str], float], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would follow a redirect and forward the Authorization header to any host."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float) -> Response:
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers=dict(headers), method="GET")  # noqa: S310 - https only, checked by GitHubClient
    try:
        with opener.open(request, timeout=timeout) as answer:
            return Response(answer.status, dict(answer.headers.items()), answer.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, dict(exc.headers.items()) if exc.headers else {}, b"")


def next_link(header: str | None) -> str | None:
    """The ``rel="next"`` URL of a ``Link`` header, if any."""
    if not header:
        return None
    for part in header.split(","):
        match = _NEXT_LINK_RE.search(part)
        if match:
            return match.group(1).strip()
    return None


def _origin(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme, parsed.netloc.lower()


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        api_url: str = DEFAULT_API_URL,
        transport: Transport = urllib_transport,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        if not token:
            raise GitHubAPIError("no GitHub token")
        if _origin(api_url)[0] != "https" or not _origin(api_url)[1]:
            raise GitHubAPIError(f"API URL must be https: {api_url!r}")
        self._token = token
        self._api_url = api_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _url(self, path: str, params: Mapping[str, str | int] | None = None) -> str:
        if not path.startswith("/") or path.startswith("//"):
            raise GitHubAPIError(f"API path must start with a single '/': {path!r}")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        return f"{self._api_url}{path}{query}"

    def _get(self, url: str) -> tuple[Any, Response]:
        if _origin(url) != _origin(self._api_url):
            raise GitHubAPIError("refusing to send the token outside the API host")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "centro-pagos-zona-roja-check",
        }
        where = urllib.parse.urlsplit(url).path
        try:
            response = self._transport(url, headers, self._timeout)
        # URLError and TimeoutError are OSErrors; IncompleteRead & co. are HTTPExceptions.
        except (OSError, http.client.HTTPException) as exc:
            raise GitHubAPIError(f"GET {where} failed: {exc.__class__.__name__}") from exc
        if response.status != 200:
            raise GitHubAPIError(f"GET {where} answered HTTP {response.status}")
        try:
            return json.loads(response.body.decode("utf-8")), response
        except (UnicodeDecodeError, ValueError) as exc:
            raise GitHubAPIError(f"GET {where} did not answer JSON") from exc

    def get_object(self, path: str) -> dict[str, Any]:
        """GET one JSON object."""
        payload, _ = self._get(self._url(path))
        if not isinstance(payload, dict):
            raise GitHubAPIError(f"GET {path}: expected a JSON object")
        return payload

    def get_list(self, path: str, *, max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
        """GET a paginated list of JSON objects, following ``Link: rel="next"``."""
        url: str | None = self._url(path, {"per_page": PER_PAGE})
        items: list[dict[str, Any]] = []
        pages = 0
        while url is not None:
            pages += 1
            if pages > max_pages:
                raise GitHubAPIError(f"GET {path}: more than {max_pages} pages")
            payload, response = self._get(url)
            if not isinstance(payload, list) or not all(isinstance(i, dict) for i in payload):
                raise GitHubAPIError(f"GET {path}: expected a JSON list of objects")
            items.extend(payload)
            url = next_link(response.header("Link"))
        return items
