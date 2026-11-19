"""AC-IDA-01/17/33 (T-IDA-31): the steps of ``scripts/e2e_login.py``, against simulated responses.

HTTP is replaced by ``FakeHub``: the BFF, Django and the fake OIDC provider in a few dicts, a
healthy stack each test breaks in one way. The point is that each step reads the redirects and
cookies the way a browser would, fails when the stack misbehaves, names the step and never prints
a token, a ``code`` nor a ``state``. The run against a real stack is recorded in
``specs/01-identity-access/verification.md``.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

import e2e_login
import pytest
from e2e_login import Response

APP = "http://127.0.0.1:3100"
PROVIDER = "http://localhost:8000"
PROVIDER_PUBLISHED = "http://127.0.0.1:8100"
EMAIL = "e2e@example.test"
LEAK_MARK = "zz9mark"


@dataclass
class Session:
    id: str
    user_agent: str
    access: str
    refresh: str
    active: bool = True


@dataclass
class FakeHub:
    """The BFF on ``APP`` and the provider on ``PROVIDER``; tokens carry ``LEAK_MARK``."""

    authorize_path: str = "/dev-oidc/authorize"
    callback_error: str | None = None
    leak_ip: bool = False
    revoke_others_works: bool = True
    logout_clears: bool = True
    logout_revokes: bool = True
    sessions: list[Session] = field(default_factory=list)
    requests: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    counter: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    def send(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> Response:
        self.requests.append((method, url, headers))
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        if origin != APP:
            assert parts.path == "/dev-oidc/authorize", url
            assert "Cookie" not in headers, "the jar leaked to the provider"
            return self.authorize(query)
        cookies = dict(
            pair.strip().split("=", 1)
            for pair in headers.get("Cookie", "").split(";")
            if "=" in pair
        )
        route = (method, parts.path)
        if route == ("GET", "/api/auth/google/start"):
            return self.start()
        if route == ("GET", "/api/auth/google/callback"):
            return self.callback(query, cookies, headers["User-Agent"])
        session = self.session_of(cookies)
        if route == ("GET", "/api/me/"):
            return self.me(session, cookies)
        if route == ("GET", "/api/auth/sessions/"):
            return self.list(session)
        if route == ("POST", "/api/auth/sessions/revoke-others/"):
            return self.revoke_others(session, headers, cookies)
        if route == ("POST", "/api/auth/logout"):
            return self.logout(session, headers, cookies)
        raise AssertionError(f"unexpected {method} {url}")

    def start(self) -> Response:
        n = next(self.counter)
        query = urlencode({"client_id": "fake", "state": f"state-{LEAK_MARK}-{n}"})
        location = f"{PROVIDER}{self.authorize_path}?{query}"
        return redirect(location, [f"__Host-cpu_login=bind-{LEAK_MARK}; Max-Age=600; Path=/"])

    def authorize(self, query: dict[str, str]) -> Response:
        assert query["email"] == EMAIL
        assert query["email_verified"] == "true"
        callback = urlencode({"code": f"code-{LEAK_MARK}", "state": query["state"]})
        return redirect(f"{APP}/api/auth/google/callback?{callback}")

    def callback(self, query: dict[str, str], cookies: dict[str, str], agent: str) -> Response:
        assert query["state"].startswith(f"state-{LEAK_MARK}")
        assert cookies.get("__Host-cpu_login") == f"bind-{LEAK_MARK}"
        cleared = ["__Host-cpu_login=; Max-Age=0; Path=/"]
        if self.callback_error:
            return redirect(f"{APP}/login?error={self.callback_error}", cleared)
        n = next(self.counter)
        session = Session(f"sid-{n}", agent, f"at-{LEAK_MARK}-{n}", f"rt-{LEAK_MARK}-{n}")
        self.sessions.append(session)
        set_cookies = [
            f"__Host-cpu_at={session.access}; Max-Age=840; Path=/; Secure; HttpOnly",
            f"__Host-cpu_rt={session.refresh}; Max-Age=2592000; Path=/; Secure; HttpOnly",
            f"__Host-cpu_csrf=csrf-{LEAK_MARK}-{n}; Max-Age=2592000; Path=/; Secure",
            *cleared,
        ]
        return redirect(f"{APP}/inicio", set_cookies)

    def session_of(self, cookies: dict[str, str]) -> Session | None:
        for session in self.sessions:
            if cookies.get("__Host-cpu_at") == session.access or (
                "__Host-cpu_at" not in cookies and cookies.get("__Host-cpu_rt") == session.refresh
            ):
                return session if session.active else None
        return None

    def me(self, session: Session | None, cookies: dict[str, str]) -> Response:
        if session is None:
            ended = ["__Host-cpu_at=; Max-Age=0", "__Host-cpu_rt=; Max-Age=0"] if cookies else []
            return reply(401, '{"code": "session_revoked"}', ended)
        return reply(200, f'{{"email": "{EMAIL}", "memberships": []}}')

    def list(self, session: Session | None) -> Response:
        assert session is not None
        rows = []
        for other in (s for s in self.sessions if s.active):
            browser, system = next(
                (name, os) for _, agent, name, os in e2e_login.BROWSERS if agent == other.user_agent
            )
            row = {
                "id": other.id,
                "browser": browser,
                "os": system,
                "created_at": "2026-11-19T10:00:00Z",
                "last_used_at": "2026-11-19T10:00:00Z",
                "is_current": other is session,
            }
            if self.leak_ip:
                row["ip"] = "10.0.0.1"
            rows.append(row)
        body = {"count": len(rows), "next": None, "previous": None, "results": rows}
        return reply(200, json.dumps(body))

    def revoke_others(
        self, session: Session | None, headers: dict[str, str], cookies: dict[str, str]
    ) -> Response:
        assert session is not None
        assert_csrf(headers, cookies)
        if self.revoke_others_works:
            for other in self.sessions:
                other.active = other.active and other is session
        return reply(204, "")

    def logout(
        self, session: Session | None, headers: dict[str, str], cookies: dict[str, str]
    ) -> Response:
        assert headers.get("Origin") == APP
        if "__Host-cpu_rt" in cookies:
            assert_csrf(headers, cookies)
        if session is not None and self.logout_revokes:
            session.active = False
        names = ("__Host-cpu_at", "__Host-cpu_rt", "__Host-cpu_csrf", "__Host-cpu_org")
        cleared = [f"{name}=; Max-Age=0; Path=/; Secure" for name in names]
        return reply(204, "", cleared if self.logout_clears else [])


def assert_csrf(headers: dict[str, str], cookies: dict[str, str]) -> None:
    assert headers.get("Origin") == APP, "an unsafe request without the app Origin"
    assert headers.get("X-CSRF-Token") == cookies.get("__Host-cpu_csrf"), "no double submit"


def reply(status: int, body: str, set_cookies: list[str] | None = None) -> Response:
    headers = [("Content-Type", "application/json")]
    headers += [("Set-Cookie", value) for value in set_cookies or []]
    return Response(status, tuple(headers), body)


def redirect(location: str, set_cookies: list[str] | None = None) -> Response:
    headers = [("Location", location)] + [("Set-Cookie", value) for value in set_cookies or []]
    return Response(302, tuple(headers), "")


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> FakeHub:
    fake = FakeHub()
    monkeypatch.setattr(e2e_login, "send", fake.send)
    return fake


def run_e2e(capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
    code = e2e_login.main(["--email", EMAIL, "--frontend-url", APP, *extra])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert LEAK_MARK not in output, "a token, code, state or binding was printed"
    return code, output


def assert_fails(capsys: pytest.CaptureFixture[str], step: str, *details: str) -> str:
    code, output = run_e2e(capsys)
    assert code == 1
    assert f"e2e failed [{step}]" in output
    for detail in details:
        assert detail in output
    return output


def test_AC_IDA_01_e2e_flow_parses_redirects(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    assert output.splitlines()[-1] == "e2e passed"
    for label in ("A", "B", "C"):
        assert f"e2e ok [login-{label}]" in output
    assert len(hub.sessions) == 3
    authorize_calls = [url for _, url, _ in hub.requests if "/dev-oidc/" in url]
    assert len(authorize_calls) == 3
    assert all(url.startswith(f"{PROVIDER}/dev-oidc/authorize?") for url in authorize_calls)


def test_AC_IDA_01_provider_url_replaces_only_the_origin(
    hub: FakeHub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    original = hub.send

    def published(
        method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> Response:
        if url.startswith(PROVIDER_PUBLISHED):
            seen.append(url)
            url = PROVIDER + url.removeprefix(PROVIDER_PUBLISHED)
        return original(method, url, headers, body)

    monkeypatch.setattr(e2e_login, "send", published)
    code, _ = run_e2e(capsys, "--provider-url", PROVIDER_PUBLISHED)

    assert code == 0
    assert len(seen) == 3
    assert all(
        f"{PROVIDER_PUBLISHED}/dev-oidc/authorize?client_id=fake&state=" in url for url in seen
    )


def test_AC_IDA_01_refuses_a_provider_that_is_not_the_fake_one(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.authorize_path = "/o/oauth2/v2/auth"

    assert_fails(capsys, "login-start", "not the fake provider", f"{PROVIDER}/o/oauth2/v2/auth")
    assert not any("/dev-oidc/" in url or "oauth2" in url for _, url, _ in hub.requests)


def test_AC_IDA_01_a_refused_login_names_its_error_code(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.callback_error = "not_invited"

    assert_fails(capsys, "login-A-callback", "/login?error=not_invited")


def test_AC_IDA_01_jar_follows_max_age_zero_and_stays_on_the_app() -> None:
    jar = e2e_login.CookieJar()
    jar.update(redirect(APP, ["a=1; Path=/", "b=2; Max-Age=60", "c=3"]))
    jar.update(redirect(APP, ["a=; Max-Age=0; Path=/", "b=22; Max-Age=60", "c=x; max-age=0"]))

    assert jar.values == {"b": "22"}
    assert jar.header() == "b=22"


def test_AC_IDA_33_e2e_revoke_others(hub: FakeHub, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    assert "e2e ok [sessions-before]" in output
    assert "e2e ok [revoke-others]" in output
    assert [session.active for session in hub.sessions] == [False, False, False]  # A logged out
    revoke = [headers for method, url, headers in hub.requests if url.endswith("revoke-others/")]
    assert len(revoke) == 1
    assert revoke[0]["Origin"] == APP
    assert revoke[0]["X-CSRF-Token"].startswith(f"csrf-{LEAK_MARK}")


def test_AC_IDA_33_other_sessions_still_active_fail(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.revoke_others_works = False

    assert_fails(capsys, "sessions-after", "expected 1 session, got 3")


def test_AC_IDA_33_a_session_row_with_an_ip_fails(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.leak_ip = True

    assert_fails(capsys, "sessions-before", "out of contract", "'ip'")


def test_AC_IDA_17_e2e_logout_step(hub: FakeHub, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    assert "e2e ok [logout]" in output
    logouts = [headers for method, url, headers in hub.requests if url.endswith("/api/auth/logout")]
    assert len(logouts) == 2
    assert "X-CSRF-Token" in logouts[0]
    assert "Cookie" not in logouts[1]
    assert "X-CSRF-Token" not in logouts[1]
    replay = [
        headers.get("Cookie", "")
        for _, url, headers in hub.requests
        if url.endswith("/api/me/") and headers.get("Cookie", "").startswith("__Host-cpu_rt=")
    ]
    assert replay == [f"__Host-cpu_rt=rt-{LEAK_MARK}-2"]


def test_AC_IDA_17_cookies_left_after_logout_fail(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.logout_clears = False

    assert_fails(capsys, "logout", "cookies not cleared")


def test_AC_IDA_17_a_refresh_token_alive_after_logout_fails(
    hub: FakeHub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.logout_revokes = False

    assert_fails(capsys, "logout-refresh-dead", "expected 401, got HTTP 200")


@pytest.mark.parametrize(
    "argv",
    [
        ["--frontend-url", APP],
        ["--email", "no-at-sign", "--frontend-url", APP],
        ["--email", EMAIL, "--frontend-url", f"{APP}/path"],
        ["--email", EMAIL, "--provider-url", "ftp://127.0.0.1"],
    ],
)
def test_AC_IDA_01_invalid_arguments_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        e2e_login.main(argv)

    assert raised.value.code == 2


def test_AC_IDA_01_send_reports_a_refused_connection_without_the_query() -> None:
    with pytest.raises(e2e_login.E2EError) as raised:
        e2e_login.send("GET", f"http://127.0.0.1:9/x?code={LEAK_MARK}", {})

    assert raised.value.step == "http"
    assert LEAK_MARK not in str(raised.value)
