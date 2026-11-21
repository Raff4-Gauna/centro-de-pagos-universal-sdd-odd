"""The platform operator reissues or revokes the first owner's invitation (RF-TEN-07, Q-213).

Only ``manage.py tenancy_owner_invite`` calls this. An organization is born without members and
with a ``first_owner`` invitation (``services/platform_org.py``); until somebody accepts it, nobody
can invite, so the operator is the one who renews or withdraws it (spec §4, the one exception to
RN-TEN-14). The command checks ``--operator`` against ``PLATFORM_OPERATOR_EMAILS`` before it gets
here; the operator (that email) is the actor of every event, with ``os_user`` in ``metadata``.

Both run in one transaction, in the lock order of the module (organization, then invitation):

1. ``tenant_scope(system_context(org, PLATFORM_COMMAND))``: an unknown organization is
   ``OrganizationNotFound``. ``lock_membership_mutex`` takes the organization's lock: it waits for
   an acceptance in flight, which takes the same lock, so the owner check below is the real one. A
   ``SystemActor`` is not stopped by a suspension (design.md §3.6).
2. An organization with an active owner is ``OrganizationHasOwnerError``: from then on its owners
   manage their invitations (Q-213, design.md §4.5). Nothing is written nor audited: nothing was
   attempted on any invitation.
3. The first owner's invitation is the latest ``first_owner`` one (a reissue points at the one it
   replaces), ``FOR UPDATE``; none is ``NoOwnerInvitationError``. A ``pending`` one past its expiry
   becomes ``expired`` first (``invitation.expired``, the system as its actor, Q-234 b).
4. Revoking: only a ``pending`` one, which becomes ``revoked`` with ``revoked_reason=operator``
   (design.md §5) and ``invitation.revoked``.
   Reissuing (Q-213, "si vence, el operador la reemite"): a ``pending`` one is ``revoked`` with
   ``revoked_reason=resent``, as a resend; an ``expired`` one stays as it is. The new one keeps the
   email, is ``owner`` / ``first_owner``, is issued by the operator, points at the old one
   (``replaces``) and lives seven days from now with a fresh token (``insert_invitation``); then
   ``invitation.resent``. A ``revoked`` or ``accepted`` one is not reissued.
5. Any other status is ``InvalidTransition``, and ``transition.rejected`` (entity, state, event)
   goes out after the transaction: the expiry of step 3 stays (C-05, AC-TEN-37, design.md §3.3).

``ReissuedInvitation.accept_url`` is the only place the new token exists in clear (masked in
``repr``); the command prints it once. Without ``FRONTEND_BASE_URL`` a reissue locks nor writes
anything. Logs and events carry ids, never an email nor a token (C-06).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.common.audit.port import AuditActor
from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.locks import bounded_lock_wait, system_context
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import (
    InvitationPurpose,
    InvitationStatus,
    RevokedReason,
    expires_at_for,
    hash_token,
    is_expired,
    new_token,
)
from apps.tenancy.errors import InvalidTransition
from apps.tenancy.models import Invitation
from apps.tenancy.selectors.locks import active_owner_count, lock_membership_mutex
from apps.tenancy.services.audit import record_event
from apps.tenancy.services.invitations import (
    accept_base_url,
    accept_url,
    expire_invitation,
    insert_invitation,
)
from apps.tenancy.services.platform_org import Operator

logger = get_logger(__name__)

REISSUED_EVENT = "tenancy.platform_owner_invitation_reissued"
REVOKED_EVENT = "tenancy.platform_owner_invitation_revoked"
REISSUE = "reissue"
REVOKE = "revoke"
_ENTITY = "invitation"
_REVOKED_FIELDS = ["status", "revoked_reason", "revoked_at", "updated_at"]
_PENDING = InvitationStatus.PENDING.value
_REISSUABLE = frozenset({_PENDING, InvitationStatus.EXPIRED.value})


class OrganizationHasOwnerError(Exception):
    def __init__(self, organization_id: uuid.UUID) -> None:
        super().__init__("the organization has an active owner")
        self.organization_id = organization_id


class NoOwnerInvitationError(Exception):
    def __init__(self, organization_id: uuid.UUID) -> None:
        super().__init__("the organization has no first owner invitation")
        self.organization_id = organization_id


@dataclass(frozen=True, slots=True)
class ReissuedInvitation:
    invitation_id: uuid.UUID
    replaces: uuid.UUID
    accept_url: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _Rejected:
    """``transition.rejected``, emitted after the transaction (step 5)."""

    ctx: TenantContext
    metadata: dict[str, str]


def reissue_owner_invitation(
    organization_id: uuid.UUID, operator: Operator, *, now: datetime | None = None
) -> ReissuedInvitation:
    base = accept_base_url()  # before any lock: a missing setting writes nothing
    moment = timezone.now() if now is None else now
    token = new_token()
    with transaction.atomic():
        ctx = _platform_context(organization_id)
        with tenant_scope(ctx):
            old = _lock_owner_invitation(ctx, ActionKind.WRITE, moment)
            outcome = _reissue_locked(ctx, old, operator, hash_token(token), moment)
    new_id = _raise_rejected(outcome, operator)
    logger.info(REISSUED_EVENT, invitation_id=str(new_id), replaces=str(old.pk))
    return ReissuedInvitation(new_id, old.pk, accept_url(base, token))


def revoke_owner_invitation(
    organization_id: uuid.UUID, operator: Operator, *, now: datetime | None = None
) -> uuid.UUID:
    moment = timezone.now() if now is None else now
    with transaction.atomic():
        ctx = _platform_context(organization_id)
        with tenant_scope(ctx):
            invitation = _lock_owner_invitation(ctx, ActionKind.REDUCE_ACCESS, moment)
            outcome: uuid.UUID | _Rejected
            if invitation.status != _PENDING:
                outcome = _rejection(ctx, invitation, REVOKE)
            else:
                _mark_revoked(ctx, invitation, RevokedReason.OPERATOR, operator, moment)
                outcome = invitation.pk
    revoked_id = _raise_rejected(outcome, operator)
    logger.info(REVOKED_EVENT, invitation_id=str(revoked_id))
    return revoked_id


def _platform_context(organization_id: uuid.UUID) -> TenantContext:
    if not isinstance(organization_id, uuid.UUID):
        raise TypeError("organization_id must be a UUID")
    return system_context(organization_id, SystemReason.PLATFORM_COMMAND)


def _lock_owner_invitation(ctx: TenantContext, kind: ActionKind, now: datetime) -> Invitation:
    """Steps 1 to 3: the organization without owner and its first owner invitation, locked."""
    mutex = lock_membership_mutex(ctx, kind)
    if active_owner_count(mutex):
        raise OrganizationHasOwnerError(ctx.organization_id)
    with bounded_lock_wait():
        invitation = (
            Invitation.objects.for_tenant(ctx)
            .select_for_update()
            .filter(purpose=InvitationPurpose.FIRST_OWNER.value)
            .order_by("-created_at", "-id")
            .first()
        )
    if invitation is None:
        raise NoOwnerInvitationError(ctx.organization_id)
    if invitation.status == _PENDING and is_expired(invitation.expires_at, now):  # Q-234 b
        expire_invitation(ctx, invitation)
    return invitation


def _reissue_locked(
    ctx: TenantContext, old: Invitation, operator: Operator, token_hash: str, now: datetime
) -> uuid.UUID | _Rejected:
    if old.status not in _REISSUABLE:
        return _rejection(ctx, old, REISSUE)
    if old.status == _PENDING:
        _mark_revoked(ctx, old, RevokedReason.RESENT, operator, now)
    new = insert_invitation(
        ctx,
        email=old.email,
        role=Role.OWNER.value,
        purpose=InvitationPurpose.FIRST_OWNER.value,
        token_hash=token_hash,
        expires_at=expires_at_for(now),
        invited_by_operator=operator.email,
        replaces=old,
    )
    record_event(
        TenancyAuditAction.INVITATION_RESENT,
        ctx=ctx,
        actor=AuditActor.platform_operator(operator.email),
        metadata={
            "invitation_id": str(new.pk),
            "replaces": str(old.pk),
            "role": Role.OWNER.value,
            "purpose": InvitationPurpose.FIRST_OWNER.value,
            "os_user": operator.os_user,
        },
    )
    return new.pk


def _mark_revoked(
    ctx: TenantContext,
    invitation: Invitation,
    reason: RevokedReason,
    operator: Operator,
    now: datetime,
) -> None:
    """No ``revoked_by``: the operator is not a user; the event names them."""
    invitation.status = InvitationStatus.REVOKED.value
    invitation.revoked_reason = reason.value
    invitation.revoked_at = now
    invitation.save(update_fields=_REVOKED_FIELDS)
    record_event(
        TenancyAuditAction.INVITATION_REVOKED,
        ctx=ctx,
        actor=AuditActor.platform_operator(operator.email),
        reason=reason.value,
        metadata={
            "invitation_id": str(invitation.pk),
            "role": str(invitation.role),
            "os_user": operator.os_user,
        },
    )


def _rejection(ctx: TenantContext, invitation: Invitation, event: str) -> _Rejected:
    state = str(invitation.status)
    metadata = {"entity": _ENTITY, "entity_id": str(invitation.pk), "state": state, "event": event}
    return _Rejected(ctx, metadata)


def _raise_rejected(outcome: uuid.UUID | _Rejected, operator: Operator) -> uuid.UUID:
    """A refusal goes out after the transaction: ``transition.rejected``, then the error."""
    if isinstance(outcome, _Rejected):
        record_event(
            TenancyAuditAction.TRANSITION_REJECTED,
            ctx=outcome.ctx,
            actor=AuditActor.platform_operator(operator.email),
            metadata={**outcome.metadata, "os_user": operator.os_user},
        )
        raise InvalidTransition
    return outcome
