"""E2E of tenancy with the fake OIDC provider (T-TEN-36, SPEC-02, design.md §9, Q-108).

Usage, against a running stack with dev or test settings and ``IDENTITY_OIDC_PROVIDER=fake``:
    python3 scripts/e2e_tenancy.py --manage "COMMAND" --operator EMAIL
        [--frontend-url URL] [--provider-url URL] [--run-id ID]

``--manage`` is how this machine runs ``manage.py`` in the stack's backend, e.g.
``"docker compose -p hub-e2e exec -T backend python manage.py"``; it is split as a shell would
and never goes through a shell. ``--operator`` is an email of ``PLATFORM_OPERATOR_EMAILS``.
Every person and company is new to the run: the emails and keys carry ``--run-id`` (random by
default), so the script can run again on the same stack.

It drives the stack as people would, each in a browser of its own (``e2e_login.Browser``):

- AC-TEN-22: the operator creates company A by command; the link it prints once is on the app,
  with the token in the fragment. The owner, a new person, opens ``/invitacion`` and logs in: the
  first login accepts the invitation (SPEC-01, RN-IDA-06), and A has exactly one member, the owner.
- The owner creates a branch and invites an ``operator`` (``201`` with the link; the token is in
  no list, AC-TEN-24). The operator logs in, in another session, and sees Sucursales read-only:
  the list answers, ``allowed_actions`` has no branch write and creating one is ``403``.
- AC-TEN-39: company B invites that operator, already a user, as ``viewer``, and someone else;
  company C invites them as owner and is suspended. ``/api/invitations/mine/`` lists B's only,
  with organization, role and expiry, without a token. Accepting the other email's invitation by
  id is the same ``400 invitation_invalid`` as an id that does not exist, and that invitation is
  still ``pending``; accepting their own from the session gives a ``viewer`` membership of B.
- AC-TEN-08: ``/api/organizations/`` of that person is exactly A (``operator``) and B (``viewer``).

**Not covered here:** after that first login the ``/invitacion`` page sends the token it kept,
for an invitation the login already accepted. What it should show then is an open question
(proposed as Q-243), so this script does not send it. Audit events are left to the backend tests.

**Prerequisites.** As ``e2e_login.py``: dev or test settings (the CI stack runs ``settings.prod``),
``--frontend-url`` exactly ``HUB_APP_ORIGIN`` and ``FRONTEND_BASE_URL``, ``--provider-url`` if the
backend is published on another port. ``infra/README.md`` ("E2E de tenancy") raises a throwaway
stack. Nothing secret is printed: no link, token, cookie nor command output; a failure is
``e2e failed [<step>]: <detail>``. Exit 0 ok, 1 failed, 2 invalid arguments. Standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shlex
import subprocess
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import e2e_login
from e2e_login import COOKIE_CSRF, Browser, E2EError, Response, http_origin, ok, shown

COMMAND_TIMEOUT_SECONDS = 120
INVITATION_PAGE_PATH = "/invitacion"
ORGANIZATIONS_PATH = "/api/organizations/"
CURRENT_PATH = "/api/organizations/current/"
MEMBERSHIPS_PATH = "/api/memberships/"
INVITATIONS_PATH = "/api/invitations/"
MINE_PATH = "/api/invitations/mine/"
BRANCHES_PATH = "/api/branches/"
BRANCH_WRITES = frozenset({"branch.create", "branch.update", "branch.deactivate"})
ORGANIZATION_FIELDS = frozenset({"id", "name", "status", "role"})
MINE_FIELDS = frozenset({"id", "organization", "role", "expires_at"})
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
CREATED_LINE = re.compile(rf"Organization ({_UUID}) created; owner invitation ({_UUID})")
AGENT = e2e_login.BROWSERS[0][1]


@dataclass(frozen=True)
class Config:
    frontend_url: str
    provider_url: str | None
    manage: tuple[str, ...]
    operator: str
    run_id: str

    def email(self, who: str) -> str:
        return f"e2e-{who}-{self.run_id}@example.test"


@dataclass(frozen=True)
class Invitation:
    id: str
    token: str


@dataclass(frozen=True)
class Company:
    """An organization of the run and the owner invitation the command issued for it."""

    id: str
    owner: Invitation


def run_manage(argv: Sequence[str]) -> tuple[int, str]:
    """``manage.py`` in the stack: exit code and stdout. Stderr is dropped (it may echo args)."""
    done = subprocess.run(  # noqa: S603 - argv from --manage, no shell
        list(argv), capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS, check=False
    )
    return done.returncode, done.stdout


def manage(config: Config, step: str, *args: str) -> str:
    try:
        code, output = run_manage([*config.manage, *args])
    except (OSError, subprocess.TimeoutExpired) as error:
        raise E2EError(step, f"{args[0]}: {type(error).__name__}") from None
    if code != 0:
        raise E2EError(step, f"{args[0]} exited {code}")
    return output


def token_of(step: str, link: str, app_origin: str) -> str:
    """The link of design.md §6: ``{app}/invitacion#token=<token>``, the token in the fragment."""
    parts = urlsplit(link)
    if shown(link) != f"{app_origin}{INVITATION_PAGE_PATH}" or parts.query:
        raise E2EError(step, f"the link is not the app's invitation page: {shown(link)}")
    match = re.fullmatch(r"token=([A-Za-z0-9_\-]{20,})", parts.fragment)
    if not match:
        raise E2EError(step, "the link has no token in its fragment")
    return match.group(1)


def create_org(config: Config, label: str, owner: str) -> Company:
    """AC-TEN-22: ``tenancy_create_org`` with a key of this run; its output is never printed."""
    step = f"org-{label}"
    output = manage(
        config,
        step,
        "tenancy_create_org",
        f"--key=e2e-{config.run_id}-{label}",
        f"--name=E2E {label} {config.run_id}",
        f"--owner-email={owner}",
        f"--operator={config.operator}",
    )
    found = CREATED_LINE.search(output)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not found or not lines:
        raise E2EError(step, "the command did not report a new organization and its invitation")
    token = token_of(step, lines[-1], config.frontend_url)
    return Company(found.group(1), Invitation(found.group(2), token))


def suspend(config: Config, company: Company) -> None:
    manage(
        config,
        "suspend-C",
        "tenancy_set_org_status",
        f"--org={company.id}",
        "--status=suspended",
        "--reason=E2E of tenancy",
        f"--operator={config.operator}",
    )


def call(
    browser: Browser, method: str, path: str, *, org: str | None = None, body: object = None
) -> Response:
    """A request of the app's JavaScript: JSON, ``X-Organization-Id`` per tab, CSRF on writes."""
    headers = {"User-Agent": browser.user_agent, "Accept": "application/json"}
    if browser.jar.values:
        headers["Cookie"] = browser.jar.header()
    if org is not None:
        headers["X-Organization-Id"] = org
    data = None
    if method != "GET":
        headers["Origin"] = browser.app_origin
        headers["X-CSRF-Token"] = browser.jar.values.get(COOKIE_CSRF, "")
        data = b"" if body is None else json.dumps(body).encode()
        if body is not None:
            headers["Content-Type"] = "application/json"
    response = e2e_login.send(method, f"{browser.app_origin}{path}", headers, data)
    browser.jar.update(response)
    return response


def expect(step: str, response: Response, status: int) -> Any:
    if response.status != status:
        raise E2EError(step, f"expected {status}, got HTTP {response.status}")
    return response.json(step) if response.body else None


def rows(
    step: str,
    browser: Browser,
    path: str,
    org: str | None = None,
    tokens: Sequence[Invitation] = (),
) -> list[dict[str, Any]]:
    """One page of a list of SPEC-00 (``{count, next, previous, results}``) with no token in it."""
    response = call(browser, "GET", f"{path}?page_size=200", org=org)
    body = expect(step, response, 200)
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list) or body.get("next") is not None:
        raise E2EError(step, "not one page of results")
    if not all(isinstance(row, dict) for row in results):
        raise E2EError(step, "a row is not an object")
    if any(invitation.token in response.body for invitation in tokens):
        raise E2EError(step, "a list carries an invitation token")  # AC-TEN-24
    return results


def person(config: Config, who: str) -> Browser:
    """A new browser that logs ``who`` in; a new email gets in by its pending invitations."""
    browser = Browser(who, AGENT, config.frontend_url)
    login = e2e_login.Config(config.frontend_url, config.provider_url, config.email(who))
    e2e_login.login(browser, login)
    return browser


def expect_orgs(step: str, browser: Browser, wanted: dict[str, str]) -> None:
    """AC-TEN-08: the companies of the person and the role in each, nothing else."""
    found: dict[str, str] = {}
    for row in rows(step, browser, ORGANIZATIONS_PATH):
        if set(row) != ORGANIZATION_FIELDS:
            raise E2EError(step, "an organization row out of contract")
        found[row["id"]] = row["role"]
    if found != wanted:
        detail = f"expected roles {sorted(wanted.values())}, got {sorted(found.values())}"
        raise E2EError(step, detail)


def pending(
    step: str, browser: Browser, company: Company, tokens: Sequence[Invitation]
) -> set[str]:
    listed = rows(step, browser, INVITATIONS_PATH, company.id, tokens)
    return {row["id"] for row in listed if row.get("status") == "pending"}


def owner_joins(config: Config, company: Company, who: str, label: str) -> Browser:
    """AC-TEN-22: the link's page opens without a session, then the first login; one owner."""
    step = f"owner-{label}"
    page = Browser(f"{who}-page", AGENT, config.frontend_url)
    if call(page, "GET", INVITATION_PAGE_PATH).status != 200:
        raise E2EError(step, "the invitation page does not open without a session")
    browser = person(config, who)
    expect_orgs(step, browser, {company.id: "owner"})
    members = rows(step, browser, MEMBERSHIPS_PATH, company.id)
    owners = [m for m in members if m.get("role") == "owner" and m.get("status") == "active"]
    if len(members) != 1 or len(owners) != 1:
        raise E2EError(step, f"expected exactly one member, the owner; got {len(members)}")
    if pending(step, browser, company, [company.owner]):
        raise E2EError(step, "an invitation is still pending after the owner joined")
    return browser


def invite(step: str, browser: Browser, org: str, email: str, role: str) -> Invitation:
    asked = {"email": email, "role": role}
    created = expect(step, call(browser, "POST", INVITATIONS_PATH, org=org, body=asked), 201)
    if not isinstance(created, dict) or created.get("role") != role:
        raise E2EError(step, "the created invitation is not the one asked for")
    token = token_of(step, str(created.get("accept_url")), browser.app_origin)
    return Invitation(str(created.get("id")), token)


def operator_reads_branches(browser: Browser, org: str, branch: str) -> None:
    """Sucursales in read-only mode: listed, no write action, and a write is ``403``."""
    step = "operator-branches"
    if branch not in {row.get("id") for row in rows(step, browser, BRANCHES_PATH, org)}:
        raise E2EError(step, "the operator does not see the branch")
    current = expect(step, call(browser, "GET", CURRENT_PATH, org=org), 200)
    actions = set(current.get("allowed_actions", []))
    if current.get("my_role") != "operator" or "branch.read" not in actions:
        raise E2EError(step, "the active company does not say operator with branch.read")
    if actions & BRANCH_WRITES:
        raise E2EError(step, f"the operator may write branches: {sorted(actions & BRANCH_WRITES)}")
    attempt = call(browser, "POST", BRANCHES_PATH, org=org, body={"name": "E2E operator"})
    if attempt.status != 403:
        raise E2EError(step, f"a branch created as operator: expected 403, got {attempt.status}")
    if call(browser, "GET", MEMBERSHIPS_PATH, org=org).status != 403:
        raise E2EError(step, "the operator lists the members (AC-TEN-34)")


def refusal(step: str, response: Response) -> dict[str, Any]:
    """The body of a ``400 invitation_invalid`` without its per-request id."""
    body = expect(step, response, 400)
    if not isinstance(body, dict) or body.get("code") != "invitation_invalid":
        raise E2EError(step, "expected invitation_invalid")
    return {key: value for key, value in body.items() if key not in {"request_id", "instance"}}


def mine(step: str, browser: Browser, tokens: Sequence[Invitation]) -> dict[str, dict[str, Any]]:
    found = {row["id"]: row for row in rows(step, browser, MINE_PATH, tokens=tokens)}
    if any(set(row) != MINE_FIELDS for row in found.values()):
        raise E2EError(step, "an invitation of mine out of contract")
    return found


def accept_from_session(
    config: Config, member: Browser, a: Company, b: Company, c: Company
) -> None:
    """AC-TEN-39 with B (``viewer``, and someone else's) and C (``owner``, then suspended)."""
    owner_b = owner_joins(config, b, "owner-b", "B")
    ok("owner-B")
    own = invite("invite-viewer-B", owner_b, b.id, config.email("member"), "viewer")
    other = invite("invite-other-B", owner_b, b.id, config.email("other"), "viewer")
    ok("invite-B")
    tokens = [own, other, b.owner, c.owner]
    if set(mine("mine-before", member, tokens)) != {own.id, c.owner.id}:
        raise E2EError("mine-before", "expected the invitations of B and C, and no other")
    suspend(config, c)
    ok("suspend-C")
    listed = mine("mine", member, tokens)
    if set(listed) != {own.id}:
        raise E2EError("mine", "expected only the invitation of B (C is suspended)")
    row = listed[own.id]
    if row["organization"].get("id") != b.id or row["role"] != "viewer" or not row["expires_at"]:
        raise E2EError("mine", "the invitation of B lacks its company, role or expiry")
    ok("mine")
    step = "accept-other-email"
    theirs = refusal(step, call(member, "POST", f"{INVITATIONS_PATH}{other.id}/accept/"))
    missing = refusal(step, call(member, "POST", f"{INVITATIONS_PATH}{uuid.uuid4()}/accept/"))
    if theirs != missing:
        raise E2EError(step, "another person's invitation answers unlike a missing one")
    if other.id not in pending(step, owner_b, b, tokens):
        raise E2EError(step, "the other person's invitation is no longer pending")
    expect_orgs(step, member, {a.id: "operator"})
    ok(step)
    step = "accept-from-session"
    joined = expect(step, call(member, "POST", f"{INVITATIONS_PATH}{own.id}/accept/"), 200)
    if joined.get("organization", {}).get("id") != b.id or joined.get("role") != "viewer":
        raise E2EError(step, "the membership is not a viewer of B")
    if own.id in mine(step, member, tokens):
        raise E2EError(step, "the accepted invitation is still listed as mine")
    ok(step)


def run(config: Config) -> None:
    a = create_org(config, "A", config.email("owner-a"))
    ok("org-A")
    owner = owner_joins(config, a, "owner-a", "A")
    ok("owner-A")
    created = call(owner, "POST", BRANCHES_PATH, org=a.id, body={"name": "E2E"})
    branch = expect("branch-A", created, 201)
    ok("branch-A")
    invited = invite("invite-operator", owner, a.id, config.email("member"), "operator")
    if invited.id not in pending("invite-operator", owner, a, [a.owner, invited]):
        raise E2EError("invite-operator", "the invitation is not listed as pending")
    ok("invite-operator")
    member = person(config, "member")
    expect_orgs("operator-A", member, {a.id: "operator"})
    ok("operator-A")
    operator_reads_branches(member, a.id, str(branch.get("id")))
    ok("operator-branches")
    b = create_org(config, "B", config.email("owner-b"))
    ok("org-B")
    c = create_org(config, "C", config.email("member"))
    ok("org-C")
    accept_from_session(config, member, a, b, c)
    expect_orgs("two-orgs", member, {a.id: "operator", b.id: "viewer"})
    ok("two-orgs")


def load_config(argv: Sequence[str] | None) -> Config:
    parser = argparse.ArgumentParser(description="E2E of tenancy with the fake OIDC provider.")
    parser.add_argument("--manage", required=True, help="how to run manage.py in the backend")
    parser.add_argument("--operator", required=True, help="an email of PLATFORM_OPERATOR_EMAILS")
    parser.add_argument("--frontend-url", type=http_origin, default="http://127.0.0.1:3000")
    parser.add_argument("--provider-url", type=http_origin, default=None)
    parser.add_argument("--run-id", default=None, help="1 to 16 lowercase letters or digits")
    args = parser.parse_args(argv)
    try:
        manage_argv = tuple(shlex.split(args.manage))
    except ValueError:
        parser.error("--manage is not a command line")
    if not manage_argv:
        parser.error("--manage is empty")
    operator = args.operator.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", operator):
        parser.error("--operator is not an address")
    run_id = args.run_id or secrets.token_hex(4)
    if not re.fullmatch(r"[a-z0-9]{1,16}", run_id):
        parser.error("--run-id must be 1 to 16 lowercase letters or digits")
    return Config(args.frontend_url, args.provider_url, manage_argv, operator, run_id)


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
