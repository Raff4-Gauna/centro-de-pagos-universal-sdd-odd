"""Completeness of SPEC-02's audit (AC-TEN-23, RN-TEN-17, RF-TEN-09, RNF-TEN-04; design.md §9).

One test per action of the catalog (``TenancyAuditAction``): its trigger is in ``AUDIT_TRIGGERS``
and driving it emits that action with actor, action, organization and date, in UTC. Each driver
calls the function the registry names, never an import of its own, so a trigger that is moved or
dropped fails here. ``DRIVERS`` must cover the catalog exactly: an action added without a way to
reach it, or a driver left over, fails too.

A service registers its triggers when its module is imported, so the registry is only whole once
every module of ``apps.tenancy.services`` is: ``every_service`` imports them all, as a worker or a
command would end up doing, instead of trusting what earlier tests happened to import.

The writes of the API are also driven by route, as A's member, in
``tests/cross_tenant/test_action_kinds.py``; the commands and the expiry task only here.
"""

from __future__ import annotations

import pkgutil
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from importlib import import_module

import pytest
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.common.audit.port import AuditActor, AuditActorKind, get_sink
from apps.common.audit.sinks import RecordingSink
from apps.common.authz.roles import Role
from apps.common.tenancy.context import OrgStatus, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.tenancy import services
from apps.tenancy.domain.audit_events import TenancyAuditAction as Action
from apps.tenancy.models import Branch, Membership, Organization
from apps.tenancy.selectors.invitations import InvitationRef
from apps.tenancy.services.audit import AUDIT_TRIGGERS, Trigger
from apps.tenancy.services.invitations import create_invitation
from apps.tenancy.services.platform_org import Operator, clean_request
from apps.tenancy.services.platform_owner_invite import OrganizationHasOwnerError
from tests.tenancy.invitation_setup import invitee, issue, make_due
from tests.tenancy.locking import PLATFORM, add_member, new_org, system_ctx, user_ctx

pytestmark = pytest.mark.django_db

OPERATOR = Operator(email="ops@hub.test", os_user="deploy")
REASON = "pedido del cliente por mesa de ayuda"

# A driver sets up its scene, calls the trigger so that it emits the action, and gives back the
# organization the event must name.
Driver = Callable[[Trigger], uuid.UUID]


def every_service() -> None:
    for info in pkgutil.iter_modules(services.__path__):
        import_module(f"{services.__name__}.{info.name}")


every_service()


@pytest.fixture
def recorded() -> Iterator[RecordingSink]:
    sink = get_sink()
    assert isinstance(sink, RecordingSink)
    sink.clear()
    yield sink
    sink.clear()


class Scene:
    """Organization A with an owner and an admin, and the context of each one's requests."""

    def __init__(self) -> None:
        self.org = new_org("A")
        self.owner = add_member(self.org, "owner-a", Role.OWNER)
        self.admin = add_member(self.org, "admin-a", Role.ADMIN)

    def as_(self, membership: Membership) -> TenantContext:
        return user_ctx(membership)

    def run(self, ctx: TenantContext, call: Callable[[], object], *, refused: bool = False) -> None:
        with tenant_scope(ctx):
            if refused:
                with pytest.raises(APIException):
                    call()
            else:
                call()

    def branch(self, *, active: bool = True) -> uuid.UUID:
        ctx = system_ctx(self.org.id)
        with tenant_scope(ctx):
            branch = Branch.objects.for_tenant(ctx).create(name="Centro", is_active=active)
        return branch.pk

    def invitation_by(self, membership: Membership) -> uuid.UUID:
        ctx = self.as_(membership)
        with tenant_scope(ctx):
            created = create_invitation(ctx, "ana@hub.test", Role.VIEWER)
        return created.invitation_id


# --- organization.* (the operator's commands and the company data) -------------------------------


def _org_created(trigger: Trigger) -> uuid.UUID:
    request = clean_request(key="acme", name="Acme", owner_email="ana@hub.test")
    return trigger(request, OPERATOR).organization_id  # type: ignore[attr-defined]


def _org_create_repeated(trigger: Trigger) -> uuid.UUID:
    request = clean_request(key="acme", name="Acme", owner_email="ana@hub.test")
    trigger(request, OPERATOR)
    return trigger(request, OPERATOR).organization_id  # type: ignore[attr-defined]


def _org_updated(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, {"name": "Acme Norte"}))
    return scene.org.id


def _org_status(target: OrgStatus, start: OrgStatus) -> Driver:
    def drive(trigger: Trigger) -> uuid.UUID:
        org = new_org("A", start)
        trigger(org.id, target, REASON, OPERATOR)
        return org.id

    return drive


def _operator_refused(trigger: Trigger) -> uuid.UUID:
    """Q-237: the first owner's invitation of an organization that has an owner already."""
    org = new_org("A")
    add_member(org, "ana", Role.OWNER)
    with pytest.raises(OrganizationHasOwnerError):
        trigger(org.id, OPERATOR)
    return org.id


# --- membership.* and owner protection -----------------------------------------------------------


def _accepted(trigger: Trigger) -> uuid.UUID:
    org = new_org("A")
    invitation, _ = issue(org, "x@hub.test", Role.OPERATOR)
    guest = add_member(new_org("Z"), "x", Role.VIEWER).user
    trigger(InvitationRef(invitation.pk, org.id), invitee(guest))
    return org.id


def _rejected(trigger: Trigger) -> uuid.UUID:
    org = new_org("A")
    invitation, _ = issue(org, "otra@hub.test", Role.OPERATOR)
    guest = add_member(new_org("Z"), "x", Role.VIEWER).user
    with pytest.raises(APIException):
        trigger(InvitationRef(invitation.pk, org.id), invitee(guest))
    return org.id


def _role_changed(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, scene.admin.pk, Role.VIEWER))
    return scene.org.id


def _owner_protection(trigger: Trigger) -> uuid.UUID:
    scene = Scene()  # the owner is the only one: demoting itself would leave A without owner
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, scene.owner.pk, Role.ADMIN), refused=True)
    return scene.org.id


def _auto_revoked(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    scene.invitation_by(scene.admin)  # a viewer cannot invite: demoting the admin revokes it
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, scene.admin.pk, Role.VIEWER))
    return scene.org.id


def _revoked(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, scene.admin.pk))
    return scene.org.id


def _left(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.admin)
    scene.run(ctx, lambda: trigger(ctx))
    return scene.org.id


# --- invitation.* --------------------------------------------------------------------------------


def _invitation_created(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, "ana@hub.test", Role.VIEWER))
    return scene.org.id


def _on_invitation(trigger: Trigger) -> uuid.UUID:
    """Resend and revoke: the owner acts on a ``pending`` invitation of its own."""
    scene = Scene()
    invitation_id = scene.invitation_by(scene.owner)
    ctx = scene.as_(scene.owner)
    scene.run(ctx, lambda: trigger(ctx, invitation_id))
    return scene.org.id


def _expired(trigger: Trigger) -> uuid.UUID:
    org = new_org("A")
    invitation, _ = issue(org, "ana@hub.test")
    make_due(invitation)
    ctx = system_ctx(org.id)
    with tenant_scope(ctx):
        trigger(ctx, invitation.pk)
    return org.id


# --- branch.* and transitions --------------------------------------------------------------------


def _branch_created(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    ctx = scene.as_(scene.admin)
    scene.run(ctx, lambda: trigger(ctx, {"name": "Centro"}))
    return scene.org.id


def _branch_updated(trigger: Trigger) -> uuid.UUID:
    scene = Scene()
    branch_id, ctx = scene.branch(), scene.as_(scene.admin)
    scene.run(ctx, lambda: trigger(ctx, branch_id, {"name": "Centro Norte"}))
    return scene.org.id


def _on_branch(*, active: bool, refused: bool = False) -> Driver:
    """Deactivate an active branch, reactivate an inactive one or (refused) an active one."""

    def drive(trigger: Trigger) -> uuid.UUID:
        scene = Scene()
        branch_id, ctx = scene.branch(active=active), scene.as_(scene.admin)
        scene.run(ctx, lambda: trigger(ctx, branch_id), refused=refused)
        return scene.org.id

    return drive


DRIVERS: dict[Action, Driver] = {
    Action.ORGANIZATION_CREATED: _org_created,
    Action.ORGANIZATION_CREATE_REPEATED: _org_create_repeated,
    Action.ORGANIZATION_UPDATED: _org_updated,
    Action.ORGANIZATION_SUSPENDED: _org_status(OrgStatus.SUSPENDED, OrgStatus.ACTIVE),
    Action.ORGANIZATION_REACTIVATED: _org_status(OrgStatus.ACTIVE, OrgStatus.SUSPENDED),
    Action.MEMBERSHIP_CREATED: _accepted,
    Action.MEMBERSHIP_ROLE_CHANGED: _role_changed,
    Action.MEMBERSHIP_REVOKED: _revoked,
    Action.MEMBERSHIP_LEFT: _left,
    Action.INVITATION_CREATED: _invitation_created,
    Action.INVITATION_RESENT: _on_invitation,
    Action.INVITATION_REVOKED: _on_invitation,
    Action.INVITATION_ACCEPTED: _accepted,
    Action.INVITATION_REJECTED: _rejected,
    Action.INVITATION_EXPIRED: _expired,
    Action.INVITATION_AUTO_REVOKED: _auto_revoked,
    Action.BRANCH_CREATED: _branch_created,
    Action.BRANCH_UPDATED: _branch_updated,
    Action.BRANCH_DEACTIVATED: _on_branch(active=True),
    Action.BRANCH_REACTIVATED: _on_branch(active=False),
    Action.OWNER_PROTECTION_REJECTED: _owner_protection,
    Action.TRANSITION_REJECTED: _on_branch(active=True, refused=True),
    Action.OPERATOR_COMMAND_REJECTED: _operator_refused,
}


# Who acts: the operator's commands are audited with the operator (Q-212), the expiry with the
# system (RNF-TEN-04); every other action is a person's.
BY_OPERATOR = frozenset(
    {
        Action.ORGANIZATION_CREATED,
        Action.ORGANIZATION_CREATE_REPEATED,
        Action.ORGANIZATION_SUSPENDED,
        Action.ORGANIZATION_REACTIVATED,
        Action.OPERATOR_COMMAND_REJECTED,
    }
)
BY_SYSTEM = frozenset({Action.INVITATION_EXPIRED})


def actor_kind(action: Action) -> AuditActorKind:
    if action in BY_OPERATOR:
        return AuditActorKind.PLATFORM_OPERATOR
    return AuditActorKind.SYSTEM if action in BY_SYSTEM else AuditActorKind.USER


def test_AC_TEN_23_drivers_and_triggers_cover_the_catalog() -> None:
    assert set(DRIVERS) == set(Action)
    assert set(AUDIT_TRIGGERS) == set(Action)


@pytest.mark.parametrize("action", [pytest.param(action, id=action.value) for action in Action])
def test_AC_TEN_23_every_action_has_trigger_and_fields(
    action: Action, recorded: RecordingSink
) -> None:
    trigger = AUDIT_TRIGGERS.get(action)
    assert trigger is not None, f"{action} has no trigger in AUDIT_TRIGGERS"
    driver = DRIVERS.get(action)
    assert driver is not None, f"{action} has no driver in this test"
    start = timezone.now()

    organization_id = driver(trigger)

    events = [event for event in recorded.events if event.action == action]
    assert events, f"{trigger.__qualname__} did not emit {action}"
    end = timezone.now()
    for event in events:
        assert isinstance(event.actor, AuditActor)
        assert event.actor.kind is actor_kind(action)
        assert event.organization_id == organization_id
        assert Organization.objects.unscoped(PLATFORM).filter(pk=organization_id).exists()
        assert event.occurred_at.utcoffset() == timedelta(0)
        assert start <= event.occurred_at <= end
