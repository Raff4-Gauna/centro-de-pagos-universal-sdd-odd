"""The two scopes of the session paths and the first step of ``accept_from_session`` (T-TEN-16).

``Invitation.pending_for_email`` and ``Invitation.for_session_accept`` cross organizations, so they
are reads only (``scopes.ModelScope``): any write under them fails closed (AC-TEN-10). A foreign
attempt answers before any transaction or lock (design.md §4.4, step 2): the queries it runs show
no ``FOR UPDATE`` and no ``FOR NO KEY UPDATE``.
"""

from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.common.tenancy.querysets import TenantScopeError
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation
from apps.tenancy.selectors.invitations import list_my_pending
from apps.tenancy.services.invitation_accept import InvitationInvalid, accept_from_session
from tests.tenancy.api.probe import new_org, new_user
from tests.tenancy.invitation_setup import invitee, issue, memberships, status_of

pytestmark = pytest.mark.django_db


def test_AC_TEN_39_pending_for_email_normalizes_and_crosses_organizations() -> None:
    a, b = new_org("A"), new_org("B")
    in_a, _ = issue(a, "ana@hub.test")
    in_b, _ = issue(b, "ana@hub.test")
    issue(b, "beto@hub.test")
    rows = Invitation.objects.pending_for_email("  ANA@Hub.test ")
    assert set(rows.values_list("id", flat=True)) == {in_a.id, in_b.id}


@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_AC_TEN_39_pending_for_email_needs_an_email(value: object) -> None:
    with pytest.raises(ValueError, match="needs an email"):
        Invitation.objects.pending_for_email(value)  # type: ignore[arg-type]


def test_AC_TEN_10_for_session_accept_needs_a_uuid() -> None:
    with pytest.raises(TypeError, match="UUID"):
        Invitation.objects.for_session_accept(str(uuid.uuid4()))  # type: ignore[arg-type]


def test_AC_TEN_10_session_scopes_are_read_only() -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    for rows in (
        Invitation.objects.pending_for_email("ana@hub.test"),
        Invitation.objects.for_session_accept(invitation.id),
    ):
        assert list(rows.values_list("id", flat=True)) == [invitation.id]
        with pytest.raises(TenantScopeError):
            rows.update(status=InvitationStatus.REVOKED.value)
        with pytest.raises(TenantScopeError):
            rows.delete()
    assert status_of(invitation) == InvitationStatus.PENDING


def test_AC_TEN_39_list_is_empty_for_a_user_without_invitations() -> None:
    issue(new_org("A"), "ana@hub.test")
    assert list_my_pending("beto@hub.test", now=timezone.now()) == []


def test_AC_TEN_39_foreign_attempt_takes_no_lock() -> None:
    invitation, _ = issue(new_org("A"), "ana@hub.test")
    beto = new_user("beto")

    with CaptureQueriesContext(connection) as queries, pytest.raises(InvitationInvalid):
        accept_from_session(invitation.id, invitee(beto))

    sql = " ".join(query["sql"].upper() for query in queries.captured_queries)
    assert "FOR UPDATE" not in sql
    assert "FOR NO KEY UPDATE" not in sql
    assert "SAVEPOINT" not in sql  # no transaction.atomic either
    assert memberships(beto) == []
