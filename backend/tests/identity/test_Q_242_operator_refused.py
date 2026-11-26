"""Q-242 (dueño, 2026-11-21): the rule of Q-241 holds for the operator commands of identity too.

``deactivate_user`` and ``reactivate_user`` check ``--operator`` against
``PLATFORM_OPERATOR_EMAILS`` (``apps.common.platform_operators``). When it is not there the run
ends with exit ``2`` and, before that, writes exactly one WARNING
``identity.platform_operator_refused`` with the name of the command and the user of the operating
system: never the email nor the value given. It is not an audit event (nothing reaches the audit
port) and the user is left as they were. A valid operator, or an exit for another argument, logs
no such line. The log is read with ``capture_logs``; the audit with the fake port.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any
from uuid import uuid4

import pytest
from django.core.management.base import CommandError
from pytest_django.fixtures import Settings as SettingsWrapper
from structlog.testing import capture_logs

from apps.identity.models import User
from tests.identity.fakes import Ports
from tests.identity.test_AC_IDA_27_deactivate import EMAIL, OPERATOR, ana, ports, run

__all__ = ["ana", "ports"]

pytestmark = pytest.mark.django_db

REFUSED_EVENT = "identity.platform_operator_refused"
COMMANDS = ("deactivate_user", "reactivate_user")


def run_refused(call: Callable[[], object]) -> tuple[CommandError, list[MutableMapping[str, Any]]]:
    with capture_logs() as logs, pytest.raises(CommandError) as raised:
        call()
    return raised.value, logs


def refusals(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == REFUSED_EVENT]


@pytest.mark.parametrize("value", ["intruso@hub.test", "ops@hub.test.evil", " ", "x" * 151])
@pytest.mark.parametrize("command", COMMANDS)
def test_Q_242_a_refused_operator_is_logged_once_without_its_value(
    ports: Ports, ana: User, command: str, value: str
) -> None:
    error, logs = run_refused(lambda: run(command, "--email", EMAIL, "--operator", value))

    assert error.returncode == 2
    assert refusals(logs) == [
        {"event": REFUSED_EVENT, "log_level": "warning", "command": command, "os_user": "deploy"}
    ]
    assert ports.audit.events == []  # not an audit event
    assert User.objects.get(pk=ana.pk).is_active
    leaked = repr(logs) + str(error)
    for secret in {value.strip(), OPERATOR, EMAIL, "intruso", "evil"} - {""}:
        assert secret not in leaked


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_242_an_empty_allowlist_refuses_and_logs_every_operator(
    ports: Ports, ana: User, settings: SettingsWrapper, command: str
) -> None:
    settings.PLATFORM_OPERATOR_EMAILS = []

    error, logs = run_refused(lambda: run(command, "--email", EMAIL, "--operator", OPERATOR))

    assert error.returncode == 2
    assert [(e["command"], e["os_user"]) for e in refusals(logs)] == [(command, "deploy")]
    assert ports.audit.events == []
    assert OPERATOR not in repr(logs)
    assert EMAIL not in repr(logs)


@pytest.mark.parametrize("command", COMMANDS)
def test_Q_242_a_valid_operator_logs_no_refusal(ports: Ports, ana: User, command: str) -> None:
    with capture_logs() as logs:
        run(command, "--email", EMAIL, "--operator", OPERATOR)

    assert refusals(logs) == []
    assert ports.audit.events  # the run itself is audited as before


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        (("--email", EMAIL, "--operator", OPERATOR, "--reason", "x" * 201), 2),
        (("--user-id", str(uuid4()), "--operator", OPERATOR), 1),
    ],
)
def test_Q_242_another_bad_argument_logs_no_refusal(
    ports: Ports, ana: User, command: str, args: tuple[str, ...], exit_code: int
) -> None:
    error, logs = run_refused(lambda: run(command, *args))

    assert error.returncode == exit_code
    assert refusals(logs) == []
