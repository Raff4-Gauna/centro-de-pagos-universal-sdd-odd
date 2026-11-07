"""The pages of the running stack, as the browser gets them (AC-PLT-29, T-PLT-38, T-IDA-26).

Only a 2xx counts as a reviewed page. A redirect is scanned too, but it is no page: it must be
listed in ``EXPECTED_REDIRECTS``, stay on the same origin and be followed once, and what gets
reviewed is its destination. A listed page answering 2xx fails: without a session, that is a
protected page open to anyone. Standard library only.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urljoin, urlsplit

from smoke_http import HttpResponse, SmokeError, http_get
from smoke_leaks import leaks_in, page_leaks_in, pages_in_manifest, static_assets

CHECK = "client-bundle"
ROUTES_MANIFEST = ".next/app-path-routes-manifest.json"

# Page -> path it must redirect to without a session. The first protected page (T-IDA-28) adds
# itself here, and from then on a 200 on it fails.
EXPECTED_REDIRECTS: dict[str, str] = {"/": "/inicio"}
# Route with ``[id]`` in the manifest -> URL that renders it without a session.
SAMPLE_URLS: dict[str, str] = {}


def page_paths(manifest: str) -> list[str]:
    """The pages the image really has: a fixed list would miss the next dynamic one."""
    try:
        pages = pages_in_manifest(manifest)
    except (ValueError, AttributeError) as error:
        raise SmokeError(CHECK, f"{ROUTES_MANIFEST} is unreadable") from error
    urls = [SAMPLE_URLS.get(path, path) for path in pages]
    parametrized = [url for url in urls if "[" in url]
    if parametrized:
        raise SmokeError(CHECK, f"no URL to render {parametrized}: add it to SAMPLE_URLS")
    if not pages:
        raise SmokeError(CHECK, "no page in the manifest: nothing was checked")
    stale = sorted((set(EXPECTED_REDIRECTS) - set(urls)) | (set(SAMPLE_URLS) - set(pages)))
    if stale:
        raise SmokeError(CHECK, f"listed but not in the image: {stale}")
    return urls


def page_text(response: HttpResponse) -> str:
    return "\n".join([response.body, *response.headers.values()])


def fail_on_leaks(path: str, found: list[str]) -> None:
    if found:
        raise SmokeError(CHECK, f"{path} carries {', '.join(sorted(set(found)))}")


def is_page(response: HttpResponse) -> bool:
    return 200 <= response.status < 300


def is_redirect(response: HttpResponse) -> bool:
    return 300 <= response.status < 400


def redirect_target(frontend_url: str, path: str, response: HttpResponse) -> str:
    """The path to follow, without the query of the ``Location``.

    The query is not compared, ``return_to`` varies by page, and it is not requested: what is
    requested reaches the log when it fails, here and in ``http_get``.
    """
    expected = EXPECTED_REDIRECTS.get(path)
    if expected is None:
        detail = f"{path} answered {response.status}: a redirect not listed in EXPECTED_REDIRECTS"
        raise SmokeError(CHECK, detail)
    location = response.headers.get("location")
    if not location:
        raise SmokeError(CHECK, f"{path} redirects without a Location")
    try:
        target = urlsplit(urljoin(f"{frontend_url}{path}", location))
    except ValueError as error:
        raise SmokeError(CHECK, f"{path} redirects to an unreadable Location") from error
    origin = urlsplit(frontend_url)
    if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
        raise SmokeError(CHECK, f"{path} redirects to another origin, expected {expected}")
    if target.path != expected:
        raise SmokeError(CHECK, f"{path} redirects to {target.path}, expected {expected}")
    return target.path


def check_client_bundle(frontend_url: str, pages: Sequence[str]) -> None:
    """Every page, every destination and every asset they name, as the browser gets them."""
    assets: set[str] = set()
    reviewed: set[str] = set()
    targets: dict[str, str] = {}
    rendered_on_request = 0

    def fetched(path: str) -> HttpResponse:
        response = http_get(f"{frontend_url}{path}")
        text = page_text(response)
        fail_on_leaks(path, page_leaks_in(text))
        assets.update(static_assets(text))
        return response

    for path in pages:
        response = fetched(path)
        rendered_on_request += "x-nextjs-prerender" not in response.headers
        if is_redirect(response):
            targets[path] = redirect_target(frontend_url, path, response)
        elif not is_page(response):
            raise SmokeError(CHECK, f"{path} answered {response.status}, expected a page")
        elif path in EXPECTED_REDIRECTS:
            detail = f"expected a redirect to {EXPECTED_REDIRECTS[path]}"
            raise SmokeError(CHECK, f"{path} answered {response.status}, {detail}")
        else:
            reviewed.add(path)
    for target in sorted(set(targets.values()) - reviewed):
        response = fetched(target)
        if not is_page(response):
            raise SmokeError(CHECK, f"{target} answered {response.status}, expected a page")
        reviewed.add(target)
    if not reviewed:
        raise SmokeError(CHECK, "no page reviewed: every answer was a redirect or nothing")
    if not any(asset.endswith(".js") for asset in assets):
        raise SmokeError(CHECK, "no client chunk in the pages: nothing was checked")
    for path in sorted(assets):
        response = http_get(f"{frontend_url}{path}")
        if response.status != 200:
            raise SmokeError(CHECK, f"{path} answered {response.status}, expected 200")
        fail_on_leaks(path, leaks_in(page_text(response)))
    print(
        f"ok: client bundle clean over HTTP: {len(reviewed)} pages reviewed, "
        f"{len(targets)} redirected ({rendered_on_request} rendered on request), "
        f"{len(assets)} assets"
    )
