"""The invitation email behind ``TENANCY_INVITATION_EMAIL_ENABLED`` (RF-TEN-05, Q-207, §7).

Off (the default): creating or resending an invitation through the API enqueues nothing, so the
token never reaches the broker; every publish of the process is caught with ``before_task_publish``
and the commit callbacks run, so a late enqueue would show too. On: the email task is enqueued after
the commit with the link redacted in ``kwargsrepr`` and a short ``expires``, and the task sends the
link only while the invitation is ``pending`` (``mailoutbox``: Django's in-memory backend in tests).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from celery.signals import before_task_publish
from django.core import mail
from django.test import Client
from pytest_django.fixtures import Settings as SettingsWrapper

from apps.common import feature_flags
from apps.common.authz.roles import Role
from apps.tenancy.domain.invitations import InvitationStatus
from apps.tenancy.models import Organization
from apps.tenancy.tasks import (
    EMAIL_EXPIRES_SECONDS,
    EMAIL_FLAG,
    queue_invitation_email,
    send_invitation_email,
)
from tests.tenancy.api.invitation_api_setup import ACCEPT_PREFIX, invite, manage, token_of
from tests.tenancy.api.membership_setup import member
from tests.tenancy.api.probe import new_org
from tests.tenancy.invitation_setup import issue, set_status
from tests.tenancy.locking import system_ctx

pytestmark = pytest.mark.django_db

BODY = {"email": "ana@hub.test", "role": "operator"}
LINK = f"{ACCEPT_PREFIX}not-a-real-token"


@pytest.fixture
def org_a() -> Organization:
    return new_org("Acme")


@pytest.fixture
def published() -> Iterator[list[dict[str, Any]]]:
    """Every message this process publishes to the broker, with its body and headers."""
    messages: list[dict[str, Any]] = []

    def catch(body: Any = None, headers: Any = None, **kwargs: Any) -> None:
        messages.append({"body": body, "headers": headers})

    before_task_publish.connect(catch, weak=False, dispatch_uid="test_invitation_email_flag")
    yield messages
    before_task_publish.disconnect(dispatch_uid="test_invitation_email_flag")


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The options of each ``send_invitation_email.apply_async``: caught, nothing goes out."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        send_invitation_email, "apply_async", lambda **options: calls.append(options)
    )
    return calls


def flag(settings: SettingsWrapper, on: bool) -> None:
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, EMAIL_FLAG: on}


def test_the_flag_is_registered_and_off_by_default(settings: SettingsWrapper) -> None:
    assert EMAIL_FLAG in feature_flags.REGISTRY
    assert settings.FEATURE_FLAGS[EMAIL_FLAG] is False


def test_token_never_reaches_broker_with_flag_off(
    client: Client,
    org_a: Organization,
    published: list[dict[str, Any]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    owner, _ = member(org_a, Role.OWNER)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        created = invite(client, owner, org_a, BODY)
        resent = manage(client, owner, org_a, created.json()["id"], "resend")

    assert (created.status_code, resent.status_code) == (201, 201)
    tokens = [token_of(created), token_of(resent)]
    assert published == []
    assert all(token not in repr(callback) for callback in callbacks for token in tokens)
    assert mail.outbox == []


def test_queue_does_nothing_with_flag_off(
    django_capture_on_commit_callbacks: Any, enqueued: list[dict[str, Any]]
) -> None:
    with django_capture_on_commit_callbacks() as callbacks:
        assert queue_invitation_email(system_ctx(uuid.uuid4()), uuid.uuid4(), LINK) is False

    assert callbacks == []
    assert enqueued == []


def test_flag_on_enqueues_after_commit_with_the_link_redacted(
    client: Client,
    org_a: Organization,
    settings: SettingsWrapper,
    enqueued: list[dict[str, Any]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    flag(settings, True)
    owner, _ = member(org_a, Role.OWNER)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        created = invite(client, owner, org_a, BODY)
    assert enqueued == []  # not before the commit
    for callback in callbacks:
        callback()

    (job,) = enqueued
    token = token_of(created)
    assert job["kwargs"] == {
        "organization_id": str(org_a.id),
        "invitation_id": created.json()["id"],
        "accept_url": f"{ACCEPT_PREFIX}{token}",
    }
    assert token not in job["kwargsrepr"]
    assert "[redacted]" in job["kwargsrepr"]
    assert job["expires"] == EMAIL_EXPIRES_SECONDS <= 3600


def test_flag_on_resend_enqueues_the_new_link(
    client: Client,
    org_a: Organization,
    settings: SettingsWrapper,
    enqueued: list[dict[str, Any]],
    django_capture_on_commit_callbacks: Any,
) -> None:
    flag(settings, True)
    owner, _ = member(org_a, Role.OWNER)
    invitation, _ = issue(org_a, "ana@hub.test")

    with django_capture_on_commit_callbacks(execute=True):
        resent = manage(client, owner, org_a, invitation.pk, "resend")

    (job,) = enqueued
    assert job["kwargs"]["invitation_id"] == resent.json()["id"] != str(invitation.pk)
    assert job["kwargs"]["accept_url"] == f"{ACCEPT_PREFIX}{token_of(resent)}"


def test_flag_on_task_sends_the_link_to_the_invitee(
    org_a: Organization, settings: SettingsWrapper, mailoutbox: list[Any]
) -> None:
    flag(settings, True)
    invitation, _ = issue(org_a, "ana@hub.test")
    job = {
        "organization_id": str(org_a.id),
        "invitation_id": str(invitation.pk),
        "accept_url": LINK,
    }

    assert send_invitation_email.apply(kwargs=job).get() is True

    (message,) = mailoutbox
    assert message.to == ["ana@hub.test"]
    assert "Acme" in message.subject
    assert LINK in message.body


@pytest.mark.parametrize("status", [InvitationStatus.REVOKED, InvitationStatus.EXPIRED])
def test_flag_on_task_skips_an_invitation_that_no_longer_works(
    org_a: Organization,
    settings: SettingsWrapper,
    mailoutbox: list[Any],
    status: InvitationStatus,
) -> None:
    flag(settings, True)
    invitation, _ = issue(org_a, "ana@hub.test")
    set_status(invitation, status)
    job = {
        "organization_id": str(org_a.id),
        "invitation_id": str(invitation.pk),
        "accept_url": LINK,
    }

    assert send_invitation_email.apply(kwargs=job).get() is False
    assert mailoutbox == []


def test_task_sends_nothing_once_the_flag_is_off(
    org_a: Organization, mailoutbox: list[Any]
) -> None:
    """Enqueued while on, run after it was turned off: nothing is sent."""
    invitation, _ = issue(org_a, "ana@hub.test")
    job = {
        "organization_id": str(org_a.id),
        "invitation_id": str(invitation.pk),
        "accept_url": LINK,
    }

    assert send_invitation_email.apply(kwargs=job).get() is False
    assert mailoutbox == []


def test_task_does_not_send_another_organizations_invitation(
    org_a: Organization, settings: SettingsWrapper, mailoutbox: list[Any]
) -> None:
    flag(settings, True)
    invitation, _ = issue(new_org("Other"), "ana@hub.test")
    job = {
        "organization_id": str(org_a.id),
        "invitation_id": str(invitation.pk),
        "accept_url": LINK,
    }

    assert send_invitation_email.apply(kwargs=job).get() is False
    assert mailoutbox == []
