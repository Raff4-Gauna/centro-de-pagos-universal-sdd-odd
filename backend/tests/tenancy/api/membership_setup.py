"""Shared setup of the membership API tests (T-TEN-22): members, requests and what to read back.

Rows go in as the operator's command would (``probe.add_member``), so no business rule runs; the
tests read back with ``unscoped(PLATFORM)``, never through the code under test.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from apps.common.audit.port import get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.identity.models import User
from apps.tenancy.models import Membership, Organization
from tests.tenancy.api.probe import PLATFORM, add_member, as_member, new_user

MEMBERSHIPS = "/api/memberships/"


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


def member(organization: Organization, role: Role, name: str = "") -> tuple[User, Membership]:
    user = new_user(name or f"{role.value}-{organization.name.lower()}")
    return user, add_member(organization, user, role)


def patch_role(
    client: Client, user: User, organization: Organization, membership_id: Any, body: Any
) -> Any:
    return client.patch(
        f"{MEMBERSHIPS}{membership_id}/",
        data=json.dumps(body),
        content_type="application/json",
        headers=as_member(user, organization.id),
    )


def set_role(
    client: Client, user: User, organization: Organization, target: Membership, role: Role
) -> Any:
    return patch_role(client, user, organization, target.pk, {"role": role.value})


def role_of(membership: Membership) -> str:
    rows = Membership.objects.unscoped(PLATFORM).filter(pk=membership.pk)
    return str(rows.values_list("role", flat=True).get())


def roles_in(organization: Organization) -> list[tuple[str, str, str]]:
    """(email, role, status) of every membership of ``organization``, by email."""
    rows = Membership.objects.unscoped(PLATFORM).filter(organization=organization)
    return sorted(rows.values_list("user__email", "role", "status"))
