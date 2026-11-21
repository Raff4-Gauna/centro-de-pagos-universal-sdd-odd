"""Retries of the invitation email and its system check (RF-TEN-05, Q-207, clarifications.md §3).

A failed send is retried asynchronously (review of PR #137). What the retried message carries is
caught at ``before_task_publish`` with the broker's ``publish`` patched out, from a request as a
worker builds it (not eager: an eager retry publishes nothing). The last failure is the provider's
own error, never ``MaxRetriesExceededError`` with the kwargs in its text. ``tenancy.E001`` stops a
deploy that turns the flag on without an email backend.
"""

from __future__ import annotations

import smtplib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from celery.exceptions import Retry
from celery.signals import before_task_publish
from django.conf import global_settings
from django.core.checks import run_checks
from kombu.messaging import Producer
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common.tenancy.current import tenant_scope
from apps.tenancy import tasks
from apps.tenancy.checks import EMAIL_FLAG, EMAIL_WITHOUT_PROVIDER
from apps.tenancy.tasks import EMAIL_MAX_RETRIES, send_invitation_email
from tests.tenancy.api.probe import new_org
from tests.tenancy.invitation_setup import issue
from tests.tenancy.locking import system_ctx

pytestmark = pytest.mark.django_db

TOKEN = "not-a-real-token-but-the-secret-of-this-test"  # noqa: S105 - a fake
LINK = f"http://localhost:3000/invitacion#token={TOKEN}"
EXPIRES = "2026-11-21T12:15:00+00:00"


@pytest.fixture
def flag_on(settings: SettingsWrapper) -> None:
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, EMAIL_FLAG: True}


@pytest.fixture
def smtp_down(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise smtplib.SMTPServerDisconnected("connection closed")

    monkeypatch.setattr(tasks, "send_mail", fail)
    return calls


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """The headers of every message published; the broker never gets them."""
    messages: list[dict[str, Any]] = []

    def catch(headers: Any = None, **kwargs: Any) -> None:
        messages.append(dict(headers or {}))

    monkeypatch.setattr(Producer, "publish", lambda self, *args, **kwargs: None)
    before_task_publish.connect(catch, weak=False, dispatch_uid="test_email_retry")
    yield messages
    before_task_publish.disconnect(dispatch_uid="test_email_retry")


def job_for(organization_id: uuid.UUID, invitation_id: uuid.UUID) -> dict[str, str]:
    return {
        "organization_id": str(organization_id),
        "invitation_id": str(invitation_id),
        "accept_url": LINK,
    }


@pytest.mark.usefixtures("flag_on")
def test_RF_TEN_05_a_retry_keeps_the_link_redacted_and_the_expiry(
    smtp_down: list[object], published: list[dict[str, Any]]
) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    job = job_for(org.id, invitation.pk)
    send_invitation_email.push_request(
        id=str(uuid.uuid4()),
        retries=0,
        is_eager=False,
        called_directly=False,
        kwargs=job,
        expires=EXPIRES,
        delivery_info={},
        headers={},
    )
    try:
        with tenant_scope(system_ctx(org.id)), pytest.raises(Retry):
            send_invitation_email.run(**job)
    finally:
        send_invitation_email.pop_request()

    (headers,) = published
    assert len(smtp_down) == 1
    assert headers["retries"] == 1
    assert headers["expires"] == EXPIRES  # the original deadline: a retry never outlives it
    assert "[redacted]" in headers["kwargsrepr"]
    assert TOKEN not in repr(headers)


@pytest.mark.usefixtures("flag_on")
def test_RF_TEN_05_the_last_failure_does_not_carry_the_link(smtp_down: list[object]) -> None:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")

    result = send_invitation_email.apply(kwargs=job_for(org.id, invitation.pk))

    assert len(smtp_down) == EMAIL_MAX_RETRIES + 1
    assert result.failed()
    assert isinstance(result.result, smtplib.SMTPServerDisconnected)
    assert TOKEN not in str(result.result)
    assert TOKEN not in repr(result.result)
    assert TOKEN not in str(result.traceback or "")


# --- tenancy.E001 ---------------------------------------------------------------------------------


def e001(settings: SettingsWrapper, *, on: bool, backend: str) -> list[str]:
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, EMAIL_FLAG: on}
    settings.EMAIL_BACKEND = backend
    return [m.id for m in run_checks() if m.id == EMAIL_WITHOUT_PROVIDER]


def test_RF_TEN_05_flag_on_without_an_email_backend_stops(settings: SettingsWrapper) -> None:
    assert e001(settings, on=True, backend=global_settings.EMAIL_BACKEND) == ["tenancy.E001"]


def test_RF_TEN_05_flag_off_never_stops_the_start(settings: SettingsWrapper) -> None:
    assert e001(settings, on=False, backend=global_settings.EMAIL_BACKEND) == []


def test_RF_TEN_05_flag_on_with_a_backend_starts(settings: SettingsWrapper) -> None:
    console = "django.core.mail.backends.console.EmailBackend"
    assert e001(settings, on=True, backend=console) == []
