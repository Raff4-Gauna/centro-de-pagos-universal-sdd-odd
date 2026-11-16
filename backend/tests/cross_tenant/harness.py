"""The requests every tenant-scoped (route, method) must survive (AC-TEN-12/33, design.md §9).

``World`` is two organizations with the rows of every ``Seed``: ``member`` is the owner of A only,
B has its own owner and rows, and ``operator`` is the owner of a third one (the platform operator,
whom AC-TEN-33 also gives the superuser/staff flags). ``check_endpoint`` sends, in this order:

1. no ``X-Organization-Id`` → ``400 organization_required`` (AC-TEN-06);
2. an unknown UUID → ``404 organization_not_found``; B's id → the same body (AC-TEN-03);
3. A active, the URL and body of B's objects → ``404`` if the route names an object;
4. A ``suspended``, a ``WRITE`` → ``409 organization_suspended``, nothing written (RN-TEN-18);
5. A active, A's own objects → ``2xx``: the case is right and the guard is not denying everything.

``check_exempt`` reads an exempt route scoped to the person (``Exemption.read``) as A's member, with
no header and with B's: ``2xx`` and nothing of B, of its owner or of the owner's session.

After every request B's rows must be unchanged and no response may carry B's ids, B's owner or the
owner's session (``World.marks_of_b``). It returns
the failures instead of asserting, so a test can prove that a broken endpoint is caught: a view
that skips the guard reaches its handler on step 1 and answers anything but ``400``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from django.test import Client
from django.utils import timezone

from apps.common.authz.actions import SUSPENDED_ALLOWED_KINDS
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.querysets import UnscopedReason
from apps.identity.models import User
from apps.identity.services.session_lifecycle import open_session
from apps.tenancy.models import Organization
from tests.cross_tenant.classifier import Endpoint
from tests.cross_tenant.registry import CrossTenantCase, Exemption, Seed
from tests.tenancy.api.probe import HEADER, add_member, bearer_of, new_org, new_user

PLATFORM = UnscopedReason.PLATFORM_COMMAND
# Fields of a problem that differ between two requests (design.md §9: "sin request_id/instance").
VARYING_FIELDS = ("request_id", "instance")
NOT_FOUND = "organization_not_found"

Snapshot = tuple[frozenset[tuple[Any, ...]], ...]


@dataclass
class World:
    org_a: Organization
    org_b: Organization
    member: User
    operator: User
    seeds: tuple[Seed, ...]
    # B's owner and one of its sessions: what a route scoped to the person must never show.
    owner_b_marks: frozenset[str] = frozenset()
    bearers: dict[uuid.UUID, dict[str, str]] = field(default_factory=dict)

    def headers(self, user: User, organization_id: uuid.UUID | None) -> dict[str, str]:
        if user.pk not in self.bearers:  # one session per user: far from the session quota
            self.bearers[user.pk] = bearer_of(user)
        headers = dict(self.bearers[user.pk])
        if organization_id is not None:
            headers[HEADER] = str(organization_id)
        return headers

    def snapshot(self, organization: Organization) -> Snapshot:
        return tuple(seed.rows(organization) for seed in self.seeds)

    def ids_of(self, organization: Organization) -> set[str]:
        rows = (row for table in self.snapshot(organization) for row in table)
        return {str(organization.id), *(str(row[0]) for row in rows)}

    def marks_of_b(self) -> set[str]:
        """Everything of B no response to A's member may carry: its ids, its owner, its session."""
        return self.ids_of(self.org_b) | self.owner_b_marks


def build_world(seeds: tuple[Seed, ...]) -> World:
    org_a, org_b = new_org("A"), new_org("B")
    member, owner_b, operator = new_user("member-a"), new_user("owner-b"), new_user("operator")
    add_member(org_a, member, Role.OWNER)
    add_member(org_b, owner_b, Role.OWNER)
    add_member(new_org("C"), operator, Role.OWNER)
    for seed in seeds:
        seed.create(org_a)
        seed.create(org_b)
    session = open_session(owner_b, now=timezone.now()).session
    marks = frozenset({str(owner_b.pk), owner_b.email, str(session.pk)})
    return World(org_a, org_b, member, operator, seeds, marks)


def send(
    client: Client,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: Mapping[str, Any] | None = None,
) -> Any:
    if body is None:
        return client.generic(method, path, headers=dict(headers))
    return client.generic(
        method, path, data=json.dumps(body), content_type="application/json", headers=dict(headers)
    )


def constant_part(response: Any) -> dict[str, Any]:
    body = dict(response.json())
    for name in VARYING_FIELDS:
        body.pop(name, None)
    return body


def is_problem(response: Any, status: int, code: str) -> bool:
    if response.status_code != status:
        return False
    try:
        return bool(response.json().get("code") == code)
    except ValueError:
        return False


class _Run:
    """One endpoint under test: sends its requests and collects what went wrong."""

    def __init__(
        self, client: Client, world: World, endpoint: Endpoint, case: CrossTenantCase
    ) -> None:
        self.client, self.world, self.endpoint, self.case = client, world, endpoint, case
        self.failures: list[str] = []
        self.b_before = world.snapshot(world.org_b)
        self.b_marks = world.marks_of_b()

    def request(self, step: str, target: Organization, headers: Mapping[str, str]) -> Any:
        case = self.case
        body = case.body(target) if case.body is not None else None
        response = send(self.client, self.endpoint.method, case.path(target), headers, body)
        text = response.content.decode(errors="replace")
        if leaked := sorted(found for found in self.b_marks if found in text):
            self.fail(step, f"the response carries B's data: {leaked}")
        if (after := self.world.snapshot(self.world.org_b)) != self.b_before:
            self.fail(step, "B's rows changed")
            self.b_before = after
        return response

    def expect(self, step: str, response: Any, status: int, code: str) -> bool:
        if is_problem(response, status, code):
            return True
        self.fail(step, f"answered {response.status_code}, not {status} {code}")
        return False

    def fail(self, step: str, message: str) -> None:
        self.failures.append(f"{self.endpoint.label} [{step}]: {message}")


def check_endpoint(
    client: Client, world: World, endpoint: Endpoint, case: CrossTenantCase
) -> list[str]:
    run = _Run(client, world, endpoint, case)
    member, org_a = world.member, world.org_a
    response = run.request("no header", org_a, world.headers(member, None))
    run.expect("no header", response, 400, "organization_required")
    unknown = run.request("unknown org", org_a, world.headers(member, uuid.uuid4()))
    known = run.expect("unknown org", unknown, 404, NOT_FOUND)
    foreign = run.request("org B", org_a, world.headers(member, world.org_b.id))
    found = run.expect("org B", foreign, 404, NOT_FOUND)
    if found and known and constant_part(foreign) != constant_part(unknown):
        run.fail("org B", "the 404 body differs from an unknown organization's")
    _check_objects_of_b(run)
    _check_suspended(run)
    own = run.request("own objects", org_a, world.headers(member, org_a.id))
    if not 200 <= own.status_code < 300:
        run.fail("own objects", f"answered {own.status_code}, not 2xx (wrong case or guard)")
    return run.failures


def _check_objects_of_b(run: _Run) -> None:
    world = run.world
    response = run.request("B's objects", world.org_b, world.headers(world.member, world.org_a.id))
    if "<" in run.endpoint.route and response.status_code != 404:
        run.fail("B's objects", f"answered {response.status_code}, not 404")


def _check_suspended(run: _Run) -> None:
    world, endpoint = run.world, run.endpoint
    spec = endpoint.view_class.action_specs.get(endpoint.action)
    if spec is None or spec.kind in SUSPENDED_ALLOWED_KINDS:
        return
    _set_status(world.org_a, OrgStatus.SUSPENDED)
    try:
        before = world.snapshot(world.org_a)
        headers = world.headers(world.member, world.org_a.id)
        response = run.request("suspended", world.org_a, headers)
        run.expect("suspended", response, 409, "organization_suspended")
        if world.snapshot(world.org_a) != before:
            run.fail("suspended", "A's rows changed")
    finally:
        _set_status(world.org_a, OrgStatus.ACTIVE)


def _set_status(organization: Organization, status: OrgStatus) -> None:
    Organization.objects.unscoped(PLATFORM).filter(pk=organization.pk).update(status=status.value)
    organization.status = status.value


def check_head(
    client: Client, world: World, endpoint: Endpoint, case: CrossTenantCase
) -> list[str]:
    """HEAD, which DRF maps wherever GET is: the same denials, by status (a HEAD has no body)."""
    path, label = case.path(world.org_a), f"HEAD {endpoint.route}"
    failures = []
    for organization_id, expected in ((None, 400), (uuid.uuid4(), 404), (world.org_b.id, 404)):
        response = send(client, "HEAD", path, world.headers(world.member, organization_id))
        if response.status_code != expected:
            failures.append(f"{label}: answered {response.status_code}, not {expected}")
    return failures


def check_operator(
    client: Client, world: World, endpoint: Endpoint, case: CrossTenantCase
) -> list[str]:
    """AC-TEN-33: the operator naming A, which it is no member of, gets the unknown org's 404."""
    run = _Run(client, world, endpoint, case)
    org_a = world.org_a
    a_before = world.snapshot(org_a)
    unknown = run.request("unknown org", org_a, world.headers(world.member, uuid.uuid4()))
    operator = run.request("operator", org_a, world.headers(world.operator, org_a.id))
    found = run.expect("operator", operator, 404, NOT_FOUND)
    if found and constant_part(operator) != constant_part(unknown):
        run.fail("operator", "the 404 body differs from an unknown organization's")
    if world.snapshot(org_a) != a_before:
        run.fail("operator", "A's rows changed")
    return run.failures


def check_exempt(client: Client, world: World, exemption: Exemption) -> list[str]:
    """An exempt route of the person: A's member sees nothing of B, whatever the header says."""
    assert exemption.read is not None
    path, label = exemption.read(world.org_a), f"GET {exemption.route} (exempt)"
    marks = world.marks_of_b()
    failures = []
    for step, organization_id in (("no header", None), ("org B", world.org_b.id)):
        response = send(client, "GET", path, world.headers(world.member, organization_id))
        if not 200 <= response.status_code < 300:
            failures.append(f"{label} [{step}]: answered {response.status_code}, not 2xx")
        text = response.content.decode(errors="replace")
        if leaked := sorted(mark for mark in marks if mark in text):
            failures.append(f"{label} [{step}]: the response carries B's data: {leaked}")
    return failures
