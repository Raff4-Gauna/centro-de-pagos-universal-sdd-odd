"""Revoke a membership and leave the organization (RF-TEN-04, RN-TEN-14, RN-TEN-21, §4.2, 4-5).

``revoke_membership(ctx, membership_id)`` runs after the route's ``ActionPermission``
(``member.revoke``: owner or admin) and ``leave_organization(ctx)`` after ``member.leave`` (every
role). Both are ``REDUCE_ACCESS``: allowed with the organization suspended (Q-221). In one
transaction and in the fixed lock order (organization, then membership, then invitations), as
changing a role (``services/memberships.py``):

1. ``lock_membership_mutex`` locks the organization row: every membership change of the
   organization waits for the one in flight, so two owners who revoke each other, or leave at once,
   decide one after the other on the owners that are left (RN-TEN-14, AC-TEN-14).
2. The actor's membership is read again under the lock (RN-TEN-08): revoked since the request was
   resolved is ``404 organization_not_found``, what the next request would get (AC-TEN-04).
3. Revoking one's own membership is leaving (design.md §4.2, step 5): ``membership.left``, and the
   last owner gets ``last_owner`` (AC-TEN-13). Someone else's: a role no longer in
   ``member.revoke`` is ``403``; the target is locked, and missing or of another organization is
   ``404 not_found`` (RN-TEN-05, AC-TEN-02), ``revoked`` is ``409 invalid_transition`` with
   ``transition.rejected`` (C-05). ``decide_revoke`` decides with the roles and owners as they are
   now: an admin never revokes an owner (``403``, AC-TEN-15), nobody revokes the last owner.
4. ``ALLOW``: the membership is ``revoked`` and kept, with ``ended_reason`` ``revoked`` or ``left``,
   when and by whom (RN-TEN-21: re-inviting creates a new one, AC-TEN-31); ``membership.revoked``
   or ``membership.left``; and every ``pending`` invitation that person issued is revoked with
   ``inviter_lost_permission`` and ``invitation.auto_revoked`` (Q-223, AC-TEN-36), in the same
   transaction. A resent invitation belongs to whoever resent it (Q-234 a); the operator's are never
   touched.

The audited refusals (``owner_protection.rejected``, ``transition.rejected``) leave the transaction
without changes and go out after it (design.md §3.3). A lock not taken within ``lock_timeout`` is
``503 organization_busy`` (Q-230). Logs carry ids, never an email.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.common.logging import get_logger
from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import Forbidden, OrganizationNotFound
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import Decision, decide_leave, decide_revoke
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Membership
from apps.tenancy.models.membership import EndedReason, MembershipStatus
from apps.tenancy.selectors.locks import (
    LockedMembership,
    MembershipMutex,
    active_owner_count,
    actor_membership,
    lock_membership,
    lock_membership_mutex,
)
from apps.tenancy.services.audit import audit_trigger, record_event
from apps.tenancy.services.memberships import (
    MEMBERSHIP_NOT_FOUND,
    LastOwner,
    Refused,
    auto_revoke_invitations,
)

logger = get_logger(__name__)

REVOKED_EVENT = "tenancy.membership_revoked"
LEFT_EVENT = "tenancy.membership_left"
# The ``event`` of ``transition.rejected`` and ``owner_protection.rejected`` (Q-225).
REVOKE = "revoke"
LEAVE = "leave"
_ENTITY = "membership"
_REVOKE = TENANCY_ACTIONS[TenancyAction.MEMBER_REVOKE]
_LEAVE = TENANCY_ACTIONS[TenancyAction.MEMBER_LEAVE]
_AUDITED = {
    EndedReason.REVOKED: TenancyAuditAction.MEMBERSHIP_REVOKED,
    EndedReason.LEFT: TenancyAuditAction.MEMBERSHIP_LEFT,
}


@dataclass(frozen=True, slots=True)
class MembershipExit:
    """The membership that ended, why, and the invitations revoked with it (Q-223)."""

    membership_id: uuid.UUID
    reason: EndedReason
    auto_revoked: tuple[uuid.UUID, ...]


@audit_trigger(TenancyAuditAction.MEMBERSHIP_REVOKED)
def revoke_membership(ctx: TenantContext, membership_id: uuid.UUID) -> MembershipExit:
    if not isinstance(membership_id, uuid.UUID):
        raise TypeError("membership_id must be a UUID")
    with transaction.atomic():
        outcome = _revoke_locked(ctx, membership_id)
    return _finish(ctx, outcome)


@audit_trigger(TenancyAuditAction.MEMBERSHIP_LEFT)
def leave_organization(ctx: TenantContext) -> MembershipExit:
    with transaction.atomic():
        mutex = lock_membership_mutex(ctx, _LEAVE.kind)
        actor = actor_membership(mutex)
        if actor is None:  # left or revoked since the resolution: what the next request answers
            raise OrganizationNotFound
        outcome = _leave(mutex, actor)
    return _finish(ctx, outcome)


def _finish(ctx: TenantContext, outcome: MembershipExit | Refused) -> MembershipExit:
    """A refusal goes out after the transaction: its event, then its error."""
    if isinstance(outcome, Refused):
        record_event(outcome.action, ctx=ctx, metadata=outcome.metadata)
        raise outcome.error
    logger.info(
        LEFT_EVENT if outcome.reason is EndedReason.LEFT else REVOKED_EVENT,
        membership_id=str(outcome.membership_id),
        auto_revoked=len(outcome.auto_revoked),
    )
    return outcome


def _revoke_locked(ctx: TenantContext, membership_id: uuid.UUID) -> MembershipExit | Refused:
    mutex = lock_membership_mutex(ctx, _REVOKE.kind)
    actor = actor_membership(mutex)
    if actor is None:  # revoked since the resolution: what the next request would answer
        raise OrganizationNotFound
    if membership_id == actor.membership_id:  # one's own: leaving (design.md §4.2, step 5)
        return _leave(mutex, actor)
    if actor.role not in _REVOKE.roles:  # demoted since the resolution (RN-TEN-08)
        raise Forbidden
    target = lock_membership(mutex, membership_id)
    if target is None:
        raise NotFound(MEMBERSHIP_NOT_FOUND)
    if target.status is not MembershipStatus.ACTIVE:
        metadata = {
            "entity": _ENTITY,
            "entity_id": str(target.membership_id),
            "state": target.status.value,
            "event": REVOKE,
        }
        return Refused(TenancyAuditAction.TRANSITION_REJECTED, metadata, InvalidTransition())
    decision = decide_revoke(actor.role, target.role, active_owners=active_owner_count(mutex))
    if decision is Decision.FORBIDDEN:
        raise Forbidden
    if decision is Decision.LAST_OWNER:
        return _last_owner(target, REVOKE)
    return _end(mutex, target, EndedReason.REVOKED, by=actor)


def _leave(mutex: MembershipMutex, actor: LockedMembership) -> MembershipExit | Refused:
    own = lock_membership(mutex, actor.membership_id)  # the row, after the organization
    if own is None or own.status is not MembershipStatus.ACTIVE:
        raise OrganizationNotFound  # cannot happen: it was just read active under the lock
    if decide_leave(own.role, active_owners=active_owner_count(mutex)) is Decision.LAST_OWNER:
        return _last_owner(own, LEAVE)
    return _end(mutex, own, EndedReason.LEFT, by=actor)


def _last_owner(target: LockedMembership, event: str) -> Refused:
    metadata = {"membership_id": str(target.membership_id), "event": event}
    return Refused(TenancyAuditAction.OWNER_PROTECTION_REJECTED, metadata, LastOwner())


def _end(
    mutex: MembershipMutex, target: LockedMembership, reason: EndedReason, *, by: LockedMembership
) -> MembershipExit:
    ctx = mutex.ctx
    now = timezone.now()
    Membership.objects.for_tenant(ctx).filter(pk=target.membership_id).update(
        status=MembershipStatus.REVOKED.value,
        ended_reason=reason.value,
        ended_at=now,
        ended_by_id=by.user_id,
        updated_at=now,
    )
    record_event(
        _AUDITED[reason],
        ctx=ctx,
        reason=reason.value,
        metadata={
            "membership_id": str(target.membership_id),
            "user_id": str(target.user_id),
            "role": target.role.value,
        },
    )
    revoked = auto_revoke_invitations(
        ctx,
        target.user_id,
        None,
        membership_id=target.membership_id,
        by_user_id=by.user_id,
        now=now,
    )
    return MembershipExit(target.membership_id, reason, tuple(revoked))
