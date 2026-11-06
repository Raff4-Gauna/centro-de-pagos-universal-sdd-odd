"""``scripts/github_api.py``: minimal GitHub REST client, tested with a fake transport (T-PLT-07).

No network: every test injects the transport. Any error or unexpected answer must raise
``GitHubAPIError`` (the ``zona-roja`` check then fails as "not verified", AC-PLT-32).
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from typing import Any

import pytest
from github_api import GitHubAPIError, GitHubClient, Response, next_link, urllib_transport

API = "https://api.github.test"
TOKEN = "fake-token-for-tests"  # noqa: S105 - not a secret, never sent anywhere


class FakeTransport:
    """Answers by URL from a dict; records each request (url, headers)."""

    def __init__(self, answers: Mapping[str, Response | Exception]) -> None:
        self.answers = dict(answers)
        self.requests: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.requests.append((url, dict(headers)))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(payload: Any, link: str | None = None) -> Response:
    headers = {"Link": link} if link else {}
    return Response(200, headers, json.dumps(payload).encode())


def client(answers: Mapping[str, Response | Exception]) -> tuple[GitHubClient, FakeTransport]:
    transport = FakeTransport(answers)
    return GitHubClient(TOKEN, api_url=API, transport=transport), transport


def test_github_api_get_object_sends_token_and_api_headers() -> None:
    api, transport = client({f"{API}/repos/o/r/pulls/7": ok({"number": 7})})
    assert api.get_object("/repos/o/r/pulls/7") == {"number": 7}
    _, headers = transport.requests[0]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Accept"] == "application/vnd.github+json"
    assert "X-GitHub-Api-Version" in headers


def test_github_api_paginates_link_header() -> None:
    first = f"{API}/repos/o/r/pulls/7/files?per_page=100"
    second = f"{API}/repositories/1/pulls/7/files?per_page=100&page=2"
    third = f"{API}/repositories/1/pulls/7/files?per_page=100&page=3"
    api, transport = client(
        {
            first: ok([{"n": 1}, {"n": 2}], f'<{second}>; rel="next", <{third}>; rel="last"'),
            second: ok([{"n": 3}], f'<{first}>; rel="prev", <{third}>; rel="next"'),
            third: ok([{"n": 4}], f'<{first}>; rel="first", <{second}>; rel="prev"'),
        }
    )
    items = api.get_list("/repos/o/r/pulls/7/files")
    assert [item["n"] for item in items] == [1, 2, 3, 4]
    assert [url for url, _ in transport.requests] == [first, second, third]


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "not a list"},
        [{"n": 1}, "not an object"],
        "text",
        None,
    ],
)
def test_github_api_unexpected_payload_raises(payload: Any) -> None:
    api, _ = client({f"{API}/x?per_page=100": ok(payload)})
    with pytest.raises(GitHubAPIError):
        api.get_list("/x")


@pytest.mark.parametrize("payload", [[], "text", 3, None])
def test_github_api_object_endpoint_with_non_object_raises(payload: Any) -> None:
    api, _ = client({f"{API}/x": ok(payload)})
    with pytest.raises(GitHubAPIError):
        api.get_object("/x")


@pytest.mark.parametrize(
    "answer",
    [
        Response(404, {}, b'{"message": "Not Found"}'),
        Response(500, {}, b"oops"),
        Response(301, {"Location": "https://evil.test/"}, b""),
        Response(200, {}, b"not json"),
        Response(200, {}, b"\xff\xfe"),
        OSError("connection reset"),
        TimeoutError("timed out"),
    ],
)
def test_github_api_http_or_transport_error_raises(answer: Response | Exception) -> None:
    api, _ = client({f"{API}/x": answer})
    with pytest.raises(GitHubAPIError) as excinfo:
        api.get_object("/x")
    assert TOKEN not in str(excinfo.value)


def test_github_api_next_link_to_another_host_raises() -> None:
    """The token is never sent outside the API host, even if a Link header points elsewhere."""
    first = f"{API}/x?per_page=100"
    api, transport = client({first: ok([], '<https://evil.test/x?page=2>; rel="next"')})
    with pytest.raises(GitHubAPIError):
        api.get_list("/x")
    assert len(transport.requests) == 1


def test_github_api_page_limit_raises() -> None:
    url = f"{API}/x?per_page=100"
    api, _ = client({url: ok([{"n": 1}], f'<{url}>; rel="next"')})
    with pytest.raises(GitHubAPIError):
        api.get_list("/x", max_pages=3)


def test_github_api_path_must_be_absolute_and_url_https() -> None:
    api, _ = client({})
    with pytest.raises(GitHubAPIError):
        api.get_object("https://evil.test/x")
    with pytest.raises(GitHubAPIError):
        GitHubClient(TOKEN, api_url="http://api.github.test", transport=FakeTransport({}))
    with pytest.raises(GitHubAPIError):
        GitHubClient("", api_url=API, transport=FakeTransport({}))


def test_github_api_next_link_parser() -> None:
    assert next_link(None) is None
    assert next_link('<https://a.test/x?page=3>; rel="last"') is None
    header = '<https://a.test/x?page=2>; rel="next", <https://a.test/x?page=3>; rel="last"'
    assert next_link(header) == "https://a.test/x?page=2"


class FakeAnswer:
    status = 200
    headers = Message()

    def __enter__(self) -> FakeAnswer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


class FakeOpener:
    def __init__(self, result: FakeAnswer | urllib.error.HTTPError) -> None:
        self.result = result
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, timeout: float) -> FakeAnswer:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def patch_opener(monkeypatch: pytest.MonkeyPatch, opener: FakeOpener) -> list[object]:
    handlers: list[object] = []

    def build(*args: object) -> FakeOpener:
        handlers.extend(args)
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", build)
    return handlers


def test_github_api_urllib_transport_gets_with_headers_and_refuses_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = FakeOpener(FakeAnswer())
    handlers = patch_opener(monkeypatch, opener)
    answer = urllib_transport(f"{API}/x", {"Authorization": "Bearer t"}, 1.0)
    assert (answer.status, answer.body) == (200, b"{}")
    assert opener.requests[0].get_method() == "GET"
    assert opener.requests[0].get_header("Authorization") == "Bearer t"
    redirects = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert len(redirects) == 1
    # A None here makes urllib raise HTTPError instead of following the redirect.
    assert redirects[0].redirect_request(None, None, 302, "", {}, "") is None  # type: ignore[arg-type]


def test_github_api_urllib_transport_turns_http_errors_into_a_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = urllib.error.HTTPError(f"{API}/x", 302, "Found", Message(), io.BytesIO())
    patch_opener(monkeypatch, FakeOpener(error))
    api = GitHubClient(TOKEN, api_url=API, transport=urllib_transport)
    with pytest.raises(GitHubAPIError, match="HTTP 302"):
        api.get_object("/x")
