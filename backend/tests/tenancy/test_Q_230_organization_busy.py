"""Q-230: a lock of the organization not taken within ``lock_timeout`` is ``503 organization_busy``.

With ``Retry-After: 2``, the fixed title the UI shows, and nothing written; for every write that
takes ``lock_org_for_write``/``ensure_writable`` or ``lock_membership_mutex``, not only memberships.
The wait is real: a thread holds the organization row ``FOR UPDATE`` (as the operator's suspension
does) and the request, in another thread, waits on it until PostgreSQL shows it blocked
(``wait_for_a_blocked_backend``) and its shortened ``lock_timeout`` runs out. Any other database
error is still the generic ``500``.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from django.db import OperationalError, connection
from django.test import Client

from apps.common.api.exceptions import problem_exception_handler
from apps.common.authz.roles import Role
from apps.common.tenancy import locks
from apps.tenancy.models import Branch, Invitation, Organization
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.membership_setup import member, role_of
from tests.tenancy.api.probe import PLATFORM, as_member, bearer_of, new_org, new_user
from tests.tenancy.invitation_setup import issue, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

BUSY_TITLE = "Hay otra operación en curso, probá de nuevo"


@dataclass
class Write:
    """One request that takes a lock of the organization, and how to tell it wrote nothing."""

    method: str
    path: str
    body: dict[str, Any]
    headers: dict[str, str]
    untouched: Callable[[], bool]


def change_a_role(org: Organization) -> Write:
    owner, _ = member(org, Role.OWNER)
    _, target = member(org, Role.ADMIN)
    return Write(
        "PATCH",
        f"/api/memberships/{target.pk}/",
        {"role": "viewer"},
        as_member(owner, org.id),
        lambda: role_of(target) == "admin",
    )


def create_a_branch(org: Organization) -> Write:
    owner, _ = member(org, Role.OWNER)
    rows = Branch.objects.unscoped(PLATFORM).filter(organization=org)
    return Write(
        "POST",
        "/api/branches/",
        {"name": "Centro"},
        as_member(owner, org.id),
        lambda: not rows.exists(),
    )


def edit_the_organization(org: Organization) -> Write:
    owner, _ = member(org, Role.OWNER)
    rows = Organization.objects.unscoped(PLATFORM).filter(pk=org.pk)
    return Write(
        "PATCH",
        "/api/organizations/current/",
        {"name": "Otra"},
        as_member(owner, org.id),
        lambda: rows.values_list("name", flat=True).get() == "A",
    )


def accept_an_invitation(org: Organization) -> Write:
    invitation, token = issue(org, "x@hub.test")
    return Write(
        "POST",
        "/api/invitations/accept/",
        {"token": token},
        bearer_of(new_user("x")),
        lambda: status_of(invitation) == "pending",
    )


def create_an_invitation(org: Organization) -> Write:
    owner, _ = member(org, Role.OWNER)
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=org)
    return Write(
        "POST",
        "/api/invitations/",
        {"email": "x@hub.test", "role": "viewer"},
        as_member(owner, org.id),
        lambda: not rows.exists(),
    )


class Request(threading.Thread):
    def __init__(self, write: Write) -> None:
        super().__init__(daemon=True)
        self.write = write
        self.response: Any = None

    def run(self) -> None:
        try:
            self.response = Client().generic(
                self.write.method,
                self.write.path,
                data=json.dumps(self.write.body),
                content_type="application/json",
                headers=self.write.headers,
            )
        finally:
            connection.close()


def hold_the_organization(org: Organization) -> Callable[[], Organization]:
    return lambda: Organization.objects.unscoped(PLATFORM).select_for_update().get(pk=org.pk)


@pytest.mark.parametrize(
    "build",
    [
        change_a_role,
        create_a_branch,
        edit_the_organization,
        accept_an_invitation,
        create_an_invitation,
    ],
)
def test_Q_230_lock_timeout_is_organization_busy(
    build: Callable[[Organization], Write], monkeypatch: pytest.MonkeyPatch
) -> None:
    org = new_org("A")
    write = build(org)
    monkeypatch.setattr(locks, "LOCK_TIMEOUT", "1s")  # 5 s in production: the test is short
    holder = Held(hold_the_organization(org))
    request = Request(write)
    holder.start()
    try:
        assert holder.reached.wait(PATIENCE), "the holder never took the lock"
        request.start()
        assert wait_for_a_blocked_backend(), "the request did not wait for the lock"
        request.join(PATIENCE)
        assert not request.is_alive(), "the request waited past its lock timeout"
    finally:
        holder.go_on.set()
        holder.join(PATIENCE)
    assert holder.error is None

    response = request.response
    assert response.status_code == 503
    assert response["Retry-After"] == "2"
    body = response.json()
    assert (body["code"], body["title"], body["status"]) == ("organization_busy", BUSY_TITLE, 503)
    assert "detail" not in body
    assert write.untouched()
    assert Invitation.objects.unscoped(PLATFORM).filter(status="accepted").count() == 0


class _LockNotAvailableError(Exception):
    sqlstate = "55P03"


class _OtherDatabaseError(Exception):
    sqlstate = "57014"  # query_canceled: not a lock


def _wrapped(cause: Exception) -> OperationalError:
    error = OperationalError("database error")
    error.__cause__ = cause
    return error


def test_Q_230_only_lock_not_available_is_busy() -> None:
    busy = problem_exception_handler(_wrapped(_LockNotAvailableError()), {})
    other = problem_exception_handler(_wrapped(_OtherDatabaseError()), {})
    bare = problem_exception_handler(OperationalError("no cause"), {})

    assert (busy.status_code, busy.data["code"], busy["Retry-After"]) == (
        503,
        "organization_busy",
        "2",
    )
    for response in (other, bare):
        assert (response.status_code, response.data["code"]) == (500, "internal_error")
        assert not response.has_header("Retry-After")
