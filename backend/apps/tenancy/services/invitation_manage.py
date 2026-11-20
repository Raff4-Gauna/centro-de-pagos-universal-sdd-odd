"""Resend and revoke an invitation of the active organization (RF-TEN-05, RN-TEN-12, §4.3).

``resend_invitation(ctx, id)`` runs after the route's ``ActionPermission`` (``invitation.resend``,
owner or admin, a ``WRITE``) and ``revoke_invitation(ctx, id)`` after ``invitation.revoke`` (owner
or admin, a ``REDUCE_ACCESS``: allowed with the organization suspended, Q-221). In one transaction
and in the fixed lock order (organization, then invitation), as creating one
(``services/invitations.py``):

1. ``lock_membership_mutex`` with the action's kind: suspended is ``409 organization_suspended``
   for a resend (AC-TEN-28), not for a revoke.
2. The actor's membership is read again under the lock (RN-TEN-08): revoked since the request was
   resolved is ``404 organization_not_found``; a role no longer in the action's list, ``403``.
3. The invitation, ``FOR UPDATE``: another organization's and a missing one are the same
   ``404 not_found`` (RN-TEN-05, AC-TEN-02). ``decide_manage_invitation`` with the role as it is
   now: an admin never touches an ``owner`` one (``403``, Q-202, AC-TEN-15), whatever its state.
4. A ``pending`` one past its expiry becomes ``expired`` first (``invitation.expired``, the system
   as its actor; lazy expiry, RN-TEN-12). Any status other than ``pending`` is
   ``409 invalid_transition``, and ``transition.rejected`` (entity, state, event) goes out after
   the transaction: the expiry stays and the refusal never rolls its own audit back (C-05, Q-225,
   AC-TEN-37, design.md §3.3).
5. Revoking: ``revoked`` with ``revoked_reason=revoked``, who and when, and ``invitation.revoked``.
   Resending (AC-TEN-26): the old one is ``revoked`` with ``revoked_reason=resent`` and
   ``invitation.revoked``; the new one keeps its email, role, purpose and reason, points at it
   (``replaces``), is issued by the actor (who vouches for it now, also for Q-223) and lives seven
   days from now, with a fresh token, inserted as a new one is (``insert_invitation``); then
   ``invitation.resent``.

The resend's ``accept_url`` is the only place the new token exists in clear (RNF-TEN-03,
AC-TEN-24), masked in ``repr``; the old token is ``invitation_invalid`` (``revoked``) from then on.
Without ``FRONTEND_BASE_URL`` nothing is locked nor written. A lock not taken within
``lock_timeout`` is ``503 organization_busy`` (Q-230). Logs and events carry ids, never an email
nor a token (C-06).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import Forbidden, OrganizationNotFound
from apps.common.tenancy.locks import bounded_lock_wait
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import (
    InvitationStatus,
    RevokedReason,
    expires_at_for,
    hash_token,
    is_expired,
    new_token,
)
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction
from apps.tenancy.domain.role_rules import Decision, decide_manage_invitation
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Invitation
from apps.tenancy.selectors.locks import LockedMembership, actor_membership, lock_membership_mutex
from apps.tenancy.services.audit import audit_trigger, record_event
from apps.tenancy.services.invitations import (
    ACCEPT_PATH,
    CreatedInvitation,
    accept_base_url,
    expire_invitation,
    insert_invitation,
)

logger = get_logger(__name__)

RESENT_EVENT = "tenancy.invitation_resent"
REVOKED_EVENT = "tenancy.invitation_revoked"
INVITATION_NOT_FOUND = "La invitación no existe."
# ``transition.rejected`` (Q-225): which entity, in which state, refused which event.
_ENTITY = "invitation"
RESEND = "resend"
REVOKE = "revoke"
_REVOKED_FIELDS = ["status", "revoked_reason", "revoked_at", "revoked_by", "updated_at"]


@dataclass(frozen=True, slots=True)
class RevokedInvitation:
    """The invitation revoked and the actor's role under the lock."""

    invitation_id: uuid.UUID
    actor_role: Role


@dataclass(frozen=True, slots=True)
class _Rejected:
    """``transition.rejected``, emitted after the transaction (step 4)."""

    metadata: dict[str, str]


_Outcome = tuple[uuid.UUID, Role] | _Rejected


@audit_trigger(TenancyAuditAction.INVITATION_RESENT)
def resend_invitation(
    ctx: TenantContext, invitation_id: uuid.UUID, *, now: datetime | None = None
) -> CreatedInvitation:
    if not isinstance(invitation_id, uuid.UUID):
        raise TypeError("invitation_id must be a UUID")
    base = accept_base_url()  # before any lock: a missing setting writes nothing
    moment = timezone.now() if now is None else now
    token = new_token()
    with transaction.atomic():
        outcome = _resend_locked(ctx, invitation_id, hash_token(token), moment)
    new_id, actor_role = _raise_rejected(ctx, outcome)
    logger.info(RESENT_EVENT, invitation_id=str(new_id), replaces=str(invitation_id))
    return CreatedInvitation(new_id, actor_role, f"{base}{ACCEPT_PATH}#token={token}")


@audit_trigger(TenancyAuditAction.INVITATION_REVOKED)
def revoke_invitation(
    ctx: TenantContext, invitation_id: uuid.UUID, *, now: datetime | None = None
) -> RevokedInvitation:
    if not isinstance(invitation_id, uuid.UUID):
        raise TypeError("invitation_id must be a UUID")
    moment = timezone.now() if now is None else now
    with transaction.atomic():
        outcome = _revoke_locked(ctx, invitation_id, moment)
    revoked_id, actor_role = _raise_rejected(ctx, outcome)
    logger.info(REVOKED_EVENT, invitation_id=str(revoked_id))
    return RevokedInvitation(revoked_id, actor_role)


def _raise_rejected(ctx: TenantContext, outcome: _Outcome) -> tuple[uuid.UUID, Role]:
    """A refusal goes out after the transaction: ``transition.rejected``, then the ``409``."""
    if isinstance(outcome, _Rejected):
        record_event(TenancyAuditAction.TRANSITION_REJECTED, ctx=ctx, metadata=outcome.metadata)
        raise InvalidTransition
    return outcome


def _resend_locked(
    ctx: TenantContext, invitation_id: uuid.UUID, token_hash: str, now: datetime
) -> _Outcome:
    locked = _lock_managed(ctx, invitation_id, TenancyAction.INVITATION_RESEND, RESEND, now)
    if isinstance(locked, _Rejected):
        return locked
    actor, old = locked
    _mark_revoked(ctx, old, RevokedReason.RESENT, actor, now)
    new = insert_invitation(
        ctx,
        email=old.email,
        role=old.role,
        purpose=old.purpose,
        reason=old.reason,
        token_hash=token_hash,
        expires_at=expires_at_for(now),
        invited_by_user_id=actor.user_id,
        replaces=old,
    )
    record_event(
        TenancyAuditAction.INVITATION_RESENT,
        ctx=ctx,
        metadata={
            "invitation_id": str(new.pk),
            "replaces": str(old.pk),
            "role": str(new.role),
            "purpose": str(new.purpose),
        },
    )
    return new.pk, actor.role


def _revoke_locked(ctx: TenantContext, invitation_id: uuid.UUID, now: datetime) -> _Outcome:
    locked = _lock_managed(ctx, invitation_id, TenancyAction.INVITATION_REVOKE, REVOKE, now)
    if isinstance(locked, _Rejected):
        return locked
    actor, invitation = locked
    _mark_revoked(ctx, invitation, RevokedReason.REVOKED, actor, now)
    return invitation.pk, actor.role


def _lock_managed(
    ctx: TenantContext, invitation_id: uuid.UUID, action: TenancyAction, event: str, now: datetime
) -> tuple[LockedMembership, Invitation] | _Rejected:
    """Steps 1 to 4: the actor and the invitation under the lock, or the refusal of its state."""
    spec = TENANCY_ACTIONS[action]
    mutex = lock_membership_mutex(ctx, spec.kind)
    actor = actor_membership(mutex)
    if actor is None:  # revoked since the resolution: what the next request would answer
        raise OrganizationNotFound
    if actor.role not in spec.roles:  # demoted since the resolution (RN-TEN-08)
        raise Forbidden
    with bounded_lock_wait():
        invitation = (
            Invitation.objects.for_tenant(ctx).select_for_update().filter(pk=invitation_id).first()
        )
    if invitation is None:
        raise NotFound(INVITATION_NOT_FOUND)
    if decide_manage_invitation(actor.role, invitation.role) is not Decision.ALLOW:
        raise Forbidden
    pending = InvitationStatus.PENDING.value
    if invitation.status == pending and is_expired(invitation.expires_at, now):
        expire_invitation(ctx, invitation)
    if invitation.status != pending:
        state = str(invitation.status)
        metadata = {"entity": _ENTITY, "entity_id": str(invitation.pk), "state": state}
        return _Rejected({**metadata, "event": event})
    return actor, invitation


def _mark_revoked(
    ctx: TenantContext,
    invitation: Invitation,
    reason: RevokedReason,
    actor: LockedMembership,
    now: datetime,
) -> None:
    invitation.status = InvitationStatus.REVOKED.value
    invitation.revoked_reason = reason.value
    invitation.revoked_at = now
    invitation.revoked_by_id = actor.user_id
    invitation.save(update_fields=_REVOKED_FIELDS)
    record_event(
        TenancyAuditAction.INVITATION_REVOKED,
        ctx=ctx,
        reason=reason.value,
        metadata={"invitation_id": str(invitation.pk), "role": str(invitation.role)},
    )
