"""``services.invitations.create_invitation`` under the lock (RN-TEN-08, RN-TEN-12, design.md §4.3).

The actor is read again under the organization's lock: a role lost or a membership revoked since
the request was resolved is the one that rules. Two creations for the same email at once leave
one ``pending`` (spec §12, AC-TEN-26): threads with their own connection and transaction
(``transaction=True``), as in ``test_invitation_accept_race.py``.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext, UserActor
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import Forbidden, OrganizationNotFound
from apps.tenancy.models import Membership, Organization
from apps.tenancy.services.invitations import (
    CreatedInvitation,
    InvitationPending,
    create_invitation,
)
from tests.identity.test_refresh_concurrency import PATIENCE
from tests.tenancy.api.invitation_api_setup import invitations_of
from tests.tenancy.api.membership_setup import member
from tests.tenancy.api.probe import PLATFORM, new_org, revoke


def ctx_of(organization: Organization, membership: Membership, role: Role) -> TenantContext:
    """The context the request resolved, with ``role``: maybe not the one in the table now."""
    actor = UserActor(user_id=membership.user_id, membership_id=membership.pk, role=role)
    return TenantContext(
        organization_id=organization.id, organization_status=OrgStatus.ACTIVE, actor=actor
    )


def create(ctx: TenantContext, email: str, role: Role) -> CreatedInvitation:
    with tenant_scope(ctx):
        return create_invitation(ctx, email, role)


@pytest.mark.django_db
def test_RN_TEN_08_owner_demoted_since_the_request_cannot_invite_an_owner() -> None:
    org = new_org("A")
    _, mine = member(org, Role.OWNER)
    ctx = ctx_of(org, mine, Role.OWNER)
    Membership.objects.unscoped(PLATFORM).filter(pk=mine.pk).update(role=Role.ADMIN.value)

    with pytest.raises(Forbidden):
        create(ctx, "jefa@hub.test", Role.OWNER)
    created = create(ctx, "op@hub.test", Role.OPERATOR)

    assert created.actor_role is Role.ADMIN
    assert invitations_of(org) == [("op@hub.test", "operator", "pending")]


@pytest.mark.django_db
def test_RN_TEN_08_revoked_since_the_request_is_organization_not_found() -> None:
    org = new_org("A")
    _, mine = member(org, Role.OWNER)
    ctx = ctx_of(org, mine, Role.OWNER)
    revoke(org, mine)

    with pytest.raises(OrganizationNotFound):
        create(ctx, "op@hub.test", Role.OPERATOR)
    assert invitations_of(org) == []


@pytest.mark.django_db
def test_RNF_TEN_03_created_invitation_masks_its_link() -> None:
    org = new_org("A")
    _, mine = member(org, Role.OWNER)

    created = create(ctx_of(org, mine, Role.OWNER), "op@hub.test", Role.OPERATOR)

    assert "#token=" in created.accept_url
    assert "token" not in repr(created)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_AC_TEN_26_two_creations_at_once_leave_one_pending() -> None:
    org = new_org("A")
    _, mine = member(org, Role.OWNER)
    ctx = ctx_of(org, mine, Role.OWNER)
    start = threading.Barrier(4)
    outcomes: list[str] = []

    def run() -> None:
        try:
            start.wait(PATIENCE)
            create(ctx, "x@dominio.com", Role.OPERATOR)
            outcomes.append("created")
        except InvitationPending:
            outcomes.append("invitation_pending")
        finally:
            connection.close()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(PATIENCE)

    assert sorted(outcomes) == ["created", *["invitation_pending"] * 3]
    assert invitations_of(org) == [("x@dominio.com", "operator", "pending")]
