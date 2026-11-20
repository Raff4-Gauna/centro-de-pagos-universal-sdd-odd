"""Accept an invitation: the one way into an organization (RN-TEN-11, RN-TEN-12, design.md §4.4).

The only acceptance path (ADR-0002 §5), shared by every entry point:

- ``accept_by_token(token, invitee)``: ``POST /api/invitations/accept/`` (T-TEN-15). The token is
  hashed and looked up once (``selectors.invitations.find_by_token``); no row is ``not_found``.
- ``accept_from_session(invitation_id, invitee)``: ``POST /api/invitations/{id}/accept/``
  (T-TEN-16, Q-121, Q-124), in the three steps of §4.4. (1) It reads the row by id with
  ``Invitation.objects.for_session_accept`` (any organization: the only file allowed to,
  ``allowlists.RESTRICTED_SCOPE_ALLOWLIST``), with no transaction and no lock, so somebody else's
  attempt locks nothing. (2) No row, or a row of another email, is ``not_found`` with the same body;
  for an existing row ``invitation.rejected`` (``email_mismatch``, the person as actor, no email)
  goes out on its own, outside any transaction, and the row stays ``pending``. (3) The holder goes
  on to ``accept_invitation`` with ``mismatch=InvalidReason.NOT_FOUND``: if the email no longer
  matches under the lock it answers the same ``not_found`` (that contract has no
  ``email_mismatch``).
- ``accept_invitation(ref, invitee, mismatch=...)``: the rest of the diagram for a known row.
- ``accept_locked(mutex, invitation_id, invitee, now=)``: the decision and the writes, inside a
  transaction that already holds the organization's ``MembershipMutex``. The port of SPEC-01
  (T-TEN-17) calls it inside its own all-or-nothing transaction and turns a refusal into its error.

The person has no membership in that organization yet, so there is no ``UserActor``: the scope is
``system_context(organization_id, SystemReason.INVITATION_ACCEPT)`` of the invitation's own
organization, opened before anything is read under it or written (``tenant_scope``). Every read
and write goes through ``for_tenant`` of that scope: the membership is created in the organization
of the invitation, never in another one, and an id of another organization's invitation is
``not_found``. The suspension does not stop a ``SystemActor`` by itself, so it is checked here on
the status read under the lock; the audit names the person as the actor, not the system.

Order (§4.4): lock the organization (``FOR NO KEY UPDATE``, the membership mutex) and then the
invitation (``FOR UPDATE``); then another email (``email_mismatch``, stays ``pending``), a status
other than ``pending`` (``used``, ``revoked``, ``expired``), the clock (a ``pending`` one past
``expires_at`` becomes ``expired`` and that is committed, with ``invitation.expired``), a suspended
organization (``409 organization_suspended``), already a member (``409 already_member``, stays
``pending``). A second accept in parallel waits for the lock and reads ``accepted``: ``used``.

``invitation.rejected`` (another email) is emitted after the transaction, in its own write, so the
refusal does not roll it back (design.md §3.3). Logs carry ids only: never the token, its hash nor
an email (C-06, RNF-TEN-06).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.common.audit.port import AuditActor, AuditActorKind
from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationSuspended
from apps.common.tenancy.locks import bounded_lock_wait, system_context
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import (
    InvalidReason,
    InvitationStatus,
    decide_accept,
    emails_match,
)
from apps.tenancy.models import Invitation, Membership, Organization
from apps.tenancy.models.membership import MembershipStatus
from apps.tenancy.selectors.invitations import InvitationRef, find_by_token
from apps.tenancy.selectors.locks import MembershipMutex, lock_membership_mutex
from apps.tenancy.services.audit import audit_trigger, record_event

logger = get_logger(__name__)

ACCEPTED_EVENT = "tenancy.invitation_accepted"
REFUSED_EVENT = "tenancy.invitation_refused"
# What a refused other email may answer: its own reason, or a missing invitation (T-TEN-16).
MISMATCH_ANSWERS = frozenset({InvalidReason.EMAIL_MISMATCH, InvalidReason.NOT_FOUND})


class InvitationInvalid(APIException):
    """``400 invitation_invalid`` with its ``reason``; the body never repeats the input."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invitation_invalid"
    default_detail = "La invitación no es válida o ya no está vigente."

    def __init__(self, reason: InvalidReason) -> None:
        super().__init__()
        self.problem_reason = InvalidReason(reason).value


class AlreadyMember(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "already_member"
    default_detail = "Ya sos miembro de esta organización."


@dataclass(frozen=True, slots=True)
class Invitee:
    """The authenticated person who accepts: their id and their Google email (RN-TEN-11)."""

    user_id: uuid.UUID
    email: str


@dataclass(frozen=True, slots=True)
class AcceptedInvitation:
    organization_id: uuid.UUID
    organization_name: str
    role: Role
    membership_id: uuid.UUID


def accept_by_token(
    token: str, invitee: Invitee, *, now: datetime | None = None
) -> AcceptedInvitation:
    ref = find_by_token(token)
    if ref is None:
        _refused(InvalidReason.NOT_FOUND, invitee, None)
        raise InvitationInvalid(InvalidReason.NOT_FOUND)
    return accept_invitation(ref, invitee, now=now)


@audit_trigger(
    TenancyAuditAction.INVITATION_ACCEPTED,
    TenancyAuditAction.MEMBERSHIP_CREATED,
    TenancyAuditAction.INVITATION_REJECTED,
)
def accept_invitation(
    ref: InvitationRef,
    invitee: Invitee,
    *,
    now: datetime | None = None,
    mismatch: InvalidReason = InvalidReason.EMAIL_MISMATCH,
) -> AcceptedInvitation:
    if mismatch not in MISMATCH_ANSWERS:
        raise ValueError("another email answers email_mismatch or not_found")
    moment = timezone.now() if now is None else now
    ctx = _accept_context(ref.organization_id)
    with tenant_scope(ctx):
        try:
            with transaction.atomic():
                mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
                outcome = accept_locked(mutex, ref.invitation_id, invitee, now=moment)
        except (AlreadyMember, OrganizationSuspended) as refusal:
            _refused(str(refusal.default_code), invitee, ref.invitation_id)
            raise
        if isinstance(outcome, AcceptedInvitation):
            logger.info(
                ACCEPTED_EVENT,
                invitation_id=str(ref.invitation_id),
                membership_id=str(outcome.membership_id),
                user_id=str(invitee.user_id),
            )
            return outcome
        if outcome is InvalidReason.EMAIL_MISMATCH:
            _rejected(ctx, ref.invitation_id, invitee)
        _refused(outcome, invitee, ref.invitation_id)
    raise InvitationInvalid(mismatch if outcome is InvalidReason.EMAIL_MISMATCH else outcome)


def accept_from_session(
    invitation_id: uuid.UUID, invitee: Invitee, *, now: datetime | None = None
) -> AcceptedInvitation:
    row = (
        Invitation.objects.for_session_accept(invitation_id)
        .values_list("organization_id", "email")
        .first()
    )
    if row is None:
        _refused(InvalidReason.NOT_FOUND, invitee, None)
        raise InvitationInvalid(InvalidReason.NOT_FOUND)
    ref = InvitationRef(invitation_id, row[0])
    if not emails_match(row[1], invitee.email):  # another person's: nothing is locked or written
        _rejected(_accept_context(ref.organization_id), invitation_id, invitee)
        _refused(InvalidReason.EMAIL_MISMATCH, invitee, invitation_id)
        raise InvitationInvalid(InvalidReason.NOT_FOUND)
    return accept_invitation(ref, invitee, now=now, mismatch=InvalidReason.NOT_FOUND)


def accept_locked(
    mutex: MembershipMutex, invitation_id: uuid.UUID, invitee: Invitee, *, now: datetime
) -> AcceptedInvitation | InvalidReason:
    """Accept it in the mutex's transaction, or say why not (``already_member`` and a suspended
    organization raise, they write nothing). An expired ``pending`` one is left ``expired``."""
    ctx = mutex.ctx
    with bounded_lock_wait():
        invitation = (
            Invitation.objects.for_tenant(ctx).select_for_update().filter(pk=invitation_id).first()
        )
    if invitation is None:  # none, or another organization's: the scope does not reach it
        return InvalidReason.NOT_FOUND
    reason = decide_accept(
        status=InvitationStatus(invitation.status),
        expires_at=invitation.expires_at,
        invited_email=invitation.email,
        user_email=invitee.email,
        now=now,
    )
    if reason is InvalidReason.EXPIRED and invitation.status == InvitationStatus.PENDING:
        _expire(ctx, invitation)
    if reason is not None:
        return reason
    if mutex.organization_status is OrgStatus.SUSPENDED:
        raise OrganizationSuspended
    members = Membership.objects.for_tenant(ctx)
    if members.filter(user_id=invitee.user_id, status=MembershipStatus.ACTIVE.value).exists():
        raise AlreadyMember
    return _accept(ctx, invitation, invitee, now)


def _accept(
    ctx: TenantContext, invitation: Invitation, invitee: Invitee, now: datetime
) -> AcceptedInvitation:
    if invitation.organization_id != ctx.organization_id:  # the scope already ensures it
        raise AssertionError("an invitation is accepted in its own organization only")
    membership = Membership.objects.for_tenant(ctx).create(
        user_id=invitee.user_id,
        role=invitation.role,
        invited_by_id=invitation.invited_by_user_id,
        source_invitation=invitation,
    )
    invitation.status = InvitationStatus.ACCEPTED.value
    invitation.accepted_by_id = invitee.user_id
    invitation.accepted_at = now
    invitation.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])
    metadata = {
        "invitation_id": str(invitation.pk),
        "membership_id": str(membership.pk),
        "role": invitation.role,
    }
    for action in (TenancyAuditAction.MEMBERSHIP_CREATED, TenancyAuditAction.INVITATION_ACCEPTED):
        record_event(action, ctx=ctx, actor=_person(invitee), metadata=metadata)
    name = Organization.objects.for_tenant(ctx).values_list("name", flat=True).get()
    return AcceptedInvitation(ctx.organization_id, name, Role(invitation.role), membership.pk)


def _expire(ctx: TenantContext, invitation: Invitation) -> None:
    """Seen past its expiry while ``pending``: ``expired`` for good, by the system (Q-225)."""
    invitation.status = InvitationStatus.EXPIRED.value
    invitation.save(update_fields=["status", "updated_at"])
    record_event(
        TenancyAuditAction.INVITATION_EXPIRED,
        ctx=ctx,
        metadata={"invitation_id": str(invitation.pk)},
    )


def _accept_context(organization_id: uuid.UUID) -> TenantContext:
    """The scope of the invitation's organization; the status is read again under the lock."""
    return system_context(organization_id, SystemReason.INVITATION_ACCEPT)


def _rejected(ctx: TenantContext, invitation_id: uuid.UUID, invitee: Invitee) -> None:
    """Another email tried it: audited after (or without) the transaction, so a refusal does not
    roll it back (design.md §3.3, RNF-TEN-04); the id only, no email of anyone."""
    record_event(
        TenancyAuditAction.INVITATION_REJECTED,
        ctx=ctx,
        actor=_person(invitee),
        reason=InvalidReason.EMAIL_MISMATCH.value,
        metadata={"invitation_id": str(invitation_id)},
    )


def _person(invitee: Invitee) -> AuditActor:
    return AuditActor(kind=AuditActorKind.USER, id=invitee.user_id)


def _refused(reason: str, invitee: Invitee, invitation_id: uuid.UUID | None) -> None:
    logger.warning(
        REFUSED_EVENT,
        reason=str(reason),
        invitation_id=None if invitation_id is None else str(invitation_id),
        user_id=str(invitee.user_id),
    )
