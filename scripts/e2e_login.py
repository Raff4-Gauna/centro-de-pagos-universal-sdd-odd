"""E2E of the login with the fake OIDC provider (T-IDA-31, SPEC-01, design.md §9).

Usage, against a running stack with dev or test settings and ``IDENTITY_OIDC_PROVIDER=fake``:
    python3 scripts/e2e_login.py --email ADDRESS
        [--frontend-url URL] [--provider-url URL]

It talks to the BFF the way a browser does, three browsers with a cookie jar each, and proves:

- AC-IDA-01: each login (``/api/auth/google/start`` → ``/dev-oidc/authorize`` → the callback) lands
  in the app with the session cookies set, and ``/api/me`` answers ``200`` with that email.
- AC-IDA-33: the first browser sees its three sessions (browser, OS and dates, no IP), "cerrar las
  demás" leaves only its own ``active``, and the other two get ``401`` from then on.
- AC-IDA-17: logout is a ``204`` that clears the cookies, ``/api/me`` is ``401`` after it, the
  refresh token of the ended session no longer opens one, and a second logout is ``204`` too.

**Prerequisites.** The provider only exists with ``settings.dev`` or ``settings.test`` (T-IDA-20):
the CI stack (``infra/docker-compose.ci.yml``) runs ``settings.prod`` and does not have it. The
user must exist and be active: a new email gets in only with a pending invitation (SPEC-02's
port), the script issues none, so it ends in ``not_invited``. ``infra/README.md`` ("E2E del login")
seeds the user and raises a throwaway stack.

``--frontend-url`` is the app origin, exactly ``HUB_APP_ORIGIN``: unsafe requests send it as
``Origin``. ``--provider-url`` replaces the origin of the authorization URL Django builds, for a
stack whose backend is published on a port other than the one of ``IDENTITY_FAKE_OIDC_BASE_URL``;
the path and query stay. That URL must be the fake provider's ``/dev-oidc/authorize``: anything
else, Google's included, is refused before any email is sent.

**Its own cookie jar.** The BFF's cookies are ``__Host-`` and ``Secure``; a browser keeps them on
``http://localhost``, ``http.cookiejar`` does not send them over plain HTTP. The jar here keeps
name and value, honours ``Max-Age=0`` and sends everything back to the one origin it talks to.

Nothing secret is printed: no cookie, token, ``code`` nor ``state``; a URL is shown as origin and
path. Each failure prints ``e2e failed [<step>]: <detail>``. Exit 0 ok, 1 failed, 2 invalid
arguments. Standard library only, no browser.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

HTTP_TIMEOUT_SECONDS = 15
COOKIE_ACCESS = "__Host-cpu_at"
COOKIE_REFRESH = "__Host-cpu_rt"
COOKIE_CSRF = "__Host-cpu_csrf"
COOKIE_LOGIN = "__Host-cpu_login"
SESSION_COOKIES = (COOKIE_ACCESS, COOKIE_REFRESH, COOKIE_CSRF)
START_PATH = "/api/auth/google/start"
CALLBACK_PATH = "/api/auth/google/callback"
LOGOUT_PATH = "/api/auth/logout"
ME_PATH = "/api/me/"
SESSIONS_PATH = "/api/auth/sessions/"
REVOKE_OTHERS_PATH = "/api/auth/sessions/revoke-others/"
LOGIN_PAGE_PATH = "/login"
FAKE_AUTHORIZE_PATH = "/dev-oidc/authorize"
# The contract of a session row (SessionSerializer): an IP or the raw User-Agent is a failure.
SESSION_FIELDS = frozenset({"id", "browser", "os", "created_at", "last_used_at", "is_current"})
# (label, User-Agent, browser, OS): three devices, each summarized as client_hint.py names it.
BROWSERS = (
    (
        "A",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36",
        "Chrome",
        "Windows",
    ),
    (
        "B",
        "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "Firefox",
        "Linux",
    ),
    (
        "C",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.6 Safari/605.1.15",
        "Safari",
        "macOS",
    ),
)


class E2EError(Exception):
    """A step that did not pass; ``step`` names it. ``detail`` never carries a secret."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: str

    def header(self, name: str) -> str | None:
        wanted = name.lower()
        return next((value for key, value in self.headers if key.lower() == wanted), None)

    def set_cookies(self) -> list[str]:
        return [value for key, value in self.headers if key.lower() == "set-cookie"]

    def json(self, step: str) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            raise E2EError(step, f"HTTP {self.status} without a JSON body") from None


def send(method: str, url: str, headers: dict[str, str], body: bytes | None = None) -> Response:
    """One request as it goes: no redirect followed, no proxy from the environment."""
    parts = urlsplit(url)
    connection_class = (
        http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_class(parts.netloc, timeout=HTTP_TIMEOUT_SECONDS)
    target = parts.path or "/"
    if parts.query:
        target += f"?{parts.query}"
    try:
        connection.request(method, target, body=body, headers=headers)
        reply = connection.getresponse()
        text = reply.read().decode("utf-8", errors="replace")
        return Response(reply.status, tuple(reply.getheaders()), text)
    except (OSError, http.client.HTTPException) as error:
        raise E2EError("http", f"{method} {shown(url)}: {type(error).__name__}") from None
    finally:
        connection.close()


def shown(url: str) -> str:
    """Origin and path only: a query here can carry the ``code``, the ``state`` or the email."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


@dataclass
class CookieJar:
    """Name and value of each cookie the one origin set; ``Max-Age=0`` deletes it."""

    values: dict[str, str] = field(default_factory=dict)

    def update(self, response: Response) -> None:
        for raw in response.set_cookies():
            pair, _, attributes = raw.partition(";")
            name, _, value = pair.strip().partition("=")
            expired = any(
                attribute.strip().lower() == "max-age=0" for attribute in attributes.split(";")
            )
            if expired or value == "":
                self.values.pop(name, None)
            else:
                self.values[name] = value

    def header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.values.items())


@dataclass
class Browser:
    label: str
    user_agent: str
    app_origin: str
    jar: CookieJar = field(default_factory=CookieJar)

    def request(self, method: str, url: str, *, unsafe: bool = False) -> Response:
        """``url`` absolute or a path on the app. The jar only goes to the app origin."""
        absolute = url if "://" in url else f"{self.app_origin}{url}"
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        on_app = origin_of(absolute) == self.app_origin
        if on_app and self.jar.values:
            headers["Cookie"] = self.jar.header()
        if unsafe:
            headers["Origin"] = self.app_origin
            csrf = self.jar.values.get(COOKIE_CSRF)
            if csrf:
                headers["X-CSRF-Token"] = csrf
        response = send(method, absolute, headers, b"" if unsafe else None)
        if on_app:
            self.jar.update(response)
        return response


@dataclass(frozen=True)
class Config:
    frontend_url: str
    provider_url: str | None
    email: str


def redirect_target(step: str, response: Response) -> str:
    location = response.header("location")
    if response.status != 302 or not location:
        raise E2EError(step, f"expected a 302 with Location, got HTTP {response.status}")
    return location


def login_error_of(url: str) -> str | None:
    """The allowlisted ``error`` of ``/login?error=<code>``, the only query shown."""
    parts = urlsplit(url)
    if parts.path != LOGIN_PAGE_PATH:
        return None
    match = re.search(r"(?:^|&)error=([a-z_]{1,40})(?:&|$)", parts.query)
    return match.group(1) if match else "none"


def provider_url_for(authorization_url: str, provider_url: str | None) -> str:
    parts = urlsplit(authorization_url)
    if parts.path != FAKE_AUTHORIZE_PATH:
        raise E2EError("login-start", f"not the fake provider, refused: {shown(authorization_url)}")
    if provider_url is None:
        return authorization_url
    base = urlsplit(provider_url)
    return urlunsplit((base.scheme, base.netloc, parts.path, parts.query, ""))


def login(browser: Browser, config: Config) -> None:
    """AC-IDA-01: start → fake provider → callback → the app, with the session cookies."""
    step = f"login-{browser.label}"
    start = browser.request("GET", START_PATH)
    authorization_url = redirect_target(f"{step}-start", start)
    error = login_error_of(authorization_url)
    if error is not None:
        raise E2EError(f"{step}-start", f"/login?error={error}")
    if COOKIE_LOGIN not in browser.jar.values:
        raise E2EError(f"{step}-start", f"{COOKIE_LOGIN} not set")
    target = provider_url_for(authorization_url, config.provider_url)
    form = urlencode(
        {"email": config.email, "name": f"E2E {browser.label}", "email_verified": "true"}
    )
    authorize = browser.request("GET", f"{target}&{form}")
    callback_url = redirect_target(f"{step}-authorize", authorize)
    if shown(callback_url) != f"{config.frontend_url}{CALLBACK_PATH}":
        raise E2EError(f"{step}-authorize", f"back to another place: {shown(callback_url)}")
    landing_url = redirect_target(f"{step}-callback", browser.request("GET", callback_url))
    error = login_error_of(landing_url)
    if error is not None:
        raise E2EError(f"{step}-callback", f"/login?error={error}")
    if origin_of(landing_url) != config.frontend_url:
        raise E2EError(f"{step}-callback", f"lands off the app: {shown(landing_url)}")
    missing = [name for name in SESSION_COOKIES if name not in browser.jar.values]
    if missing:
        raise E2EError(f"{step}-callback", f"session cookies not set: {missing}")
    if COOKIE_LOGIN in browser.jar.values:
        raise E2EError(f"{step}-callback", f"{COOKIE_LOGIN} not cleared")
    me = browser.request("GET", ME_PATH)
    if me.status != 200:
        raise E2EError(f"{step}-me", f"expected 200, got HTTP {me.status}")
    if me.json(f"{step}-me").get("email") != config.email.strip().lower():
        raise E2EError(f"{step}-me", "/api/me names another person")


def expect_unauthenticated(browser: Browser, step: str) -> None:
    me = browser.request("GET", ME_PATH)
    if me.status != 401:
        raise E2EError(step, f"/api/me expected 401, got HTTP {me.status}")


def list_sessions(browser: Browser, step: str) -> list[dict[str, Any]]:
    """AC-IDA-33: the rows carry browser, OS and dates, and nothing else."""
    reply = browser.request("GET", f"{SESSIONS_PATH}?page_size=200")
    if reply.status != 200:
        raise E2EError(step, f"expected 200, got HTTP {reply.status}")
    body = reply.json(step)
    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list) or body.get("next") is not None:
        raise E2EError(step, "not one page of sessions")
    for row in rows:
        if not isinstance(row, dict) or set(row) != SESSION_FIELDS:
            extra = sorted(set(row) - SESSION_FIELDS) if isinstance(row, dict) else "not an object"
            raise E2EError(step, f"a session row out of contract: {extra}")
    if sum(1 for row in rows if row["is_current"] is True) != 1:
        raise E2EError(step, "not exactly one current session")
    return rows


def check_three_sessions(browsers: Sequence[tuple[Browser, str, str]]) -> None:
    rows = list_sessions(browsers[0][0], "sessions-before")
    devices = {(row["browser"], row["os"]) for row in rows}
    for browser, name, system in browsers:
        if (name, system) not in devices:
            raise E2EError("sessions-before", f"no session of {name} on {system} ({browser.label})")
    current = next(row for row in rows if row["is_current"])
    if (current["browser"], current["os"]) != (browsers[0][1], browsers[0][2]):
        raise E2EError("sessions-before", "the current session is not this browser's")


def revoke_others(first: Browser, others: Sequence[Browser]) -> None:
    """AC-IDA-33: only the current session stays ``active``; the others are out."""
    reply = first.request("POST", REVOKE_OTHERS_PATH, unsafe=True)
    if reply.status != 204:
        raise E2EError("revoke-others", f"expected 204, got HTTP {reply.status}")
    rows = list_sessions(first, "sessions-after")
    if len(rows) != 1:
        raise E2EError("sessions-after", f"expected 1 session, got {len(rows)}")
    for other in others:
        expect_unauthenticated(other, f"revoked-{other.label}")
    expect_ok(first, "current-still-in")


def expect_ok(browser: Browser, step: str) -> None:
    me = browser.request("GET", ME_PATH)
    if me.status != 200:
        raise E2EError(step, f"/api/me expected 200, got HTTP {me.status}")


def logout(browser: Browser) -> None:
    """AC-IDA-17: ``204``, cookies cleared, the refresh token dead, a second logout ``204``."""
    old_refresh = browser.jar.values.get(COOKIE_REFRESH, "")
    reply = browser.request("POST", LOGOUT_PATH, unsafe=True)
    if reply.status != 204:
        raise E2EError("logout", f"expected 204, got HTTP {reply.status}")
    kept = [name for name in SESSION_COOKIES if name in browser.jar.values]
    if kept:
        raise E2EError("logout", f"cookies not cleared: {kept}")
    expect_unauthenticated(browser, "logout-me")
    # A copy of the refresh cookie from before the logout: the BFF refreshes with it and Django
    # refuses, so the session cannot be brought back.
    replay = Browser(f"{browser.label}-replay", browser.user_agent, browser.app_origin)
    replay.jar.values[COOKIE_REFRESH] = old_refresh
    expect_unauthenticated(replay, "logout-refresh-dead")
    again = browser.request("POST", LOGOUT_PATH, unsafe=True)
    if again.status != 204:
        raise E2EError("logout-again", f"expected 204, got HTTP {again.status}")


def run(config: Config) -> None:
    browsers = [
        (Browser(label, agent, config.frontend_url), name, system)
        for label, agent, name, system in BROWSERS
    ]
    for browser, _, _ in browsers:
        login(browser, config)
        ok(f"login-{browser.label}")
    check_three_sessions(browsers)
    ok("sessions-before")
    first = browsers[0][0]
    revoke_others(first, [browser for browser, _, _ in browsers[1:]])
    ok("revoke-others")
    logout(first)
    ok("logout")


def ok(step: str) -> None:
    print(f"e2e ok [{step}]", flush=True)


def http_origin(value: str) -> str:
    if not re.fullmatch(r"https?://[^/\s?#]+/?", value):
        raise argparse.ArgumentTypeError(f"not an http(s) origin: {value}")
    return value.rstrip("/")


def load_config(argv: Sequence[str] | None) -> Config:
    parser = argparse.ArgumentParser(description="E2E of the login with the fake OIDC provider.")
    parser.add_argument("--email", required=True, help="an active user of the stack")
    parser.add_argument("--frontend-url", type=http_origin, default="http://127.0.0.1:3000")
    parser.add_argument("--provider-url", type=http_origin, default=None)
    args = parser.parse_args(argv)
    if "@" not in args.email or any(char.isspace() for char in args.email.strip()):
        parser.error("--email is not an address")
    return Config(args.frontend_url, args.provider_url, args.email.strip())


def main(argv: Sequence[str] | None = None) -> int:
    config = load_config(argv)
    try:
        run(config)
    except E2EError as error:
        print(f"e2e failed [{error.step}]: {error.detail}", file=sys.stderr, flush=True)
        return 1
    print("e2e passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
