"""AC-PLT-29 in the running stack (T-PLT-38): what the browser gets carries nothing server-only.

``smoke_pages.check_client_bundle`` and the pages it takes from the image, over a fake frontend;
the rules are compared against the frontend files they mirror. What counts as a reviewed page:
``test_smoke_pages.py``.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import smoke_leaks
import smoke_pages
import smoke_stack
from smoke_http import HttpResponse, SmokeError

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = "abcdef0" + "1" * 33
FRONTEND = "http://127.0.0.1:3000"
CHUNK = "/_next/static/chunks/app.js"
PAGES = ("/", "/inicio", "/configuracion")
PAGE = f'<html><script src="{CHUNK}"></script></html>'


class FakeFrontend:
    """The pages and one chunk; ``smoke_pages.check_client_bundle`` needs nothing else."""

    def __init__(self) -> None:
        self.responses = {
            f"{FRONTEND}/": HttpResponse(307, {"location": "/inicio"}, ""),
            f"{FRONTEND}/inicio": HttpResponse(200, {}, PAGE),
            f"{FRONTEND}/configuracion": HttpResponse(200, {}, PAGE),
            f"{FRONTEND}{CHUNK}": HttpResponse(200, {}, "console.log(1)"),
        }

    def get(self, url: str) -> HttpResponse:
        return self.responses[url]


@pytest.fixture
def frontend(monkeypatch: pytest.MonkeyPatch) -> FakeFrontend:
    fake = FakeFrontend()
    monkeypatch.setattr(smoke_pages, "http_get", fake.get)
    return fake


def bundle_error() -> SmokeError:
    with pytest.raises(SmokeError) as caught:
        smoke_pages.check_client_bundle(FRONTEND, PAGES)
    assert caught.value.check == "client-bundle"
    return caught.value


def test_AC_PLT_29_clean_pages_and_chunks_pass(frontend: FakeFrontend) -> None:
    smoke_pages.check_client_bundle(FRONTEND, PAGES)


@pytest.mark.parametrize(
    "leak",
    [
        "http://backend:8000",
        "http%3A%2F%2Fbackend%3A8000",
        "HTTP%3a%2f%2fBACKEND%3a8000",
        "backend:8000",
        "bundle-sentinel-backend-internal-url.invalid",
        "BACKEND_INTERNAL_URL",
        "process.env.DJANGO_SECRET_KEY",
        'env["REDIS_URL"]',
    ],
)
@pytest.mark.parametrize("where", ["/inicio", "/configuracion", CHUNK])
def test_AC_PLT_29_smoke_finds_a_server_only_value_in_what_the_browser_gets(
    leak: str, where: str, frontend: FakeFrontend
) -> None:
    url = f"{FRONTEND}{where}"
    frontend.responses[url] = HttpResponse(200, {}, frontend.responses[url].body + leak)
    assert where in bundle_error().detail


@pytest.mark.parametrize(
    "leak",
    [
        "http://backend:8000",
        "http://backend/",
        "<p>backend</p>",
        "Host: BACKEND",
        "BACKEND_INTERNAL_URL",
    ],
)
def test_AC_PLT_29_smoke_rejects_url_hostname_and_name_in_a_dynamic_page(
    leak: str, frontend: FakeFrontend
) -> None:
    # Rendered on request: no x-nextjs-prerender, and no build ever saw this text.
    url = f"{FRONTEND}/dinamica"
    frontend.responses[url] = HttpResponse(200, {}, PAGE + leak)
    with pytest.raises(SmokeError) as caught:
        smoke_pages.check_client_bundle(FRONTEND, [*PAGES, "/dinamica"])
    assert "/dinamica carries" in caught.value.detail


def test_AC_PLT_29_clean_dynamic_page_passes_and_is_counted(
    frontend: FakeFrontend, capsys: pytest.CaptureFixture[str]
) -> None:
    prerendered = HttpResponse(200, {"x-nextjs-prerender": "1"}, PAGE)
    frontend.responses[f"{FRONTEND}/inicio"] = prerendered
    frontend.responses[f"{FRONTEND}/configuracion"] = prerendered
    redirect = {"x-nextjs-prerender": "1", "location": "/inicio"}
    frontend.responses[f"{FRONTEND}/"] = HttpResponse(307, redirect, "")
    frontend.responses[f"{FRONTEND}/dinamica"] = HttpResponse(200, {}, PAGE + "<p>Hola</p>")
    smoke_pages.check_client_bundle(FRONTEND, [*PAGES, "/dinamica"])
    assert "(1 rendered on request)" in capsys.readouterr().out


def test_AC_PLT_29_hostname_alone_in_a_chunk_is_a_word_but_in_a_url_is_a_leak(
    frontend: FakeFrontend,
) -> None:
    frontend.responses[f"{FRONTEND}{CHUNK}"] = HttpResponse(200, {}, "//backend/x")
    assert CHUNK in bundle_error().detail


def test_AC_PLT_29_pages_come_from_the_manifest_of_the_image() -> None:
    manifest = json.dumps(
        {
            "/page": "/",
            "/(dashboard)/inicio/page": "/inicio",
            "/_not-found/page": "/_not-found",
            "/_global-error/page": "/_global-error",
            "/api/[...path]/route": "/api/[...path]",
            "/api/health/route": "/api/health",
        }
    )
    assert smoke_leaks.pages_in_manifest(manifest) == ["/", "/inicio"]


@pytest.mark.parametrize(
    ("code", "stdout", "detail"),
    [
        (1, "", "unreadable"),
        (0, "not json", "unreadable"),
        (0, "[]", "unreadable"),
        (0, "{}", "no page"),
        (0, '{"/x/[id]/page": "/x/[id]"}', "/x/[id]"),
    ],
)
def test_AC_PLT_29_manifest_that_lists_no_renderable_page_fails_closed(
    code: int, stdout: str, detail: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, code, stdout, "")

    monkeypatch.setattr(smoke_stack, "run_command", run)
    config = smoke_stack.Config(SHA, "http://b", FRONTEND, ())
    with pytest.raises(SmokeError) as caught:
        smoke_pages.page_paths(smoke_stack.read_manifest(config))
    assert detail in caught.value.detail


def test_AC_PLT_29_smoke_scans_the_redirect_of_the_root(frontend: FakeFrontend) -> None:
    frontend.responses[f"{FRONTEND}/"] = HttpResponse(307, {"location": "http://backend:8000/"}, "")
    assert "/ " in bundle_error().detail


def test_AC_PLT_29_finding_names_the_rule_not_the_variable_value(frontend: FakeFrontend) -> None:
    frontend.responses[f"{FRONTEND}/inicio"] = HttpResponse(200, {}, PAGE + "env.SOME_TOKEN")
    detail = bundle_error().detail
    assert "non-public env reference" in detail


@pytest.mark.parametrize(
    "text",
    ["env.NODE_ENV", "env.NEXT_PUBLIC_API", 'env["NEXT_PUBLIC_API"]', "env.lower", "backend"],
)
def test_AC_PLT_29_public_names_pass(text: str, frontend: FakeFrontend) -> None:
    frontend.responses[f"{FRONTEND}{CHUNK}"] = HttpResponse(200, {}, text)
    smoke_pages.check_client_bundle(FRONTEND, PAGES)


def test_AC_PLT_29_page_without_chunks_proves_nothing(frontend: FakeFrontend) -> None:
    for page in ("/inicio", "/configuracion"):
        frontend.responses[f"{FRONTEND}{page}"] = HttpResponse(200, {}, "<html></html>")
    assert "no client chunk" in bundle_error().detail


@pytest.mark.parametrize("path", ["/inicio", "/configuracion", CHUNK])
def test_AC_PLT_29_page_or_chunk_with_another_status_fails(
    path: str, frontend: FakeFrontend
) -> None:
    frontend.responses[f"{FRONTEND}{path}"] = HttpResponse(500, {}, PAGE)
    assert "500" in bundle_error().detail


def test_AC_PLT_29_chunks_listed_in_the_link_header_are_scanned(frontend: FakeFrontend) -> None:
    other = "/_next/static/chunks/other.js"
    headers = {"link": f'<{other}>; rel="preload"; as="script"'}
    frontend.responses[f"{FRONTEND}/inicio"] = HttpResponse(200, headers, PAGE)
    frontend.responses[f"{FRONTEND}{other}"] = HttpResponse(200, {}, "backend:8000")
    assert other in bundle_error().detail


def test_AC_PLT_29_sentinel_and_variables_match_the_frontend() -> None:
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert f"BACKEND_INTERNAL_URL=http://{smoke_leaks.BUNDLE_SENTINEL_HOST}:8000" in dockerfile
    check = (REPO_ROOT / "frontend" / "scripts" / "check-client-bundle.ts").read_text(
        encoding="utf-8"
    )
    variables = re.search(r"SERVER_ONLY_VARIABLES[^=]*= \[([^\]]*)\]", check)
    assert variables is not None
    assert re.findall(r'"([A-Z_]+)"', variables.group(1)) == list(smoke_leaks.SERVER_ONLY_VARIABLES)


def test_AC_PLT_29_env_reference_rule_matches_the_bundle_check() -> None:
    check = (REPO_ROOT / "frontend" / "scripts" / "check-client-bundle.ts").read_text(
        encoding="utf-8"
    )
    assert f"/{smoke_leaks.ENV_REFERENCE.pattern}/g" in check
