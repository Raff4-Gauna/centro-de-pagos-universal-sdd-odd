"""``tenancy_create_org`` (RF-TEN-07, RN-TEN-10, AC-TEN-22, AC-TEN-40, AC-IDA-32; design.md §4.5).

The command runs as the operator would, through ``call_command``, with the one operator of the
test settings (``PLATFORM_OPERATOR_EMAILS``). The link comes from its stdout, the only place the
token exists; accepting goes through the real services (by token, from the session) and the real
first login (``IDENTITY_INVITATION_PORT`` at its default, the real port). Everything is read back
with ``unscoped(PLATFORM)``, never through the code under test.
"""

from __future__ import annotations

import getpass
import re
import threading
from collections.abc import Iterator
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.common.audit.port import AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.identity.models import User
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import hash_token
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.services.audit import AUDIT_TRIGGERS
from apps.tenancy.services.invitation_accept import accept_by_token, accept_from_session
from apps.tenancy.services.platform_org import create_platform_org
from tests.identity.api.login_flow import EMAIL, Flow, flow, make_user
from tests.identity.test_login_with_real_port import REAL_PORT
from tests.identity.test_refresh_concurrency import PATIENCE
from tests.tenancy.api.probe import PLATFORM, add_member, new_org
from tests.tenancy.invitation_setup import invitee, memberships

__all__ = ["flow"]

pytestmark = pytest.mark.django_db

OPERATOR = "ops@hub.test"
LINK = re.compile(r"^http://localhost:3000/invitacion#token=(?P<token>[A-Za-z0-9_-]+)$", re.M)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingSink]:
    monkeypatch.setattr(getpass, "getuser", lambda: "deploy")
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def create_org(*, key: str = "acme-2026", name: str = "Acme", email: str = EMAIL, **kw: str) -> str:
    out = StringIO()
    operator = kw.get("operator", OPERATOR)
    args = ["--key", key, "--name", name, "--owner-email", email, "--operator", operator]
    call_command("tenancy_create_org", *args, stdout=out)
    return out.getvalue()


def token_of(output: str) -> str:
    [match] = LINK.finditer(output)
    return match.group("token")


def organization() -> Organization:
    return Organization.objects.unscoped(PLATFORM).get(platform_creation_key="acme-2026")


def invitations(org: Organization) -> list[tuple[Any, ...]]:
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=org).order_by("created_at")
    fields = ("email", "role", "status", "purpose", "invited_by_user", "invited_by_operator")
    return list(rows.values_list(*fields))


def members_of(org: Organization) -> list[tuple[Any, ...]]:
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=org)
    return list(rows.values_list("user_id", "role", "status"))


def counts() -> tuple[int, int, int]:
    return (
        Organization.objects.unscoped(PLATFORM).count(),
        Invitation.objects.unscoped(PLATFORM).count(),
        Membership.objects.unscoped(PLATFORM).count(),
    )


def owner_pending(email: str = EMAIL) -> tuple[Any, ...]:
    return (email, "owner", "pending", "first_owner", None, OPERATOR)


def test_AC_TEN_22_org_without_memberships_plus_invitation(recorded: RecordingSink) -> None:
    output = create_org(email="  Ana@Example.com ")

    org = organization()
    assert (org.name, org.status, org.created_by_operator) == ("Acme", "active", OPERATOR)
    assert members_of(org) == []
    assert invitations(org) == [owner_pending()]
    stored = Invitation.objects.unscoped(PLATFORM).get(organization=org)
    assert stored.token_hash == hash_token(token_of(output))
    assert f"Organization {org.pk} created" in output
    assert [(e.action, e.organization_id) for e in recorded.events] == [
        (TenancyAuditAction.ORGANIZATION_CREATED, org.pk),
        (TenancyAuditAction.INVITATION_CREATED, org.pk),
    ]
    assert recorded.events[1].metadata == {
        "invitation_id": str(stored.pk),
        "role": "owner",
        "purpose": "first_owner",
        "os_user": "deploy",
    }


def test_AC_TEN_22_accept_gives_one_owner(recorded: RecordingSink) -> None:
    token = token_of(create_org())
    ana = make_user()

    accepted = accept_by_token(token, invitee(ana))

    org = organization()
    assert (accepted.organization_id, accepted.role) == (org.pk, Role.OWNER)
    assert members_of(org) == [(ana.pk, "owner", "active")]


def test_AC_TEN_40_existing_user_gets_invitation_not_membership(recorded: RecordingSink) -> None:
    ana = make_user()
    other = new_org("A")
    add_member(other, ana, Role.VIEWER)

    create_org()

    org = organization()
    assert invitations(org) == [owner_pending()]
    assert members_of(org) == []
    assert memberships(ana) == [(other.pk, "viewer", "active", None)]


@pytest.mark.integration
def test_AC_TEN_40_next_login_does_not_accept(
    flow: Flow, recorded: RecordingSink, settings: SettingsWrapper
) -> None:
    settings.IDENTITY_INVITATION_PORT = REAL_PORT  # the flow installs the in-memory one
    ana = make_user()
    add_member(new_org("A"), ana, Role.VIEWER)
    create_org()

    response = flow.login()

    assert response.status_code == 200
    assert [user.pk for user in User.objects.all()] == [ana.pk]
    org = organization()
    assert members_of(org) == []
    assert invitations(org) == [owner_pending()]


def test_AC_TEN_40_accept_from_session_gives_one_owner(recorded: RecordingSink) -> None:
    ana = make_user()
    other = new_org("A")
    add_member(other, ana, Role.VIEWER)
    create_org()
    org = organization()
    pending = Invitation.objects.unscoped(PLATFORM).get(organization=org)

    accepted = accept_from_session(pending.pk, invitee(ana))

    assert (accepted.organization_id, accepted.role) == (org.pk, Role.OWNER)
    assert members_of(org) == [(ana.pk, "owner", "active")]
    assert sorted(row[:2] for row in memberships(ana)) == sorted(
        [(other.pk, "viewer"), (org.pk, "owner")]
    )


def test_AC_IDA_32_bootstrap_command_audited(recorded: RecordingSink) -> None:
    with capture_logs() as logs:
        output = create_org()

    token = token_of(output)
    assert AUDIT_TRIGGERS[TenancyAuditAction.ORGANIZATION_CREATED] is create_platform_org
    actors = {(e.actor.kind, e.actor.name, e.metadata["os_user"]) for e in recorded.events}
    assert actors == {(AuditActorKind.PLATFORM_OPERATOR, OPERATOR, "deploy")}
    assert len(recorded.events) == 2
    trail = repr(recorded.events) + repr(logs)
    assert token not in trail
    assert EMAIL not in trail
    assert output.count(token) == 1
    assert [entry["event"] for entry in logs] == ["tenancy.platform_org_created"]


def repeated(sink: RecordingSink) -> list[tuple[Any, ...]]:
    """Every ``organization.create_repeated``: (organization, actor, metadata)."""
    return [
        (e.organization_id, e.actor.kind, e.actor.name, e.metadata)
        for e in sink.events
        if e.action == TenancyAuditAction.ORGANIZATION_CREATE_REPEATED
    ]


def repeat_of(org: Organization, outcome: str) -> tuple[Any, ...]:
    metadata = {"outcome": outcome, "os_user": "deploy"}
    return (org.pk, AuditActorKind.PLATFORM_OPERATOR, OPERATOR, metadata)


def test_Q_123_repeat_creates_nothing(recorded: RecordingSink) -> None:
    create_org()
    before, events = counts(), len(recorded.events)

    with capture_logs() as logs:
        again = create_org(name=" Acme ", email="ANA@example.com")

    assert counts() == before
    assert "already exists" in again
    assert "#token=" not in again
    # Q-235: the repeat is audited, with exactly one event and nothing else.
    assert len(recorded.events) == events + 1
    assert repeated(recorded) == [repeat_of(organization(), "no_change")]
    assert EMAIL not in repr(recorded.events) + repr(logs)
    assert [(entry["event"], entry["outcome"]) for entry in logs] == [
        ("tenancy.platform_org_repeated", "no_change")
    ]


@pytest.mark.parametrize("changed", [{"name": "Acme SA"}, {"email": "beto@example.com"}])
def test_Q_235_conflict_is_audited_and_writes_nothing(
    recorded: RecordingSink, changed: dict[str, str]
) -> None:
    create_org()
    before, events = counts(), len(recorded.events)

    with pytest.raises(CommandError) as raised:
        create_org(**changed)

    assert raised.value.returncode == 1
    assert counts() == before
    assert len(recorded.events) == events + 1
    assert repeated(recorded) == [repeat_of(organization(), "conflict")]
    assert "beto@example.com" not in repr(recorded.events) + str(raised.value)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_Q_123_two_runs_at_once_create_one_organization(recorded: RecordingSink) -> None:
    start = threading.Barrier(3)
    outputs: list[str] = []

    def run() -> None:
        try:
            start.wait(PATIENCE)
            outputs.append(create_org())
        finally:
            connection.close()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(PATIENCE)

    assert len(outputs) == 3
    assert sum("#token=" in output for output in outputs) == 1
    assert counts() == (1, 1, 0)
    org = organization()
    assert invitations(org) == [owner_pending()]
    assert repeated(recorded) == [repeat_of(org, "no_change")] * 2


@pytest.mark.parametrize(
    "args",
    [
        {"operator": "intruso@hub.test"},
        {"operator": " "},
        {"key": " "},
        {"key": "k" * 65},
        {"name": " "},
        {"name": "n" * 121},
        {"email": "not-an-email"},
    ],
)
def test_RF_TEN_07_bad_arguments_exit_2_and_write_nothing(
    recorded: RecordingSink, args: dict[str, str]
) -> None:
    with pytest.raises(CommandError) as raised:
        create_org(**args)

    assert raised.value.returncode == 2
    assert counts() == (0, 0, 0)
    assert recorded.events == []
    assert "intruso" not in str(raised.value)


def test_RF_TEN_07_no_operator_configured_runs_nothing(
    recorded: RecordingSink, settings: SettingsWrapper
) -> None:
    settings.PLATFORM_OPERATOR_EMAILS = ()

    with pytest.raises(CommandError) as raised:
        create_org()

    assert raised.value.returncode == 2
    assert counts() == (0, 0, 0)


def test_RF_TEN_07_operator_is_normalized(recorded: RecordingSink) -> None:
    create_org(operator="  OPS@Hub.Test ")

    assert organization().created_by_operator == OPERATOR
    assert {e.actor.name for e in recorded.events} == {OPERATOR}


def test_RF_TEN_07_without_frontend_base_url_writes_nothing(
    recorded: RecordingSink, settings: SettingsWrapper
) -> None:
    settings.FRONTEND_BASE_URL = ""

    with pytest.raises(CommandError) as raised:
        create_org()

    assert raised.value.returncode == 1
    assert counts() == (0, 0, 0)
    assert recorded.events == []
