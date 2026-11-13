"""``services/user_provisioning.py``, case (a) and the identity conflict (design.md §4.2, step 7).

RN-IDA-21 against the real PostgreSQL: the unique index on ``email`` is part of the rule. Rejections
are only raised here; ``login_complete`` (T-IDA-13) audits them after its rollback.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
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
from apps.identity.ports.audit import AuditEvent
from apps.identity.ports.invitations import InvitationRef
from apps.identity.ports.registry import get_membership_selector
from apps.identity.services import user_provisioning
from apps.identity.services.session_lifecycle import open_session
from apps.identity.services.user_provisioning import provision_user

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SUB = "1000000000000000000001"
OTHER_SUB = "1000000000000000000002"
NEW_SUB = "1000000000000000000003"

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class RecordingAuditPort:
    events: list[AuditEvent] = []  # noqa: RUF012 - reset by the fixture, read by the tests

    def record(self, event: AuditEvent) -> None:
        RecordingAuditPort.events.append(event)


class ForbiddenInvitationPort:
    """Q-121: case (a) must never get here."""

    calls: list[str] = []  # noqa: RUF012 - reset by the fixture, read by the tests

    def find_valid_invitations(
        self, email_normalized: str, *, now: datetime
    ) -> list[InvitationRef]:
        ForbiddenInvitationPort.calls.append("find_valid_invitations")
        return [InvitationRef(invitation_id=uuid.uuid4(), organization_id=uuid.uuid4())]

    def accept_invitations(
        self, invitations: Sequence[InvitationRef], user_id: uuid.UUID, *, now: datetime
    ) -> None:
        ForbiddenInvitationPort.calls.append("accept_invitations")


@pytest.fixture(autouse=True)
def ports(settings: SettingsWrapper) -> None:
    RecordingAuditPort.events = []
    ForbiddenInvitationPort.calls = []
    settings.IDENTITY_AUDIT_PORT = f"{__name__}.RecordingAuditPort"
    settings.IDENTITY_INVITATION_PORT = f"{__name__}.ForbiddenInvitationPort"


def identity(sub: str = SUB, email: str = "ana@x.com", **claims: Any) -> VerifiedIdentity:
    values: dict[str, Any] = {"email_verified": True, "name": "Ana", "picture": ""}
    return evaluate_identity(sub=sub, email=email, **{**values, **claims})


def make_user(sub: str = SUB, email: str = "ana@x.com", **fields: Any) -> User:
    user = User.objects.create_user(google_sub=sub, email=email)
    if fields:
        User.objects.filter(pk=user.pk).update(**fields)
        user.refresh_from_db()
    return user


def rejection_of(verified: VerifiedIdentity) -> LoginRejectedError:
    with pytest.raises(LoginRejectedError) as raised:
        provision_user(verified, now=NOW)
    return raised.value


def actions() -> list[IdentityAuditAction]:
    return [event.action for event in RecordingAuditPort.events]


def log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_AC_IDA_29_email_change_free() -> None:
    user = make_user(email="a@x.com")

    provisioned = provision_user(identity(email="b@x.com"), now=NOW)

    assert provisioned.pk == user.pk
    user.refresh_from_db()
    assert user.email == "b@x.com"
    [event] = RecordingAuditPort.events
    assert event.action == IdentityAuditAction.EMAIL_CHANGED
    assert event.result == AuditResult.SUCCESS
    assert (event.actor_type, event.actor_id) == (AuditActorType.USER, user.pk)
    assert event.organization_id is None
    assert event.metadata == {}


def test_AC_IDA_29_collision_keeps_old_email() -> None:
    user = make_user(email="a@x.com")
    make_user(sub=OTHER_SUB, email="b@x.com")

    provisioned = provision_user(identity(email="b@x.com"), now=NOW)

    assert provisioned.pk == user.pk
    user.refresh_from_db()
    assert user.email == "a@x.com"
    assert user.last_login_at == NOW
    [event] = RecordingAuditPort.events
    assert event.action == IdentityAuditAction.EMAIL_CHANGE_COLLISION
    assert (event.actor_type, event.actor_id) == (AuditActorType.USER, user.pk)
    assert event.metadata == {}


def test_AC_IDA_29_collision_found_by_the_unique_index_keeps_old_email(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Someone takes the address between the check and the UPDATE: the index has the last word.
    user = make_user(email="a@x.com")
    make_user(sub=OTHER_SUB, email="b@x.com")
    monkeypatch.setattr(user_provisioning, "get_by_email", lambda *_a, **_k: None)
    capsys.readouterr()

    provisioned = provision_user(identity(email="b@x.com", name="Ana María"), now=NOW)

    assert provisioned.email == "a@x.com"
    user.refresh_from_db()
    assert (user.email, user.display_name) == ("a@x.com", "Ana María")
    assert actions() == [IdentityAuditAction.EMAIL_CHANGE_COLLISION]
    output = capsys.readouterr().out
    assert "b@x.com" not in output
    assert SUB not in output


def test_AC_IDA_29_new_sub_with_taken_email_is_conflict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    owner = make_user(email="a@x.com")
    capsys.readouterr()

    rejection = rejection_of(identity(sub=NEW_SUB, email="a@x.com"))

    assert rejection.code == IdentityErrorCode.IDENTITY_CONFLICT
    assert rejection.user_id is None
    assert list(User.objects.values_list("google_sub", flat=True)) == [SUB]
    assert not AuthSession.objects.exists()
    assert RecordingAuditPort.events == []
    # Even with a valid invitation for that address (AC-IDA-29): the port is never asked.
    assert ForbiddenInvitationPort.calls == []
    lines = log_lines(capsys)
    [alert] = [line for line in lines if line.get("alert") is True]
    assert alert["message"] == "auth.identity_conflict"
    assert alert["outcome"] == "rejected"
    assert alert["reason"] == "identity_conflict"
    assert alert["level"] == "warning"
    assert alert["existing_user_id"] == str(owner.pk)
    text = json.dumps(lines)
    assert "a@x.com" not in text
    assert NEW_SUB not in text


def test_AC_IDA_09_inactive_user_rejected() -> None:
    user = make_user(is_active=False, deactivated_at=NOW, display_name="Old")

    rejection = rejection_of(identity(email="b@x.com", name="New"))

    assert rejection.code == IdentityErrorCode.USER_INACTIVE
    assert rejection.user_id == user.pk
    user.refresh_from_db()
    assert (user.email, user.display_name, user.last_login_at) == ("ana@x.com", "Old", None)
    assert RecordingAuditPort.events == []
    assert ForbiddenInvitationPort.calls == []


def test_AC_IDA_30_no_memberships_still_logs_in() -> None:
    user = make_user()
    assert get_membership_selector().list_active_memberships(user.pk) == []

    with transaction.atomic():
        provisioned = provision_user(identity(), now=NOW)
        opened = open_session(provisioned, now=NOW)

    assert provisioned.pk == user.pk
    assert opened.session.status == SessionStatus.ACTIVE
    assert AuthSession.objects.filter(user=user, status=SessionStatus.ACTIVE).count() == 1
    assert RecordingAuditPort.events == []


@pytest.mark.parametrize("email", ["ana@x.com", "nueva@x.com"])
def test_Q_121_case_a_never_touches_invitations(email: str) -> None:
    make_user()
    provision_user(identity(email=email), now=NOW)
    assert ForbiddenInvitationPort.calls == []


def test_RN_IDA_21_name_and_avatar_follow_google() -> None:
    user = make_user(display_name="Ana", avatar_url="https://old.example.com/a.png")

    provision_user(identity(name="Ana María", picture="https://new.example.com/b.png"), now=NOW)

    user.refresh_from_db()
    assert (user.display_name, user.avatar_url) == ("Ana María", "https://new.example.com/b.png")
    assert user.last_login_at == NOW
    assert RecordingAuditPort.events == []


def test_RN_IDA_21_nul_in_name_or_avatar_never_rejects() -> None:
    # PostgreSQL refuses NUL in text (DataError): login_rules drops it first (domain/profile.py).
    user = make_user()

    provision_user(identity(name="A\x00na", picture="https://x.example.com/\x00.png"), now=NOW)

    user.refresh_from_db()
    assert (user.display_name, user.avatar_url) == ("Ana", "")
