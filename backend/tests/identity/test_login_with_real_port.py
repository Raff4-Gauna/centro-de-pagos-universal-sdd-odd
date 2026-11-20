"""The first login with SPEC-02's invitation port: AC-IDA-02, 04, 05 and 31, Q-120 (T-TEN-17).

The BFF route with Google faked at the network (``api/login_flow.py``), as the in-memory tests of
T-IDA-12/13 run it, but with ``IDENTITY_INVITATION_PORT`` left at its real value: the invitations,
memberships and tenancy audit are the rows of ``apps.tenancy``. Identity's audit stays the
recording port of ``fakes.py``. A lock of the organization not taken in time is Q-230.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings as django_settings
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.authz.roles import Role
from apps.common.tenancy import locks
from apps.identity.domain.audit_events import IdentityAuditAction
from apps.identity.models import AuthSession, SessionStatus, User
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services import invitation_port
from tests.identity.api.login_flow import EMAIL, Flow, flow
from tests.identity.test_refresh_concurrency import PATIENCE
from tests.tenancy.api.probe import PLATFORM, new_org
from tests.tenancy.invitation_setup import issue, make_due, set_status, status_of
from tests.tenancy.test_AC_TEN_28_lock_races import Held

__all__ = ["flow"]

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

REAL_PORT = "apps.tenancy.services.invitation_port.TenancyInvitationPort"


@pytest.fixture
def real(flow: Flow, settings: SettingsWrapper) -> Flow:
    """The login flow, with the invitation port of the settings instead of the in-memory one."""
    settings.IDENTITY_INVITATION_PORT = REAL_PORT
    return flow


def problem_code(response: Any, status: int) -> str:
    assert response.status_code == status
    assert response["Content-Type"] == "application/problem+json"
    return str(response.json()["code"])


def all_memberships() -> list[tuple[Any, ...]]:
    rows = Membership.objects.unscoped(PLATFORM).order_by("organization_id")
    return list(rows.values_list("organization_id", "user_id", "role", "source_invitation_id"))


def created_by_invitation(flow: Flow) -> list[Any]:
    return [
        event.organization_id
        for event in flow.ports.audit.events
        if event.action == IdentityAuditAction.USER_CREATED_BY_INVITATION
    ]


def assert_nothing_left(*invitations: Invitation) -> None:
    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert all_memberships() == []
    for invitation in invitations:
        assert status_of(invitation) == InvitationStatus.PENDING


def test_real_port_is_the_default_setting() -> None:
    assert django_settings.IDENTITY_INVITATION_PORT == REAL_PORT


def test_AC_IDA_02_invited_login_creates_membership(real: Flow) -> None:
    org = new_org("A")
    invitation, _ = issue(org, EMAIL, Role.OPERATOR)

    response = real.login()

    assert response.status_code == 200
    [user] = User.objects.all()
    assert user.email == EMAIL
    assert all_memberships() == [(org.id, user.pk, "operator", invitation.id)]
    assert status_of(invitation) == InvitationStatus.ACCEPTED
    assert AuthSession.objects.filter(user=user, status=SessionStatus.ACTIVE).count() == 1
    assert created_by_invitation(real) == [org.id]


def test_Q_120_all_valid_invitations_accepted(real: Flow) -> None:
    first, second = sorted((new_org("A"), new_org("B")), key=lambda org: org.id)
    issued = [issue(first, EMAIL, Role.ADMIN)[0], issue(second, EMAIL, Role.VIEWER)[0]]
    elsewhere, _ = issue(new_org("C"), "beto@example.com")

    response = real.login()

    assert response.status_code == 200
    [user] = User.objects.all()
    assert [row[:3] for row in all_memberships() if row[1] == user.pk] == [
        (first.id, user.pk, "admin"),
        (second.id, user.pk, "viewer"),
    ]
    assert [status_of(item) for item in issued] == [InvitationStatus.ACCEPTED] * 2
    assert status_of(elsewhere) == InvitationStatus.PENDING
    assert sorted(created_by_invitation(real)) == sorted([first.id, second.id])


@pytest.mark.parametrize("case", ["expired", "due_but_pending", "revoked", "suspended"])
def test_AC_IDA_04_expired_invitation(real: Flow, case: str) -> None:
    org = new_org("A")
    invitation, _ = issue(org, EMAIL)
    if case == "expired":
        set_status(invitation, InvitationStatus.EXPIRED)
    if case == "due_but_pending":
        make_due(invitation)  # valid when the login started, a week ago
    if case == "revoked":
        set_status(invitation, InvitationStatus.REVOKED)
    if case == "suspended":
        Organization.objects.unscoped(PLATFORM).filter(pk=org.pk).update(status="suspended")
    before = status_of(invitation)

    assert problem_code(real.login(), 403) == "not_invited"

    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert all_memberships() == []
    assert status_of(invitation) == before


def test_AC_IDA_04_revoked_between_find_and_accept(
    real: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Valid when the port locked it; revoked before its turn (only this transaction can now).
    invitation, _ = issue(new_org("A"), EMAIL)
    found = invitation_port.TenancyInvitationPort.find_valid_invitations

    def then_revoke(self: Any, email: str, *, now: Any) -> Any:
        refs = found(self, email, now=now)
        set_status(invitation, InvitationStatus.REVOKED)
        return refs

    monkeypatch.setattr(
        invitation_port.TenancyInvitationPort, "find_valid_invitations", then_revoke
    )

    assert problem_code(real.login(), 403) == "not_invited"

    assert not User.objects.exists()
    assert status_of(invitation) == InvitationStatus.PENDING  # the rollback took the revoke too


@pytest.mark.parametrize("failing", [0, 1])
def test_AC_IDA_05_one_invalid_rolls_back_all(
    real: Flow, monkeypatch: pytest.MonkeyPatch, failing: int
) -> None:
    orgs = sorted((new_org("A"), new_org("B")), key=lambda org: org.id)
    issued = [issue(org, EMAIL)[0] for org in orgs]
    found = invitation_port.TenancyInvitationPort.find_valid_invitations

    def then_spoil_one(self: Any, email: str, *, now: Any) -> Any:
        refs = found(self, email, now=now)
        Organization.objects.unscoped(PLATFORM).filter(pk=orgs[failing].pk).update(
            status="suspended"
        )
        return refs

    monkeypatch.setattr(
        invitation_port.TenancyInvitationPort, "find_valid_invitations", then_spoil_one
    )

    assert problem_code(real.login(), 403) == "not_invited"

    assert_nothing_left(*issued)
    assert created_by_invitation(real) == []


@pytest.mark.parametrize("google_email", ["ana@example.com", "Ana@Example.com", "ANA@EXAMPLE.COM"])
def test_AC_IDA_31_normalized_email_matches(real: Flow, google_email: str) -> None:
    invitation, _ = issue(new_org("A"), " Ana@Example.com ")

    response = real.login(email=google_email)

    assert response.status_code == 200
    [user] = User.objects.all()
    assert user.email == "ana@example.com"
    assert status_of(invitation) == InvitationStatus.ACCEPTED


@pytest.mark.parametrize("google_email", ["ana+1@example.com", "a.na@example.com"])
def test_AC_IDA_31_alias_is_not_invited(real: Flow, google_email: str) -> None:
    invitation, _ = issue(new_org("A"), " Ana@Example.com ")

    assert problem_code(real.login(email=google_email), 403) == "not_invited"

    assert_nothing_left(invitation)


@pytest.mark.django_db(transaction=True)
def test_Q_230_lock_timeout_in_the_callback_writes_nothing(
    real: Flow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The operator's suspension holds the organization ``FOR UPDATE`` past the lock timeout.
    org = new_org("A")
    invitation, _ = issue(org, EMAIL)
    monkeypatch.setattr(locks, "LOCK_TIMEOUT", "1s")
    holder = Held(
        lambda: Organization.objects.unscoped(PLATFORM).select_for_update().get(pk=org.pk)
    )
    holder.start()
    try:
        assert holder.reached.wait(PATIENCE), "the holder never took the lock"
        response = real.login()
    finally:
        holder.go_on.set()
        holder.join(PATIENCE)
    assert holder.error is None

    assert problem_code(response, 503) == "organization_busy"
    assert response["Retry-After"] == "2"
    assert_nothing_left(invitation)
    assert created_by_invitation(real) == []
