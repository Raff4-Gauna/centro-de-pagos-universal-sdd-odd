"""Change the role of a membership of the active organization (RF-TEN-04, design.md §4.2, 1-3).

``change_role(ctx, membership_id, new_role)`` runs after the route's ``ActionPermission``
(``member.change_role``: owner or admin, a ``WRITE``). In one transaction and in the fixed lock
order (organization, then membership, then invitations):

1. ``lock_membership_mutex`` locks the organization row and reads its real status: suspended is
   ``409 organization_suspended`` (AC-TEN-28). Every membership change takes the same lock, so two
   of them run one after the other (RN-TEN-14).
2. The actor's membership is read again under the lock (RN-TEN-08): if it was revoked since the
   request was resolved the answer is ``404 organization_not_found``, as the next request would
   get, and if its role no longer changes roles, ``403 forbidden``. The target is locked; missing
   or of another organization is ``404 not_found`` (RN-TEN-05, AC-TEN-02), ``revoked`` is
   ``409 invalid_transition`` with ``transition.rejected`` (C-05, Q-225). Then the active owners
   are counted and ``domain.role_rules.decide_role_change`` decides with the roles as they are now.
3. ``ALLOW``: the role is saved, the person's ``pending`` invitations that the new role could no
   longer issue are revoked with ``inviter_lost_permission`` (Q-223, AC-TEN-36), and
   ``membership.role_changed`` (and one ``invitation.auto_revoked`` per invitation) is emitted in
   the transaction. ``NOOP``: nothing is written nor emitted. ``FORBIDDEN``: ``403`` (AC-TEN-15,
   AC-TEN-16). ``LAST_OWNER``: ``409 last_owner`` (AC-TEN-13).

The audited refusals (``owner_protection.rejected``, ``transition.rejected``) leave the transaction
first, without changes, and go out on their own after it (design.md §3.3, §4.2): a refusal never
rolls its own audit back. A lock not taken within ``lock_timeout`` is the database's error, which
the API answers ``503 organization_busy`` (Q-230). Logs carry ids, never an email.

Revoking and leaving (steps 4-5 of §4.2) are ``services/membership_exit.py``: they share
``LastOwner``, ``Refused`` and ``auto_revoke_invitations`` with this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import Forbidden, OrganizationNotFound
from apps.common.tenancy.locks import bounded_lock_wait
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import InvitationStatus, RevokedReason
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import (
    Decision,
    decide_role_change,
    invitations_to_auto_revoke,
)
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Invitation, Membership
from apps.tenancy.models.membership import MembershipStatus
from apps.tenancy.selectors.locks import (
    LockedMembership,
    active_owner_count,
    actor_membership,
    lock_membership,
    lock_membership_mutex,
)
from apps.tenancy.services.audit import audit_trigger, record_event

logger = get_logger(__name__)

ROLE_CHANGED_EVENT = "tenancy.membership_role_changed"
MEMBERSHIP_NOT_FOUND = "La membership no existe."
# ``transition.rejected`` (Q-225): which entity, in which state, refused which event.
_ENTITY = "membership"
CHANGE_ROLE = "change_role"
_CHANGERS = TENANCY_ACTIONS[TenancyAction.MEMBER_CHANGE_ROLE].roles


class LastOwner(APIException):
    """``409 last_owner``: the organization keeps at least one active owner (RN-TEN-14)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "last_owner"
    default_detail = "La organización tiene que conservar al menos un owner."


@dataclass(frozen=True, slots=True)
class RoleChange:
    """What changed: the membership, whether it did, and the actor's role after the change."""

    membership_id: uuid.UUID
    changed: bool
    actor_role: Role


@dataclass(frozen=True, slots=True)
class Refused:
    """A refusal audited after the transaction: the event, its metadata and the error to raise."""

    action: TenancyAuditAction
    metadata: dict[str, str]
    error: APIException


@audit_trigger(
    TenancyAuditAction.MEMBERSHIP_ROLE_CHANGED,
    TenancyAuditAction.OWNER_PROTECTION_REJECTED,
    TenancyAuditAction.INVITATION_AUTO_REVOKED,
)
def change_role(ctx: TenantContext, membership_id: uuid.UUID, new_role: Role) -> RoleChange:
    if not isinstance(membership_id, uuid.UUID):
        raise TypeError("membership_id must be a UUID")
    if not isinstance(new_role, Role):
        raise TypeError("new_role must be a Role")
    with transaction.atomic():
        outcome = _change_locked(ctx, membership_id, new_role)
    if isinstance(outcome, Refused):
        record_event(outcome.action, ctx=ctx, metadata=outcome.metadata)
        raise outcome.error
    return outcome


def _change_locked(
    ctx: TenantContext, membership_id: uuid.UUID, new_role: Role
) -> RoleChange | Refused:
    mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
    actor = actor_membership(mutex)
    if actor is None:  # revoked since the resolution: what the next request would answer
        raise OrganizationNotFound
    if actor.role not in _CHANGERS:  # demoted since the resolution (RN-TEN-08)
        raise Forbidden
    target = lock_membership(mutex, membership_id)
    if target is None:
        raise NotFound(MEMBERSHIP_NOT_FOUND)
    if target.status is not MembershipStatus.ACTIVE:
        return Refused(
            TenancyAuditAction.TRANSITION_REJECTED,
            {
                "entity": _ENTITY,
                "entity_id": str(target.membership_id),
                "state": target.status.value,
                "event": CHANGE_ROLE,
            },
            InvalidTransition(),
        )
    is_self = target.membership_id == actor.membership_id
    decision = decide_role_change(
        actor.role,
        target.role,
        new_role,
        is_self=is_self,
        active_owners=active_owner_count(mutex),
    )
    if decision is Decision.FORBIDDEN:
        raise Forbidden
    if decision is Decision.LAST_OWNER:
        metadata = {"membership_id": str(target.membership_id), "event": CHANGE_ROLE}
        return Refused(TenancyAuditAction.OWNER_PROTECTION_REJECTED, metadata, LastOwner())
    if decision is Decision.NOOP:
        return RoleChange(target.membership_id, changed=False, actor_role=actor.role)
    _apply(ctx, target, new_role, by_user_id=actor.user_id)
    return RoleChange(
        target.membership_id, changed=True, actor_role=new_role if is_self else actor.role
    )


def _apply(
    ctx: TenantContext, target: LockedMembership, new_role: Role, *, by_user_id: uuid.UUID
) -> None:
    now = timezone.now()
    Membership.objects.for_tenant(ctx).filter(pk=target.membership_id).update(
        role=new_role.value, updated_at=now
    )
    record_event(
        TenancyAuditAction.MEMBERSHIP_ROLE_CHANGED,
        ctx=ctx,
        metadata={
            "membership_id": str(target.membership_id),
            "user_id": str(target.user_id),
            "from_role": target.role.value,
            "to_role": new_role.value,
        },
    )
    auto_revoke_invitations(
        ctx, target.user_id, new_role, membership_id=target.membership_id, by_user_id=by_user_id
    )
    logger.info(
        ROLE_CHANGED_EVENT,
        membership_id=str(target.membership_id),
        from_role=target.role.value,
        to_role=new_role.value,
    )


def auto_revoke_invitations(
    ctx: TenantContext,
    inviter_user_id: uuid.UUID,
    new_role_or_none: Role | None,
    *,
    membership_id: uuid.UUID,
    by_user_id: uuid.UUID,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Revoke the ``pending`` invitations the inviter's new role (``None``: it left or was
    revoked) no longer lets it issue (Q-223), in the caller's transaction, after the membership's
    lock. The operator's invitations name no user and are never touched. Gives their ids."""
    moment = timezone.now() if now is None else now
    with bounded_lock_wait():
        pending = list(
            Invitation.objects.for_tenant(ctx)
            .select_for_update()
            .filter(invited_by_user_id=inviter_user_id, status=InvitationStatus.PENDING.value)
            .order_by("created_at", "id")
        )
    revoked: list[uuid.UUID] = []
    for invitation in invitations_to_auto_revoke(new_role_or_none, pending):
        invitation.status = InvitationStatus.REVOKED.value
        invitation.revoked_reason = RevokedReason.INVITER_LOST_PERMISSION.value
        invitation.revoked_at = moment
        invitation.revoked_by_id = by_user_id
        invitation.save(
            update_fields=["status", "revoked_reason", "revoked_at", "revoked_by", "updated_at"]
        )
        record_event(
            TenancyAuditAction.INVITATION_AUTO_REVOKED,
            ctx=ctx,
            reason=RevokedReason.INVITER_LOST_PERMISSION.value,
            metadata={"invitation_id": str(invitation.pk), "membership_id": str(membership_id)},
        )
        revoked.append(invitation.pk)
    return revoked
