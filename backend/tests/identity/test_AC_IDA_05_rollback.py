"""AC-IDA-05 (RN-IDA-06): the user and its invitations are created together or not at all.

Against the real PostgreSQL, with the invitation port in memory: what is proved here is identity's
half, that no user nor session outlives a failed acceptance. That the memberships and the
invitations of SPEC-02 roll back with it is ``T-TEN-17``, with the real port.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest
from django.db import transaction
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.login_rules import (
    LoginRejectedError,
    VerifiedIdentity,
    evaluate_identity,
)
from apps.identity.models import AuthSession, User
from apps.identity.ports.invitations import InvitationRef
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.user_provisioning import provision_user
from tests.identity.fakes import InvitationStatus, Ports, install_ports

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SUB = "1000000000000000000001"

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class PortIsDownError(Exception):
    pass


@pytest.fixture(autouse=True)
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


def identity() -> VerifiedIdentity:
    return evaluate_identity(
        sub=SUB, email="ana@x.com", email_verified=True, name="Ana", picture=""
    )


def callback(*, then_fail: bool = False) -> None:
    """Step 7 as ``login_complete`` runs it: the user and its session in one transaction."""
    with transaction.atomic():
        user = provision_user(identity(), now=NOW)
        open_session(user, now=NOW)
        if then_fail:
            raise PortIsDownError


def assert_nothing_left(ports: Ports) -> None:
    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert ports.audit.events == []
    assert all(item.status == InvitationStatus.PENDING for item in ports.invitations.invitations)
    assert all(item.accepted_by is None for item in ports.invitations.invitations)


@pytest.mark.parametrize("failing", [0, 1, 2])
def test_AC_IDA_05_accept_failure_rolls_back_all(ports: Ports, failing: int) -> None:
    invitations = [ports.invitations.invite("ana@x.com", now=NOW) for _ in range(3)]
    invitations[failing].fails_on_accept = True

    with pytest.raises(LoginRejectedError) as raised:
        callback()

    assert raised.value.code == IdentityErrorCode.NOT_INVITED
    assert raised.value.user_id is None
    assert ports.invitations.calls == ["find_valid_invitations", "accept_invitations"]
    assert_nothing_left(ports)


def test_AC_IDA_05_single_invitation_that_fails_leaves_no_user(ports: Ports) -> None:
    ports.invitations.invite("ana@x.com", now=NOW).fails_on_accept = True

    with pytest.raises(LoginRejectedError) as raised:
        provision_user(identity(), now=NOW)

    assert raised.value.code == IdentityErrorCode.NOT_INVITED
    assert_nothing_left(ports)


def test_AC_IDA_05_any_error_of_the_port_rolls_back_and_is_not_swallowed(
    ports: Ports, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "or any error" (design.md §6.4): it is not a rejection, and the user still does not stay.
    ports.invitations.invite("ana@x.com", now=NOW)

    def broken(invitations: Sequence[InvitationRef], user_id: UUID, *, now: datetime) -> None:
        assert User.objects.filter(pk=user_id).exists()
        raise PortIsDownError

    monkeypatch.setattr(ports.invitations, "accept_invitations", broken)

    with pytest.raises(PortIsDownError):
        provision_user(identity(), now=NOW)

    assert_nothing_left(ports)


def test_AC_IDA_05_failure_after_provisioning_rolls_back_the_user_too(ports: Ports) -> None:
    # ``provision_user`` is a savepoint of the callback's transaction: no user without a session.
    ports.invitations.invite("ana@x.com", now=NOW)

    with pytest.raises(PortIsDownError):
        callback(then_fail=True)

    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
