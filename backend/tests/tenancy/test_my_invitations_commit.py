"""Accepting from the session, with committed transactions (AC-TEN-39, design.md §4.4).

``transaction=True``: what a refusal must leave behind is read after the request's own commit,
not inside the test's transaction. The audit goes through ``StructlogAuditSink``, which writes only
on commit, so an ``invitation.rejected`` that a rollback took away would be missing. The races use
threads with their own connection, as ``test_invitation_accept_race.py``: the other side holds the
invitation's row lock while the accept waits for it, and the test waits until PostgreSQL shows the
accept blocked before letting the other side commit.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.identity.models import User
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_from_session
from tests.identity.test_refresh_concurrency import PATIENCE, wait_for_a_blocked_backend
from tests.tenancy.api.probe import PLATFORM, bearer_of, new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, make_due, memberships, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held
from tests.tenancy.test_audit import audit_lines

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

STRUCTLOG_SINK = "apps.common.audit.sinks.StructlogAuditSink"


def accept_url(invitation_id: uuid.UUID) -> str:
    return f"/api/invitations/{invitation_id}/accept/"


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


class Accept(threading.Thread):
    """``accept_from_session`` as the route calls it: no transaction around it."""

    def __init__(self, invitation_id: uuid.UUID, user: User) -> None:
        super().__init__(daemon=True)
        self.invitation_id, self.user = invitation_id, user
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            accept_from_session(self.invitation_id, invitee(self.user))
        except BaseException as error:  # handed to the test, which asserts on it
            self.error = error
        finally:
            connection.close()


def lock_and_set(invitation: Invitation, **values: Any) -> Callable[[], None]:
    """The other side: the invitation ``FOR UPDATE`` (what a revoke takes), then its change."""

    def lock() -> None:
        rows = Invitation.objects.unscoped(PLATFORM).select_for_update().filter(pk=invitation.pk)
        list(rows)
        rows.update(**values)

    return lock


def race(invitation: Invitation, user: User, **values: Any) -> Accept:
    """The other side holds the row with its change; the accept starts, waits, then reads it."""
    other, accepting = Held(lock_and_set(invitation, **values)), Accept(invitation.id, user)
    other.start()
    try:
        assert other.reached.wait(PATIENCE), "the other side never took the lock"
        accepting.start()
        assert wait_for_a_blocked_backend(), "the accept did not wait for the lock"
    finally:
        other.go_on.set()
        other.join(PATIENCE)
    accepting.join(PATIENCE)
    assert other.error is None
    return accepting


def test_AC_TEN_39_foreign_attempt_is_audited(capsys: pytest.CaptureFixture[str]) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    beto = new_user("beto")
    headers = bearer_of(beto)
    capsys.readouterr()

    with override_settings(AUDIT_SINK=STRUCTLOG_SINK):
        response = Client().generic("POST", accept_url(invitation.id), headers=headers)

    assert (response.status_code, response.json()["reason"]) == (400, "not_found")
    [line] = audit_lines(capsys)
    assert (line["action"], line["reason"], line["organization_id"]) == (
        "invitation.rejected",
        "email_mismatch",
        str(org.id),
    )
    assert line["actor"]["id"] == str(beto.pk)
    assert line["metadata"] == {"invitation_id": str(invitation.id)}
    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(beto) == []


def test_AC_TEN_25_expiry_from_the_session_stays_committed() -> None:
    """Review of PR #125: the ``400 expired`` does not roll back the ``pending → expired``."""
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    make_due(invitation)
    ana = new_user("ana")
    headers = bearer_of(ana)

    response = Client().generic("POST", accept_url(invitation.id), headers=headers)

    assert (response.status_code, response.json()["reason"]) == (400, "expired")
    assert status_of(invitation) == InvitationStatus.EXPIRED
    assert memberships(ana) == []


def test_AC_TEN_39_accept_vs_revoke_in_parallel() -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    ana = new_user("ana")

    accepting = race(
        invitation,
        ana,
        status=InvitationStatus.REVOKED.value,
        revoked_reason="revoked",
        revoked_at=timezone.now(),
    )

    assert isinstance(accepting.error, InvitationInvalid)
    assert accepting.error.problem_reason == "revoked"
    assert memberships(ana) == []
    assert status_of(invitation) == InvitationStatus.REVOKED


def test_AC_TEN_39_email_changed_under_lock_is_not_found(recorded: RecordingSink) -> None:
    """Step 1 read Ana's email; under the lock the row names another one: ``not_found``, no
    membership, and ``invitation.rejected`` out of the ``atomic`` (design.md §4.4, step 3)."""
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    ana = new_user("ana")

    accepting = race(invitation, ana, email="otra@hub.test")

    assert isinstance(accepting.error, InvitationInvalid)
    assert accepting.error.problem_reason == "not_found"
    assert memberships(ana) == []
    assert status_of(invitation) == InvitationStatus.PENDING
    assert [(e.action, e.reason) for e in recorded.events] == [
        ("invitation.rejected", "email_mismatch")
    ]
