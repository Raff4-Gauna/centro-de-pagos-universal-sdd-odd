"""``TenancyInvitationPort`` against the contract of SPEC-01 (design.md §6.4; 02 design.md §4.4).

The port alone, the way ``user_provisioning`` calls it: inside a transaction, ``find`` then
``accept``. AC-TEN-17 through the port, Q-120 (every valid one), RN-IDA-06 (all or nothing, also
without the caller's rollback) and the lock order of ADR-0002 §3. The login through the BFF with
this port is ``tests/identity/test_login_with_real_port.py``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from django.db import connection, transaction
from django.db.transaction import TransactionManagementError
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.common.audit.port import AuditActor, AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus
from apps.common.tenancy.current import current_tenant
from apps.identity.models import User
from apps.identity.ports.invitations import InvitationPort, InvitationRef, InvitationsNoLongerValid
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Organization
from apps.tenancy.services import invitation_port
from apps.tenancy.services.invitation_port import TenancyInvitationPort
from tests.tenancy.api.probe import add_member, new_org
from tests.tenancy.invitation_setup import issue, make_due, memberships, set_status, status_of
from tests.tenancy.locking import set_status as set_org_status

pytestmark = pytest.mark.django_db

EMAIL = "x@dominio.com"


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


@pytest.fixture
def port() -> InvitationPort:
    return TenancyInvitationPort()


def person(email: str = EMAIL, name: str = "x") -> User:
    """A user as identity inserts it in the login, before asking the port."""
    return User.objects.create_user(google_sub=f"sub-{name}", email=email)


def orgs(*names: str) -> list[Organization]:
    """Organizations in ``id`` order, whatever order they were created in."""
    return sorted((new_org(name) for name in names), key=lambda org: org.id)


# --- AC-TEN-17 and Q-120 --------------------------------------------------------------------------


def test_AC_TEN_17_accept_via_port(port: InvitationPort, recorded: RecordingSink) -> None:
    org = new_org("A")
    invitation, _ = issue(org, EMAIL, Role.OPERATOR)
    user = person()
    now = timezone.now()

    with transaction.atomic():
        found = port.find_valid_invitations(EMAIL, now=now)
        port.accept_invitations(found, user.pk, now=now)

    assert found == [InvitationRef(invitation.id, org.id)]
    [(organization_id, role, status, source)] = memberships(user)
    assert (organization_id, role, status, source) == (org.id, "operator", "active", invitation.id)
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert [event.action for event in recorded.events] == [
        "membership.created",
        "invitation.accepted",
    ]
    for event in recorded.events:
        assert event.actor == AuditActor(kind=AuditActorKind.USER, id=user.pk)
        assert event.organization_id == org.id
    assert current_tenant() is None


def test_AC_TEN_17_second_accept_via_port_is_refused(port: InvitationPort) -> None:
    org = new_org("A")
    invitation, _ = issue(org, EMAIL)
    user = person()
    now = timezone.now()
    with transaction.atomic():
        found = port.find_valid_invitations(EMAIL, now=now)
        port.accept_invitations(found, user.pk, now=now)

    with transaction.atomic(), pytest.raises(InvitationsNoLongerValid):
        port.accept_invitations(found, user.pk, now=now)

    assert len(memberships(user)) == 1
    assert status_of(invitation) == InvitationStatus.ACCEPTED


def test_Q_120_find_returns_every_valid_one_in_organization_order(port: InvitationPort) -> None:
    valid = orgs("A", "B", "C")
    expired, revoked, suspended, other_email, used = orgs("D", "E", "F", "G", "H")
    wanted = [issue(org, EMAIL)[0] for org in valid]
    make_due(issue(expired, EMAIL)[0])
    set_status(issue(revoked, EMAIL)[0], InvitationStatus.REVOKED)
    issue(suspended, EMAIL)
    set_org_status(suspended, OrgStatus.SUSPENDED)
    issue(other_email, "otra@dominio.com")
    someone = person("y@dominio.com", "y")
    issue(used, EMAIL, status="accepted", accepted_by=someone, accepted_at=timezone.now())

    with transaction.atomic():
        found = port.find_valid_invitations(EMAIL, now=timezone.now())

    assert found == [InvitationRef(item.id, item.organization_id) for item in wanted]


def test_Q_120_accepts_all_of_them(port: InvitationPort, recorded: RecordingSink) -> None:
    valid = orgs("A", "B")
    for org, role in zip(valid, (Role.ADMIN, Role.VIEWER), strict=True):
        issue(org, EMAIL, role)
    user = person()
    now = timezone.now()

    with transaction.atomic():
        port.accept_invitations(port.find_valid_invitations(EMAIL, now=now), user.pk, now=now)

    assert [(row[0], row[1]) for row in memberships(user)] == [
        (valid[0].id, "admin"),
        (valid[1].id, "viewer"),
    ]
    assert [event.organization_id for event in recorded.events] == [
        valid[0].id,
        valid[0].id,
        valid[1].id,
        valid[1].id,
    ]


def test_RN_IDA_06_find_skips_an_organization_suspended_under_the_lock(
    port: InvitationPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Active at the first read, suspended by the time its lock is taken.
    org = new_org("A")
    issue(org, EMAIL)
    real = invitation_port.organizations_with_pending

    def then_suspend(email: str, *, now: datetime) -> list[uuid.UUID]:
        ids = real(email, now=now)
        set_org_status(org, OrgStatus.SUSPENDED)
        return ids

    monkeypatch.setattr(invitation_port, "organizations_with_pending", then_suspend)

    with transaction.atomic():
        assert port.find_valid_invitations(EMAIL, now=timezone.now()) == []


# --- Locks: organization before invitation, organizations in id order -----------------------------


def test_RN_IDA_06_find_locks_organizations_in_id_order_then_their_invitation(
    port: InvitationPort,
) -> None:
    created = [new_org(name) for name in ("C", "A", "B")]
    for org in created:
        issue(org, EMAIL)

    with transaction.atomic(), CaptureQueriesContext(connection) as queries:
        port.find_valid_invitations(EMAIL, now=timezone.now())

    locks = [
        q["sql"]
        for q in queries.captured_queries
        if "FOR NO KEY UPDATE" in q["sql"] or "FOR UPDATE" in q["sql"]
    ]
    order = sorted(org.id for org in created)
    assert len(locks) == 6
    for index, organization_id in enumerate(order):
        mutex, invitation = locks[2 * index], locks[2 * index + 1]
        assert "FOR NO KEY UPDATE" in mutex
        assert '"tenancy_organization"' in mutex.split("FROM")[1].split("WHERE")[0]
        assert str(organization_id).replace("-", "") in mutex.replace("-", "")
        assert "FOR UPDATE" in invitation
        assert "FOR NO KEY UPDATE" not in invitation
        assert str(organization_id).replace("-", "") in invitation.replace("-", "")


@pytest.mark.django_db(transaction=True)
def test_RN_IDA_06_both_methods_need_the_callers_transaction(port: InvitationPort) -> None:
    issue(new_org("A"), EMAIL)
    ref = InvitationRef(uuid.uuid4(), uuid.uuid4())

    with pytest.raises(TransactionManagementError):
        port.find_valid_invitations(EMAIL, now=timezone.now())
    with pytest.raises(TransactionManagementError):
        port.accept_invitations([ref], person().pk, now=timezone.now())


# --- All or nothing (RN-IDA-06, AC-IDA-05) --------------------------------------------------------


@pytest.mark.parametrize("failing", [0, 1])
def test_AC_IDA_05_one_invalid_rolls_back_all_inside_the_port(
    port: InvitationPort, failing: int
) -> None:
    # Without the caller's rollback: the port's own savepoint takes the accepted ones back.
    valid = orgs("A", "B")
    issued = [issue(org, EMAIL)[0] for org in valid]
    user = person()
    now = timezone.now()

    with transaction.atomic():
        found = port.find_valid_invitations(EMAIL, now=now)
        set_status(issued[failing], InvitationStatus.REVOKED)  # under our own lock
        with pytest.raises(InvitationsNoLongerValid):
            port.accept_invitations(found, user.pk, now=now)
        assert memberships(user) == []
        assert status_of(issued[1 - failing]) == InvitationStatus.PENDING


@pytest.mark.parametrize("case", ["suspended", "already_member", "wrong_organization", "gone_user"])
def test_RN_IDA_06_every_refusal_is_invitations_no_longer_valid(
    port: InvitationPort, case: str
) -> None:
    org, other = orgs("A", "B")
    invitation, _ = issue(org, EMAIL)
    user = person()
    now = timezone.now()
    ref = InvitationRef(invitation.id, org.id)
    user_id = user.pk
    if case == "suspended":
        set_org_status(org, OrgStatus.SUSPENDED)
    if case == "already_member":
        add_member(org, user, Role.VIEWER)
    if case == "wrong_organization":
        ref = InvitationRef(invitation.id, other.id)
    if case == "gone_user":
        user_id = uuid.uuid4()

    with transaction.atomic(), pytest.raises(InvitationsNoLongerValid) as raised:
        port.accept_invitations([ref], user_id, now=now)

    assert raised.value.__cause__ is None
    assert status_of(invitation) == InvitationStatus.PENDING
    assert len(memberships(user)) == (1 if case == "already_member" else 0)


@pytest.mark.parametrize("email", ["otra@dominio.com", "x+1@dominio.com"])
def test_AC_TEN_35_the_users_own_email_decides_not_the_reference(
    port: InvitationPort, email: str
) -> None:
    invitation, _ = issue(new_org("A"), EMAIL)
    user = person(email)

    with transaction.atomic(), pytest.raises(InvitationsNoLongerValid):
        port.accept_invitations(
            [InvitationRef(invitation.id, invitation.organization_id)], user.pk, now=timezone.now()
        )

    assert status_of(invitation) == InvitationStatus.PENDING
    assert memberships(user) == []


def test_RN_IDA_06_an_empty_list_is_refused(port: InvitationPort) -> None:
    # A quiet return would leave a user created without an invitation.
    with transaction.atomic(), pytest.raises(InvitationsNoLongerValid):
        port.accept_invitations([], person().pk, now=timezone.now())


def test_AC_IDA_04_expired_since_find_is_refused(port: InvitationPort) -> None:
    invitation, _ = issue(new_org("A"), EMAIL)
    user = person()
    now = timezone.now()
    with transaction.atomic():
        found = port.find_valid_invitations(EMAIL, now=now)
        with pytest.raises(InvitationsNoLongerValid):
            port.accept_invitations(found, user.pk, now=now + timedelta(days=8))

    assert status_of(invitation) == InvitationStatus.PENDING  # the savepoint took the expiry too
    assert memberships(user) == []


def test_RNF_TEN_06_logs_carry_ids_not_emails(
    port: InvitationPort,
    capsys: pytest.CaptureFixture[str],
    django_capture_on_commit_callbacks: Callable[..., Any],
) -> None:
    invitation, _ = issue(new_org("A"), EMAIL)
    refused_user = person("otra@dominio.com", "otra")
    user = person()
    now = timezone.now()
    capsys.readouterr()

    with transaction.atomic(), pytest.raises(InvitationsNoLongerValid):
        port.accept_invitations(
            [InvitationRef(invitation.id, invitation.organization_id)], refused_user.pk, now=now
        )
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        port.accept_invitations(port.find_valid_invitations(EMAIL, now=now), user.pk, now=now)

    output = capsys.readouterr().out
    lines = [json.loads(text) for text in output.splitlines()]
    messages = [(line["message"], line.get("reason")) for line in lines if "via" in line]
    assert messages == [
        ("tenancy.invitation_refused", "email_mismatch"),
        ("tenancy.invitation_accepted", None),
    ]
    assert EMAIL not in output
    assert "otra@dominio.com" not in output
