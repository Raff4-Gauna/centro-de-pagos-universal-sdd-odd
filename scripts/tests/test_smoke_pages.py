"""AC-PLT-29 (regression, T-IDA-26): what counts as a reviewed page in ``smoke_pages.py``.

A redirect is not a page: only a 2xx is reviewed, a listed redirect is followed once and its
destination is what gets checked, and an unlisted one fails. The leak rules and the manifest:
``test_smoke_client_bundle.py``.
"""

from __future__ import annotations

import json

import pytest
import smoke_pages
from smoke_http import HttpResponse, SmokeError

FRONTEND = "http://127.0.0.1:3000"
CHUNK = "/_next/static/chunks/app.js"
PAGE = HttpResponse(200, {}, f'<html><script src="{CHUNK}"></script></html>')
QUERY = "token=abc"


def to(location: str, status: int = 307) -> HttpResponse:
    return HttpResponse(status, {"location": location}, "")


class Frontend:
    """A root that redirects to a reviewed page; each test changes one thing."""

    def __init__(self) -> None:
        self.pages = ["/", "/inicio"]
        self.responses = {
            "/": to("/inicio"),
            "/inicio": PAGE,
            CHUNK: HttpResponse(200, {}, "console.log(1)"),
        }
        self.unreachable: set[str] = set()
        self.requested: list[str] = []

    def get(self, url: str) -> HttpResponse:
        self.requested.append(url)
        path = url.removeprefix(FRONTEND)
        if path in self.unreachable:
            raise SmokeError("http", f"GET {url}: URLError")  # what smoke_http.py prints
        return self.responses[path]

    def error(self) -> str:
        with pytest.raises(SmokeError) as caught:
            smoke_pages.check_client_bundle(FRONTEND, self.pages)
        assert caught.value.check == "client-bundle"
        return caught.value.detail


@pytest.fixture
def frontend(monkeypatch: pytest.MonkeyPatch) -> Frontend:
    fake = Frontend()
    monkeypatch.setattr(smoke_pages, "http_get", fake.get)
    return fake


@pytest.fixture
def protected(monkeypatch: pytest.MonkeyPatch, frontend: Frontend) -> Frontend:
    """What T-IDA-28 brings: ``/inicio`` needs a session, ``/login`` is the destination."""
    redirects = {"/": "/login", "/inicio": "/login"}
    monkeypatch.setattr(smoke_pages, "EXPECTED_REDIRECTS", redirects)
    frontend.responses.update({"/": to("/login"), "/inicio": to("/login"), "/login": PAGE})
    return frontend


def test_AC_PLT_29_redirect_is_not_counted_as_reviewed(
    frontend: Frontend, capsys: pytest.CaptureFixture[str]
) -> None:
    smoke_pages.check_client_bundle(FRONTEND, frontend.pages)
    assert "1 pages reviewed, 1 redirected" in capsys.readouterr().out


def test_AC_PLT_29_protected_page_answering_200_fails(protected: Frontend) -> None:
    protected.responses["/inicio"] = PAGE
    assert "/inicio answered 200, expected a redirect to /login" in protected.error()


def test_AC_PLT_29_root_answering_200_fails(frontend: Frontend) -> None:
    frontend.responses["/"] = PAGE
    assert "/ answered 200" in frontend.error()


def test_AC_PLT_29_unknown_redirect_fails(frontend: Frontend) -> None:
    frontend.responses["/inicio"] = to("/otra")
    assert "/inicio answered 307: a redirect not listed" in frontend.error()


def test_AC_PLT_29_parametrized_route_uses_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_pages, "SAMPLE_URLS", {"/cobros/[id]": "/cobros/sample-1"})
    manifest = {"/page": "/", "/cobros/[id]/page": "/cobros/[id]"}
    assert smoke_pages.page_paths(json.dumps(manifest)) == ["/", "/cobros/sample-1"]


def test_AC_PLT_29_parametrized_route_without_sample_still_fails() -> None:
    manifest = {"/page": "/", "/cobros/[id]/page": "/cobros/[id]"}
    with pytest.raises(SmokeError) as caught:
        smoke_pages.page_paths(json.dumps(manifest))
    assert "/cobros/[id]" in caught.value.detail


@pytest.mark.parametrize("attribute", ["EXPECTED_REDIRECTS", "SAMPLE_URLS"])
def test_AC_PLT_29_listed_page_the_image_does_not_have_fails(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A typo in a list would otherwise leave that protected page unchecked, in silence.
    monkeypatch.setattr(smoke_pages, attribute, {"/": "/inicio", "/incio": "/login"})
    with pytest.raises(SmokeError) as caught:
        smoke_pages.page_paths(json.dumps({"/page": "/"}))
    assert "/incio" in caught.value.detail


def test_AC_PLT_29_redirect_destination_is_reviewed_once_outside_the_pages(
    protected: Frontend, capsys: pytest.CaptureFixture[str]
) -> None:
    smoke_pages.check_client_bundle(FRONTEND, protected.pages)
    assert protected.requested.count(f"{FRONTEND}/login") == 1
    assert "1 pages reviewed, 2 redirected" in capsys.readouterr().out


def test_AC_PLT_29_destination_already_in_the_pages_is_not_fetched_twice(
    frontend: Frontend,
) -> None:
    smoke_pages.check_client_bundle(FRONTEND, frontend.pages)
    assert frontend.requested.count(f"{FRONTEND}/inicio") == 1


def test_AC_PLT_29_query_of_the_destination_is_dropped_and_not_compared(
    protected: Frontend,
) -> None:
    protected.responses["/inicio"] = to("/login?return_to=/inicio")
    smoke_pages.check_client_bundle(FRONTEND, protected.pages)
    assert protected.requested.count(f"{FRONTEND}/login") == 1


def test_AC_PLT_29_absolute_location_of_the_same_origin_is_followed(frontend: Frontend) -> None:
    frontend.responses["/"] = to(f"{FRONTEND}/inicio")
    smoke_pages.check_client_bundle(FRONTEND, frontend.pages)


def test_AC_PLT_29_leak_in_the_destination_is_found(protected: Frontend) -> None:
    protected.responses["/login"] = HttpResponse(200, {}, PAGE.body + "backend:8000")
    assert "/login carries" in protected.error()


def test_AC_PLT_29_chunks_of_the_destination_are_scanned(protected: Frontend) -> None:
    protected.responses[CHUNK] = HttpResponse(200, {}, "backend:8000")
    assert f"{CHUNK} carries" in protected.error()


def test_AC_PLT_29_redirect_without_location_fails(frontend: Frontend) -> None:
    frontend.responses["/"] = HttpResponse(307, {}, "")
    assert "/ redirects without a Location" in frontend.error()


@pytest.mark.parametrize(
    "location",
    [
        "https://127.0.0.1:3000/inicio",
        "http://127.0.0.1:3001/inicio",
        "http://evil.example/inicio",
        "//evil.example/inicio",
        "http://127.0.0.1:3000@evil.example/inicio",
    ],
)
def test_AC_PLT_29_redirect_to_another_origin_fails(location: str, frontend: Frontend) -> None:
    frontend.responses["/"] = to(location)
    assert "/ redirects to another origin" in frontend.error()
    assert frontend.requested == [f"{FRONTEND}/"]


def test_AC_PLT_29_redirect_to_another_path_fails(frontend: Frontend) -> None:
    frontend.responses["/"] = to("/otra")
    assert "/ redirects to /otra, expected /inicio" in frontend.error()


@pytest.mark.parametrize("location", ["/\\evil.example", "\\\\evil.example"])
def test_AC_PLT_29_backslash_location_is_not_followed(location: str, frontend: Frontend) -> None:
    # A browser reads both as another host; here they are a path that is not the expected one.
    frontend.responses["/"] = to(location)
    assert "expected /inicio" in frontend.error()
    assert frontend.requested == [f"{FRONTEND}/"]


def test_AC_PLT_29_unreadable_location_fails(frontend: Frontend) -> None:
    frontend.responses["/"] = to("http://[broken/inicio")
    assert "/ redirects to an unreadable Location" in frontend.error()


@pytest.mark.parametrize(
    "destination",
    [
        HttpResponse(500, {}, ""),
        HttpResponse(200, {}, PAGE.body + "backend:8000"),
        to("/otra"),
        None,
    ],
    ids=["error-status", "leak", "second-hop", "unreachable"],
)
def test_AC_PLT_29_location_query_is_not_printed(
    destination: HttpResponse | None, protected: Frontend
) -> None:
    protected.responses.update({"/": to(f"/login?{QUERY}"), "/inicio": to(f"/login?{QUERY}")})
    for path in ("/login", f"/login?{QUERY}"):
        if destination is None:
            protected.unreachable.add(path)
        else:
            protected.responses[path] = destination
    with pytest.raises(SmokeError) as caught:
        smoke_pages.check_client_bundle(FRONTEND, protected.pages)
    assert QUERY not in str(caught.value)
    assert not any(QUERY in url for url in protected.requested)


def test_AC_PLT_29_query_of_an_unexpected_destination_is_not_printed(
    frontend: Frontend,
) -> None:
    frontend.responses["/"] = to(f"/otra?{QUERY}")
    assert QUERY not in frontend.error()


def test_AC_PLT_29_redirect_chain_fails_after_one_hop(protected: Frontend) -> None:
    protected.responses["/login"] = to("/otra")
    assert "/login answered 307, expected a page" in protected.error()


def test_AC_PLT_29_destination_with_an_error_fails(protected: Frontend) -> None:
    protected.responses["/login"] = HttpResponse(500, {}, "")
    assert "/login answered 500, expected a page" in protected.error()


def test_AC_PLT_29_zero_reviewed_pages_fail(frontend: Frontend) -> None:
    frontend.pages = []
    assert "no page reviewed" in frontend.error()
