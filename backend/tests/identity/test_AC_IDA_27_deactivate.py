"""``deactivate_user`` and ``reactivate_user`` (RF-IDA-08, RN-IDA-07, RN-IDA-23; design.md §6.5).

The commands run as the operator would, through ``call_command``; each session is opened with
``open_session`` and its JWT issued as a login would, and the request after the command goes through
the real route with that Bearer (``HubJWTAuthentication``), so the ``401`` is the real one.
"""

from __future__ import annotations

import json
from io import StringIO
from typing import Any
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.domain.audit_events import AuditActorType, AuditResult, IdentityAuditAction
from apps.identity.management.commands import _user_status
from apps.identity.models import AuthSession, RevokeReason, SessionStatus, User
from apps.identity.services.session_lifecycle import OpenedSession, open_session
from apps.identity.tokens.access_token import issue_access_token
from tests.identity.fakes import Ports, install_ports

pytestmark = pytest.mark.django_db

ME = "/api/me/"
EMAIL = "ana@example.com"
OPERATOR = "Ops Team"


class Device:
    def __init__(self, user: User) -> None:
        self.opened: OpenedSession = open_session(user, now=timezone.now())
        self.id = self.opened.session.pk
        token = issue_access_token(user_id=user.pk, session_id=self.id)
        self.headers = {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ports(settings: SettingsWrapper, monkeypatch: pytest.MonkeyPatch) -> Ports:
    monkeypatch.setattr(_user_status.getpass, "getuser", lambda: "deploy")
    return install_ports(settings)


@pytest.fixture
def ana() -> User:
    return User.objects.create_user(google_sub="sub-ana", email=EMAIL)


def run(command: str, *args: str) -> str:
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def deactivate(*args: str) -> str:
    return run("deactivate_user", *args, "--operator", OPERATOR)


def reactivate(*args: str) -> str:
    return run("reactivate_user", *args, "--operator", OPERATOR)


def code_of(response: Any) -> str:
    assert response.status_code == 401
    code: str = json.loads(response.content)["code"]
    return code


def events(ports: Ports, action: IdentityAuditAction) -> list[Any]:
    return [event for event in ports.audit.events if event.action == action]


def test_AC_IDA_27_two_sessions_revoked_and_next_request_401(
    client: Client, ports: Ports, ana: User
) -> None:
    laptop, phone = Device(ana), Device(ana)
    beto = User.objects.create_user(google_sub="sub-beto", email="beto@example.com")
    bystander = Device(beto)
    assert client.get(ME, headers=laptop.headers).status_code == 200

    with capture_logs() as logs:
        out = deactivate("--email", "  Ana@Example.com ", "--reason", "left the company")

    assert out.strip() == f"User {ana.pk} deactivated; 2 session(s) revoked."
    ana.refresh_from_db()
    assert ana.is_active is False
    assert ana.deactivated_at is not None
    for device in (laptop, phone):
        session = AuthSession.objects.get(pk=device.id)
        assert (session.status, session.revoke_reason) == (
            SessionStatus.REVOKED,
            RevokeReason.USER_DEACTIVATED,
        )
        # The JWT has not expired; the session check of every request rejects it.
        assert code_of(client.get(ME, headers=device.headers)) == "session_revoked"
    assert client.get(ME, headers=bystander.headers).status_code == 200
    actor = {"operator": OPERATOR, "os_user": "deploy"}
    [deactivated] = events(ports, IdentityAuditAction.USER_DEACTIVATED)
    assert deactivated.result == AuditResult.SUCCESS
    assert deactivated.reason == "left the company"
    assert deactivated.actor_type == AuditActorType.PLATFORM_OPERATOR
    assert (deactivated.actor_id, deactivated.organization_id) == (None, None)
    assert deactivated.metadata == {"user_id": str(ana.pk), "revoked_sessions": 2, **actor}
    revoked = events(ports, IdentityAuditAction.SESSION_REVOKED)
    assert [event.metadata for event in revoked] == [
        {"sid": str(session_id), "user_id": str(ana.pk), **actor}
        for session_id in sorted((laptop.id, phone.id))
    ]
    assert {(e.reason, e.actor_type) for e in revoked} == {
        ("user_deactivated", AuditActorType.PLATFORM_OPERATOR)
    }
    # Neither the output nor the logs carry the email.
    assert EMAIL not in out
    assert EMAIL not in repr(logs)
    [log] = [entry for entry in logs if entry["event"] == "identity.user_deactivated"]
    assert (log["result"], log["revoked"], log["user_id"]) == ("deactivated", 2, str(ana.pk))


def test_AC_IDA_27_reactivate_does_not_revive(client: Client, ports: Ports, ana: User) -> None:
    device = Device(ana)
    deactivate("--user-id", str(ana.pk))

    out = reactivate("--user-id", str(ana.pk))

    assert out.strip() == f"User {ana.pk} reactivated; they have to log in again."
    ana.refresh_from_db()
    assert (ana.is_active, ana.deactivated_at) == (True, None)
    assert AuthSession.objects.get(pk=device.id).status == SessionStatus.REVOKED
    assert code_of(client.get(ME, headers=device.headers)) == "session_revoked"
    [reactivated] = events(ports, IdentityAuditAction.USER_REACTIVATED)
    assert reactivated.actor_type == AuditActorType.PLATFORM_OPERATOR
    assert reactivated.reason is None
    assert reactivated.metadata == {
        "user_id": str(ana.pk),
        "operator": OPERATOR,
        "os_user": "deploy",
    }
    # A new login is a new session, and it works.
    assert client.get(ME, headers=Device(ana).headers).status_code == 200


def test_AC_IDA_27_repeating_either_is_an_informed_noop(ports: Ports, ana: User) -> None:
    Device(ana)
    deactivate("--email", EMAIL)
    sessions = AuthSession.objects.filter(user=ana).order_by("pk")
    before = (list(sessions.values_list("status", "ended_at")), len(ports.audit.events))

    again = deactivate("--email", EMAIL)

    assert again.strip() == f"User {ana.pk} was already inactive; nothing changed."
    assert (list(sessions.values_list("status", "ended_at")), len(ports.audit.events)) == before
    reactivate("--email", EMAIL)
    audited = len(ports.audit.events)
    assert reactivate("--email", EMAIL).strip() == (
        f"User {ana.pk} was already active; nothing changed."
    )
    assert len(ports.audit.events) == audited


def test_AC_IDA_27_unknown_user_exits_1_without_echoing(ports: Ports, ana: User) -> None:
    for target in (("--email", "nobody@example.com"), ("--user-id", str(uuid4()))):
        with pytest.raises(CommandError) as raised:
            deactivate(*target)
        assert raised.value.returncode == 1
        assert str(raised.value) == "No user matches."
    assert ports.audit.events == []
    assert User.objects.get(pk=ana.pk).is_active


@pytest.mark.parametrize(
    "args",
    [
        ("--email", EMAIL, "--operator", "   "),
        ("--email", EMAIL, "--operator", "x" * 151),
        ("--email", EMAIL, "--operator", OPERATOR, "--reason", "x" * 201),
    ],
)
def test_AC_IDA_27_invalid_operator_or_reason_exits_2(
    ports: Ports, ana: User, args: tuple[str, ...]
) -> None:
    with pytest.raises(CommandError) as raised:
        run("deactivate_user", *args)

    assert raised.value.returncode == 2
    assert User.objects.get(pk=ana.pk).is_active
    assert ports.audit.events == []


@pytest.mark.parametrize(
    "args",
    [
        ("--operator", OPERATOR),
        ("--email", EMAIL, "--user-id", str(uuid4()), "--operator", OPERATOR),
        ("--email", EMAIL),
        ("--user-id", "not-a-uuid", "--operator", OPERATOR),
    ],
)
def test_AC_IDA_27_bad_arguments_are_refused(
    ports: Ports, ana: User, args: tuple[str, ...]
) -> None:
    with pytest.raises(CommandError):
        run("deactivate_user", *args)

    assert User.objects.get(pk=ana.pk).is_active


def test_AC_IDA_27_os_user_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_user() -> str:
        raise OSError("no login name")

    monkeypatch.setattr(_user_status.getpass, "getuser", no_user)

    assert _user_status.os_user() == "unknown"


def test_AC_IDA_27_audit_failure_rolls_everything_back(
    monkeypatch: pytest.MonkeyPatch, ports: Ports, ana: User
) -> None:
    device = Device(ana)

    def broken(event: object) -> None:
        raise RuntimeError("audit store down")

    monkeypatch.setattr(ports.audit, "record", broken)

    with pytest.raises(RuntimeError):
        deactivate("--email", EMAIL)

    assert User.objects.get(pk=ana.pk).is_active
    assert AuthSession.objects.get(pk=device.id).status == SessionStatus.ACTIVE
