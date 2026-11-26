"""Q-241 (dueño, 2026-11-21): an ``--operator`` not in the allowlist goes to the security log.

Every operator command of ``apps.tenancy`` checks ``--operator`` against
``PLATFORM_OPERATOR_EMAILS``. When it is not there the run ends with exit ``2`` and, before that,
writes exactly one WARNING ``tenancy.platform_operator_refused`` with the name of the command and
the user of the operating system: never the email nor the value given. It is not an audit event of
any company (nothing reaches the audit sink) and it writes nothing else. A valid operator, or an
exit ``2`` for another argument, logs no such line. The log is read with ``capture_logs``; the
audit with the recording sink, never through the code under test.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

import pytest
from django.core.management.base import CommandError
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.common.audit.sinks import RecordingSink
from apps.tenancy.models import Invitation, Organization
from tests.tenancy.api.probe import PLATFORM
from tests.tenancy.commands.test_create_org import OPERATOR, create_org, organization, recorded
from tests.tenancy.commands.test_owner_invite import owner_invite
from tests.tenancy.commands.test_owner_recovery import owner_recovery
from tests.tenancy.commands.test_set_org_status import set_status
from tests.tenancy.commands.test_support_access import support_access

__all__ = ["recorded"]

pytestmark = pytest.mark.django_db

REFUSED_EVENT = "tenancy.platform_operator_refused"
INTRUDER = "intruso@hub.test"

Run = Callable[[str], object]

# Every operator command of apps.tenancy, run with ``operator`` (the others valid).
COMMANDS: dict[str, Run] = {
    "tenancy_create_org": lambda operator: create_org(key="otra-2026", operator=operator),
    "tenancy_owner_invite": lambda operator: owner_invite("reissue", operator=operator),
    "tenancy_set_org_status": lambda operator: set_status(
        organization(), "suspended", operator=operator
    ),
    "tenancy_support_access": lambda operator: support_access(operator=operator),
    "tenancy_owner_recovery": lambda operator: owner_recovery(operator=operator),
}


def state() -> tuple[int, int, str]:
    """What a refused run must leave as it was: organizations, invitations and the status."""
    return (
        Organization.objects.unscoped(PLATFORM).count(),
        Invitation.objects.unscoped(PLATFORM).count(),
        organization().status,
    )


def run_refused(run: Callable[[], object]) -> tuple[CommandError, list[MutableMapping[str, Any]]]:
    with capture_logs() as logs, pytest.raises(CommandError) as raised:
        run()
    return raised.value, logs


def exit_of(run: Callable[[], object]) -> int:
    try:
        run()
    except CommandError as error:
        return error.returncode
    return 0


def refusals(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == REFUSED_EVENT]


@pytest.fixture
def created(recorded: RecordingSink) -> RecordingSink:
    """The organization ``tenancy_create_org`` leaves, with the audit of its creation cleared."""
    create_org()
    recorded.clear()
    return recorded


@pytest.mark.parametrize("value", [INTRUDER, "ops@hub.test.evil", " "])
@pytest.mark.parametrize("command", COMMANDS)
def test_Q_241_a_refused_operator_is_logged_once_without_its_value(
    created: RecordingSink, command: str, value: str
) -> None:
    before = state()

    error, logs = run_refused(lambda: COMMANDS[command](value))

    assert error.returncode == 2
    assert refusals(logs) == [
        {"event": REFUSED_EVENT, "log_level": "warning", "command": command, "os_user": "deploy"}
    ]
    assert created.events == []  # not an audit event of any company
    assert state() == before
    leaked = repr(logs) + str(error)
    for secret in {value.strip(), OPERATOR, "intruso", "evil"} - {""}:
        assert secret not in leaked


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_241_an_empty_allowlist_refuses_and_logs_every_operator(
    created: RecordingSink, settings: SettingsWrapper, command: str
) -> None:
    settings.PLATFORM_OPERATOR_EMAILS = []

    error, logs = run_refused(lambda: COMMANDS[command](OPERATOR))

    assert error.returncode == 2
    assert [(e["command"], e["os_user"]) for e in refusals(logs)] == [(command, "deploy")]
    assert created.events == []
    assert OPERATOR not in repr(logs)


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_241_a_valid_operator_logs_no_refusal(created: RecordingSink, command: str) -> None:
    with capture_logs() as logs:
        exit_code = exit_of(lambda: COMMANDS[command](OPERATOR))

    assert exit_code in {0, 1}  # done, or refused by the command itself (not by the operator)
    assert refusals(logs) == []


@pytest.mark.parametrize(
    "run",
    [
        lambda: owner_invite("reissue", org="acme"),
        lambda: set_status(organization(), "suspended", reason=" "),
        lambda: support_access(email="no-es-un-email"),
    ],
)
def test_Q_241_another_bad_argument_logs_no_refusal(
    created: RecordingSink, run: Callable[[], object]
) -> None:
    error, logs = run_refused(run)

    assert error.returncode == 2
    assert refusals(logs) == []
