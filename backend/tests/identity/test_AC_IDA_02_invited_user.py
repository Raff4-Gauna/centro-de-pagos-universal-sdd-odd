"""Case (b) of RN-IDA-05: the first login, by invitation (design.md §4.2 step 7b, RN-IDA-06).

``provision_user`` against the real PostgreSQL and the invitation port in memory (``fakes.py``); the
real port repeats AC-IDA-02, 04, 05 and 31 in ``T-TEN-17``. Rejections are only raised here:
``login_complete`` (T-IDA-13) audits them after its rollback. The race of AC-IDA-02 has its own
file, and so does the rollback of AC-IDA-05.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import transaction
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.identity.domain.audit_events import AuditActorType, AuditResult, IdentityAuditAction
from apps.identity.domain.errors import IdentityErrorCode
from apps.identity.domain.login_rules import (
    LoginRejectedError,
    VerifiedIdentity,
    evaluate_identity,
)
from apps.identity.models import AuthSession, SessionStatus, User
from apps.identity.services import user_provisioning
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.user_provisioning import UserProvisioningError, provision_user
from tests.identity.fakes import InvitationStatus, Ports, install_ports

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SUB = "1000000000000000000001"
OTHER_SUB = "1000000000000000000002"

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def ports(settings: SettingsWrapper) -> Ports:
    return install_ports(settings)


def identity(sub: str = SUB, email: str = "ana@x.com", **claims: Any) -> VerifiedIdentity:
    values: dict[str, Any] = {"email_verified": True, "name": "Ana", "picture": ""}
    return evaluate_identity(sub=sub, email=email, **{**values, **claims})


def unchecked_identity(email: str, sub: str = SUB) -> VerifiedIdentity:
    """An address ``evaluate_identity`` would have lowercased: what PostgreSQL's CHECK refuses."""
    return VerifiedIdentity(sub=sub, email=email, display_name="Ana", avatar_url="")


def rejection_of(verified: VerifiedIdentity) -> LoginRejectedError:
    with pytest.raises(LoginRejectedError) as raised:
        provision_user(verified, now=NOW)
    return raised.value


def assert_nothing_created(ports: Ports) -> None:
    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert ports.audit.events == []
    assert all(item.status != InvitationStatus.ACCEPTED for item in ports.invitations.invitations)


def test_AC_IDA_02_invited_user_is_created_and_invitation_accepted(ports: Ports) -> None:
    invitation = ports.invitations.invite("ana@x.com", now=NOW)

    with transaction.atomic():
        user = provision_user(identity(name="Ana", picture="https://x.example.com/a.png"), now=NOW)
        opened = open_session(user, now=NOW)

    [stored] = User.objects.all()
    assert stored.pk == user.pk
    assert (stored.google_sub, stored.email, stored.is_active) == (SUB, "ana@x.com", True)
    assert (stored.display_name, stored.avatar_url) == ("Ana", "https://x.example.com/a.png")
    assert stored.last_login_at == NOW
    assert not stored.has_usable_password()
    assert (invitation.status, invitation.accepted_by) == (InvitationStatus.ACCEPTED, user.pk)
    assert opened.session.status == SessionStatus.ACTIVE
    assert AuthSession.objects.filter(user=user, status=SessionStatus.ACTIVE).count() == 1
    assert ports.invitations.calls == ["find_valid_invitations", "accept_invitations"]
    [event] = ports.audit.events
    assert event.action == IdentityAuditAction.USER_CREATED_BY_INVITATION
    assert event.result == AuditResult.SUCCESS
    assert (event.actor_type, event.actor_id) == (AuditActorType.USER, user.pk)
    assert event.organization_id == invitation.organization_id
    assert event.occurred_at == NOW
    assert event.metadata == {}


def test_AC_IDA_02_every_valid_invitation_is_accepted_one_event_each(ports: Ports) -> None:
    # Q-120: all the valid ones; Q-117: one event per invitation, with its organization.
    first = ports.invitations.invite("ana@x.com", now=NOW)
    second = ports.invitations.invite("ana@x.com", now=NOW)
    expired = ports.invitations.invite("ana@x.com", now=NOW, valid_for=timedelta(0))
    someone_else = ports.invitations.invite("beto@x.com", now=NOW)

    user = provision_user(identity(), now=NOW)

    assert [first.accepted_by, second.accepted_by] == [user.pk, user.pk]
    assert expired.status == InvitationStatus.PENDING
    assert someone_else.status == InvitationStatus.PENDING
    assert [event.action for event in ports.audit.events] == [
        IdentityAuditAction.USER_CREATED_BY_INVITATION
    ] * 2
    assert {event.organization_id for event in ports.audit.events} == {
        first.organization_id,
        second.organization_id,
    }


def test_AC_IDA_02_second_login_is_case_a_and_asks_no_invitation(ports: Ports) -> None:
    ports.invitations.invite("ana@x.com", now=NOW)
    user = provision_user(identity(), now=NOW)
    ports.invitations.calls.clear()
    ports.audit.events.clear()

    again = provision_user(identity(), now=NOW + timedelta(hours=1))

    assert again.pk == user.pk
    assert User.objects.count() == 1
    assert ports.invitations.calls == []  # Q-121
    assert ports.audit.events == []


def test_AC_IDA_03_no_invitation_creates_nothing(
    ports: Ports, capsys: pytest.CaptureFixture[str]
) -> None:
    ports.invitations.invite("beto@x.com", now=NOW)
    capsys.readouterr()

    rejection = rejection_of(identity())

    assert rejection.code == IdentityErrorCode.NOT_INVITED
    assert rejection.user_id is None
    assert_nothing_created(ports)
    assert ports.invitations.calls == ["find_valid_invitations"]
    output = capsys.readouterr().out
    assert "ana@x.com" not in output
    assert SUB not in output


def test_AC_IDA_03_default_stub_port_rejects_every_new_login(settings: SettingsWrapper) -> None:
    # Until SPEC-02 registers its port (design.md §6.4).
    settings.IDENTITY_INVITATION_PORT = "apps.identity.ports.stubs.NullInvitationPort"

    assert rejection_of(identity()).code == IdentityErrorCode.NOT_INVITED
    assert not User.objects.exists()


@pytest.mark.parametrize("case", ["expired", "expires_now", "revoked", "already_accepted"])
def test_AC_IDA_04_expired_or_revoked_is_not_invited(ports: Ports, case: str) -> None:
    # Valid when the login started, five minutes ago; judged at the callback.
    started = NOW - timedelta(minutes=5)
    lifetime = {"expired": timedelta(minutes=1), "expires_now": timedelta(minutes=5)}
    invitation = ports.invitations.invite(
        "ana@x.com", now=started, valid_for=lifetime.get(case, timedelta(days=7))
    )
    assert invitation.is_valid(started)
    if case == "revoked":
        invitation.status = InvitationStatus.REVOKED
    if case == "already_accepted":
        invitation.status = InvitationStatus.ACCEPTED

    rejection = rejection_of(identity())

    assert rejection.code == IdentityErrorCode.NOT_INVITED
    assert not User.objects.exists()
    assert not AuthSession.objects.exists()
    assert ports.audit.events == []
    assert ports.invitations.calls == ["find_valid_invitations"]


@pytest.mark.parametrize("google_email", ["ana@x.com", "Ana@X.com", " ANA@X.COM "])
def test_AC_IDA_31_invitation_matches_after_trim_and_lowercase(
    ports: Ports, google_email: str
) -> None:
    invitation = ports.invitations.invite(" Ana@X.com ", now=NOW)

    user = provision_user(identity(email=google_email), now=NOW)

    assert user.email == "ana@x.com"
    assert invitation.accepted_by == user.pk


@pytest.mark.parametrize("google_email", ["ana+1@x.com", "a.na@x.com", "an.a@x.com", "ana@x.co"])
def test_AC_IDA_31_alias_is_not_invited(ports: Ports, google_email: str) -> None:
    ports.invitations.invite(" Ana@X.com ", now=NOW)

    rejection = rejection_of(identity(email=google_email))

    assert rejection.code == IdentityErrorCode.NOT_INVITED
    assert_nothing_created(ports)


# --- Q-126: a write PostgreSQL refuses is the race only when a unique index refused it ----------


def test_Q_126_unstorable_email_of_a_new_user_is_rejected_not_retried(
    ports: Ports, capsys: pytest.CaptureFixture[str]
) -> None:
    # ``users_email_normalized`` fails: PostgreSQL would lowercase the address further.
    ports.invitations.invite("ana@x.com", now=NOW)
    capsys.readouterr()

    rejection = rejection_of(unchecked_identity("ANA@x.com"))

    assert rejection.code == IdentityErrorCode.GOOGLE_AUTH_FAILED
    assert rejection.user_id is None
    assert rejection.__cause__ is None
    assert rejection.__context__ is None
    assert_nothing_created(ports)
    assert ports.invitations.calls == []
    output = capsys.readouterr().out
    [line] = [json.loads(text) for text in output.splitlines()]
    assert (line["message"], line["reason"]) == ("auth.email_not_storable", "google_auth_failed")
    assert line["detail"] == "email_not_storable"
    assert "ANA@x.com" not in output
    assert SUB not in output


def test_Q_126_unstorable_email_of_a_known_user_is_rejected_not_a_collision(
    ports: Ports, capsys: pytest.CaptureFixture[str]
) -> None:
    user = User.objects.create_user(google_sub=SUB, email="ana@x.com", display_name="Old")
    capsys.readouterr()

    rejection = rejection_of(unchecked_identity("NUEVA@x.com"))

    assert rejection.code == IdentityErrorCode.GOOGLE_AUTH_FAILED
    assert rejection.user_id == user.pk
    assert rejection.__context__ is None
    user.refresh_from_db()
    assert (user.email, user.display_name, user.last_login_at) == ("ana@x.com", "Old", None)
    assert ports.audit.events == []
    assert ports.invitations.calls == []
    output = capsys.readouterr().out
    assert "NUEVA@x.com" not in output
    assert SUB not in output


def test_AC_IDA_02_unique_violation_on_the_email_retries_into_identity_conflict(
    ports: Ports, monkeypatch: pytest.MonkeyPatch
) -> None:
    # design.md §4.3: the email is taken by another ``sub`` between the read and the INSERT.
    User.objects.create_user(google_sub=OTHER_SUB, email="ana@x.com")
    ports.invitations.invite("ana@x.com", now=NOW)
    real = user_provisioning.get_by_email
    reads: list[str] = []

    def blind_once(email: str, **kwargs: Any) -> User | None:
        reads.append(email)
        return None if len(reads) == 1 else real(email, **kwargs)

    monkeypatch.setattr(user_provisioning, "get_by_email", blind_once)

    rejection = rejection_of(identity())

    assert rejection.code == IdentityErrorCode.IDENTITY_CONFLICT
    assert len(reads) == 2
    assert list(User.objects.values_list("google_sub", flat=True)) == [OTHER_SUB]
    assert ports.invitations.calls == []
    assert ports.audit.events == []


def test_AC_IDA_02_a_race_lost_twice_fails_without_personal_data(
    ports: Ports, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # One retry, not a loop: a user that is refused and yet never found is not the race of §4.3.
    User.objects.create_user(google_sub=SUB, email="ana@x.com")
    monkeypatch.setattr(user_provisioning, "get_by_sub", lambda *_a, **_k: None)
    monkeypatch.setattr(user_provisioning, "get_by_email", lambda *_a, **_k: None)
    capsys.readouterr()

    with pytest.raises(UserProvisioningError) as raised:
        provision_user(identity(), now=NOW)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert "ana@x.com" not in str(raised.value)
    assert SUB not in str(raised.value)
    assert User.objects.count() == 1
    assert ports.invitations.calls == []
    assert capsys.readouterr().out == ""
