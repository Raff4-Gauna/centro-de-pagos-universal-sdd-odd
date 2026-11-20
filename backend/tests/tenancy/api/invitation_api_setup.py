"""Shared setup of the invitation API tests (T-TEN-20, T-TEN-21): requests and what to read back.

Rows go in as the operator's command would (``probe.add_member``, ``invitation_setup.issue``), so
no business rule runs; the tests read back with ``unscoped(PLATFORM)``, never through the code
under test.
"""

from __future__ import annotations

import json
from typing import Any

from django.test import Client

from apps.identity.models import User
from apps.tenancy.models import Invitation, Organization
from tests.tenancy.api.probe import PLATFORM, as_member

INVITATIONS = "/api/invitations/"
ACCEPT_PREFIX = "http://localhost:3000/invitacion#token="


def invite(client: Client, user: User, organization: Organization, body: Any) -> Any:
    return client.post(
        INVITATIONS,
        data=json.dumps(body),
        content_type="application/json",
        headers=as_member(user, organization.id),
    )


def manage(
    client: Client, user: User, organization: Organization, invitation_id: Any, action: str
) -> Any:
    """``POST /api/invitations/{id}/<action>/`` (``resend`` or ``revoke``, T-TEN-21), no body."""
    return client.post(
        f"{INVITATIONS}{invitation_id}/{action}/",
        content_type="application/json",
        headers=as_member(user, organization.id),
    )


def invitations_of(organization: Organization) -> list[tuple[Any, ...]]:
    """(email, role, status) of every invitation of ``organization``, by email and status."""
    rows = Invitation.objects.unscoped(PLATFORM).filter(organization=organization)
    return sorted(rows.values_list("email", "role", "status"))


def token_of(response: Any) -> str:
    url = response.json()["accept_url"]
    assert url.startswith(ACCEPT_PREFIX), url
    return str(url.removeprefix(ACCEPT_PREFIX))
