"""AC-TEN-08/22/39 (T-TEN-36): the steps of ``scripts/e2e_tenancy.py``, against a simulated stack.

``FakeStack`` is the BFF, Django, the fake OIDC provider and ``manage.py`` in a few dicts: a
healthy stack each test breaks in one way. The point is that each step reads the API the way the
app does, fails when the stack misbehaves, names the step and never prints a link, a token nor a
cookie. The run against a real stack is recorded in ``specs/02-tenancy-rbac/verification.md``.
"""

from __future__ import annotations

import itertools
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

import e2e_login
import e2e_tenancy
import pytest
from e2e_login import Response

APP = "http://127.0.0.1:3100"
PROVIDER = "http://localhost:8000"
OPERATOR = "ops@hub.test"
MANAGE = "docker compose -p hub-e2e exec -T backend python manage.py"
LEAK_MARK = "zz9mark"
RUN = "r1"
WRITES = ["branch.create", "branch.update", "branch.deactivate", "branch.reactivate"]


@dataclass
class Invite:
    id: str
    org: str
    email: str
    role: str
    token: str
    status: str = "pending"


@dataclass
class FakeStack:
    """Healthy by default; a flag breaks one behaviour. Tokens and cookies carry ``LEAK_MARK``."""

    link_origin: str = APP
    command_exit: int = 0
    operator_may_write: bool = False
    extra_org: bool = False
    token_in_lists: bool = False
    mine_shows_suspended: bool = False
    other_email_reason: str = "not_found"
    orgs: dict[str, dict[str, str]] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    invites: dict[str, Invite] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    branches: dict[str, list[str]] = field(default_factory=dict)
    commands: list[list[str]] = field(default_factory=list)
    requests: list[tuple[str, str, dict[str, str], bytes | None]] = field(default_factory=list)
    counter: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    # manage.py
    def run_manage(self, argv: Sequence[str]) -> tuple[int, str]:
        prefix = MANAGE.split()
        assert list(argv[: len(prefix)]) == prefix
        name, *rest = argv[len(prefix) :]
        args = dict(arg.removeprefix("--").split("=", 1) for arg in rest)
        self.commands.append([name, *rest])
        assert args["operator"] == OPERATOR
        if self.command_exit:
            return self.command_exit, f"refused for {args.get('owner-email')}"
        if name == "tenancy_set_org_status":
            self.status[args["org"]] = args["status"]
            return 0, f"Organization {args['org']} is now {args['status']}."
        org = str(uuid.uuid4())
        self.orgs[org], self.status[org], self.branches[org] = {}, "active", []
        invite = self.add_invite(org, args["owner-email"], "owner")
        link = f"{self.link_origin}/invitacion#token={invite.token}"
        return 0, f"Organization {org} created; owner invitation {invite.id}, valid.\nSend:\n{link}"

    def add_invite(self, org: str, email: str, role: str) -> Invite:
        token = f"tok{LEAK_MARK}{next(self.counter):030d}"
        invite = Invite(str(uuid.uuid4()), org, email, role, token)
        self.invites[invite.id] = invite
        return invite

    def users(self) -> set[str]:
        return {email for members in self.orgs.values() for email in members}

    # HTTP
    def send(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> Response:
        self.requests.append((method, url, headers, body))
        parts = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(parts.query).items()}
        if not url.startswith(APP):
            assert parts.path == "/dev-oidc/authorize"
            callback = urlencode({"code": f"{LEAK_MARK}{query['email']}"})
            return redirect(f"{APP}/api/auth/google/callback?{callback}")
        path = parts.path
        if path == "/api/auth/google/start":
            location = f"{PROVIDER}/dev-oidc/authorize?state=s{LEAK_MARK}"
            return redirect(location, [f"__Host-cpu_login=b{LEAK_MARK}; Path=/"])
        if path == "/api/auth/google/callback":
            return self.callback(query["code"].removeprefix(LEAK_MARK))
        if path == "/invitacion":
            assert "Cookie" not in headers
            return Response(200, (("Content-Type", "text/html"),), "<html></html>")
        cookie = headers.get("Cookie", "")
        email = next((e for s, e in self.sessions.items() if f"__Host-cpu_at={s}" in cookie), None)
        assert email is not None, f"no session for {method} {path}"
        if method != "GET":
            assert headers["Origin"] == APP
            assert headers["X-CSRF-Token"] == f"c{LEAK_MARK}"
        data = json.loads(body) if body else None
        return self.api(method, path, email, headers.get("X-Organization-Id"), data)

    def callback(self, email: str) -> Response:
        if email not in self.users():
            waiting = [i for i in self.invites.values() if self.valid(i) and i.email == email]
            if not waiting:
                return redirect(f"{APP}/login?error=not_invited")
            for invite in waiting:  # first login accepts them all (SPEC-01, RN-IDA-06)
                self.accept(invite)
        session = f"at{LEAK_MARK}{next(self.counter)}"
        self.sessions[session] = email
        cookies = [f"__Host-cpu_{name}=; Max-Age=0" for name in ("login",)]
        cookies += [f"__Host-cpu_{n}={v}; Path=/" for n, v in (("at", session), ("rt", "r"))]
        cookies.append(f"__Host-cpu_csrf=c{LEAK_MARK}; Path=/")
        return redirect(f"{APP}/inicio", cookies)

    def valid(self, invite: Invite) -> bool:
        return invite.status == "pending" and self.status[invite.org] == "active"

    def accept(self, invite: Invite) -> None:
        invite.status = "accepted"
        self.orgs[invite.org][invite.email] = invite.role

    def api(self, method: str, path: str, email: str, org: str | None, data: object) -> Response:
        route = (method, path)
        if route == ("GET", "/api/me/"):
            return reply(200, {"email": email})
        if route == ("GET", "/api/organizations/"):
            mine = [(o, m[email]) for o, m in self.orgs.items() if email in m]
            if self.extra_org:
                mine.append((str(uuid.uuid4()), "admin"))
            return page([{"id": o, "name": o, "status": "active", "role": r} for o, r in mine])
        if route == ("GET", "/api/invitations/mine/"):
            listed = [
                i
                for i in self.invites.values()
                if i.email == email and (self.valid(i) or self.mine_shows_suspended)
                if i.status == "pending"
            ]
            rows = [
                {
                    "id": i.id,
                    "organization": {"id": i.org, "name": "x"},
                    "role": i.role,
                    "expires_at": "2026-12-01T00:00:00Z",
                }
                for i in listed
            ]
            return page(rows)
        if path.endswith("/accept/"):
            invite = self.invites.get(path.split("/")[3])
            if invite is None or invite.email != email:
                reason = "not_found" if invite is None else self.other_email_reason
                return reply(
                    400,
                    {
                        "code": "invitation_invalid",
                        "reason": reason,
                        "request_id": str(uuid.uuid4()),
                    },
                )
            self.accept(invite)
            body = {"organization": {"id": invite.org, "name": "x"}, "role": invite.role}
            return reply(200, {**body, "membership_id": str(uuid.uuid4())})
        assert org is not None, f"{method} {path} without X-Organization-Id"
        role = self.orgs[org][email]
        manager = role in {"owner", "admin"}
        if route == ("GET", "/api/organizations/current/"):
            actions = ["branch.read", *(WRITES if manager or self.operator_may_write else [])]
            return reply(200, {"id": org, "my_role": role, "allowed_actions": actions})
        if route == ("GET", "/api/memberships/"):
            members = [{"role": r, "status": "active"} for r in self.orgs[org].values()]
            return page(members) if manager else reply(403, {"code": "permission_denied"})
        if path == "/api/branches/":
            if method == "GET":
                return page([{"id": b} for b in self.branches[org]])
            if not (manager or self.operator_may_write):
                return reply(403, {"code": "permission_denied"})
            self.branches[org].append(branch := str(uuid.uuid4()))
            return reply(201, {"id": branch})
        if route == ("GET", "/api/invitations/"):
            listed = [i for i in self.invites.values() if i.org == org and i.status == "pending"]
            rows = [{"id": i.id, "status": i.status, "role": i.role} for i in listed]
            if self.token_in_lists:
                rows = [{**row, "note": i.token} for row, i in zip(rows, listed, strict=True)]
            return page(rows)
        if route == ("POST", "/api/invitations/"):
            assert isinstance(data, dict)
            invite = self.add_invite(org, data["email"], data["role"])
            accept_url = f"{APP}/invitacion#token={invite.token}"
            return reply(201, {"id": invite.id, "role": invite.role, "accept_url": accept_url})
        raise AssertionError(f"unexpected {method} {path}")


def reply(status: int, body: object, set_cookies: Sequence[str] = ()) -> Response:
    headers = [("Content-Type", "application/json")]
    headers += [("Set-Cookie", value) for value in set_cookies]
    return Response(status, tuple(headers), json.dumps(body))


def page(results: Sequence[Mapping[str, object]]) -> Response:
    return reply(200, {"count": len(results), "next": None, "previous": None, "results": results})


def redirect(location: str, set_cookies: Sequence[str] = ()) -> Response:
    headers = [("Location", location)] + [("Set-Cookie", value) for value in set_cookies]
    return Response(302, tuple(headers), "")


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch) -> FakeStack:
    fake = FakeStack()
    monkeypatch.setattr(e2e_login, "send", fake.send)
    monkeypatch.setattr(e2e_tenancy, "run_manage", fake.run_manage)
    return fake


def run_e2e(capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
    argv = ["--manage", MANAGE, "--operator", OPERATOR, "--frontend-url", APP, "--run-id", RUN]
    code = e2e_tenancy.main([*argv, *extra])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert LEAK_MARK not in output, "a token, link or cookie was printed"
    assert "@example.test" not in output, "an email was printed"
    return code, output


def assert_fails(capsys: pytest.CaptureFixture[str], step: str, *details: str) -> None:
    code, output = run_e2e(capsys)
    assert code == 1
    assert f"e2e failed [{step}]" in output
    for detail in details:
        assert detail in output


def email(who: str) -> str:
    return f"e2e-{who}-{RUN}@example.test"


def test_AC_TEN_22_e2e_flow(stack: FakeStack, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    assert output.splitlines()[-1] == "e2e passed"
    for step in ("org-A", "owner-A", "branch-A", "invite-operator", "operator-A"):
        assert f"e2e ok [{step}]" in output
    assert "e2e ok [operator-branches]" in output
    created = [c for c in stack.commands if c[0] == "tenancy_create_org"]
    assert created[0] == [
        "tenancy_create_org",
        f"--key=e2e-{RUN}-A",
        f"--name=E2E A {RUN}",
        f"--owner-email={email('owner-a')}",
        f"--operator={OPERATOR}",
    ]
    org_a = next(iter(stack.orgs))
    assert stack.orgs[org_a] == {email("owner-a"): "owner", email("member"): "operator"}
    refused = [r for r in stack.requests if r[0] == "POST" and r[1].endswith("/api/branches/")]
    assert len(refused) == 2  # the owner's, and the operator's 403
    assert len(stack.branches[org_a]) == 1


def test_AC_TEN_22_a_link_off_the_app_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.link_origin = "http://evil.test"

    assert_fails(capsys, "org-A", "not the app's invitation page", "http://evil.test/invitacion")


def test_AC_TEN_22_a_refused_command_shows_only_its_exit_code(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.command_exit = 2

    assert_fails(capsys, "org-A", "tenancy_create_org exited 2")


def test_AC_TEN_22_an_operator_who_writes_branches_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.operator_may_write = True

    assert_fails(capsys, "operator-branches", "may write branches", "branch.create")


def test_AC_TEN_22_a_token_in_a_list_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.token_in_lists = True

    assert_fails(capsys, "invite-operator", "carries an invitation token")


def test_AC_TEN_08_e2e_two_orgs(stack: FakeStack, capsys: pytest.CaptureFixture[str]) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    assert "e2e ok [two-orgs]" in output
    member_orgs = {o: m[email("member")] for o, m in stack.orgs.items() if email("member") in m}
    assert sorted(member_orgs.values()) == ["operator", "viewer"]
    assert len(stack.orgs) == 3  # C invited them as owner and was suspended: no membership


def test_AC_TEN_08_an_organization_of_someone_else_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.extra_org = True

    assert_fails(capsys, "owner-A", "expected roles ['owner'], got ['admin', 'owner']")


def test_AC_TEN_39_e2e_accept_from_session(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output = run_e2e(capsys)

    assert code == 0
    for step in ("suspend-C", "mine", "accept-other-email", "accept-from-session"):
        assert f"e2e ok [{step}]" in output
    other = next(i for i in stack.invites.values() if i.email == email("other"))
    assert other.status == "pending"
    accepts = [(m, u, b) for m, u, _, b in stack.requests if u.endswith("/accept/")]
    assert len(accepts) == 3
    assert all(method == "POST" and body == b"" for method, _, body in accepts)
    assert stack.status[list(stack.orgs)[2]] == "suspended"


def test_AC_TEN_39_an_invitation_of_a_suspended_org_listed_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.mine_shows_suspended = True

    assert_fails(capsys, "mine", "only the invitation of B")


def test_AC_TEN_39_another_email_answered_unlike_a_missing_id_fails(
    stack: FakeStack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.other_email_reason = "email_mismatch"

    assert_fails(capsys, "accept-other-email", "unlike a missing one")


@pytest.mark.parametrize(
    "argv",
    [
        ["--operator", OPERATOR],
        ["--manage", MANAGE],
        ["--manage", "", "--operator", OPERATOR],
        ["--manage", 'unterminated "quote', "--operator", OPERATOR],
        ["--manage", MANAGE, "--operator", "no-at-sign"],
        ["--manage", MANAGE, "--operator", OPERATOR, "--run-id", "Bad-Id"],
        ["--manage", MANAGE, "--operator", OPERATOR, "--frontend-url", f"{APP}/path"],
    ],
)
def test_AC_TEN_22_invalid_arguments_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        e2e_tenancy.main(argv)

    assert raised.value.code == 2


def test_AC_TEN_22_a_missing_manage_command_is_reported_without_output() -> None:
    config = e2e_tenancy.Config(APP, None, (f"no-such-binary-{LEAK_MARK}",), OPERATOR, RUN)

    with pytest.raises(e2e_login.E2EError) as raised:
        e2e_tenancy.manage(config, "org-A", "tenancy_create_org")

    assert raised.value.step == "org-A"
    assert raised.value.detail == "tenancy_create_org: FileNotFoundError"
