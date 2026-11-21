"""The platform operator's support access and owner recovery (RF-TEN-07, RN-TEN-20, Q-222, Q-224).

Only ``manage.py tenancy_support_access`` and ``manage.py tenancy_owner_recovery`` call this. Being
the operator gives no access to an organization's data (RN-TEN-20, AC-TEN-33): both issue an
**invitation**, never a membership, and the person gets in by accepting it like anybody else
(design.md §4.4). The command checks ``--operator`` against ``PLATFORM_OPERATOR_EMAILS`` before it
gets here; the operator (that email) is the actor of the event, with ``os_user`` in ``metadata``.

- ``grant_support_access`` (Q-222): ``purpose=support``, the role chosen (``viewer`` by default)
  and never ``owner`` (``SupportRoleError``). Accepted, it is a normal membership: visible among the
  members and revocable by the owners, with exactly the permissions of its role (spec §4).
- ``issue_owner_recovery`` (Q-224): an ``owner`` invitation, ``purpose=owner_recovery``, for an
  organization that **has** an active owner (spec §4, "org con owner"): without one, the first
  owner's invitation is the way (``tenancy_owner_invite``, Q-213), so this one is
  ``OrganizationWithoutOwnerError``. Nobody is revoked, no membership and no other invitation is
  touched. The notice to the existing owners waits for an email provider (Q-224, Q-207): there is
  none yet, so nobody is notified; ``IssuedAccess.owners`` says how many remain.

Both carry a mandatory reason (Q-225, ``invitation_operator_reason``), the rule of
``tenancy_set_org_status`` (``clean_reason``: 1 to 200 characters), kept on the invitation and in
the event's ``reason``, never in the logs. In one transaction and in the lock order of the module
(organization, then invitation), as creating an invitation (``services/invitations.py``):

1. ``tenant_scope(system_context(org, PLATFORM_COMMAND))``; ``lock_membership_mutex`` takes the
   organization's lock (an unknown one is ``OrganizationNotFound``). A ``SystemActor`` is not
   stopped by a suspension (design.md §3.6), as ``tenancy_owner_invite``; accepting it waits for
   the organization to be active again (AC-TEN-28).
2. Recovery only: no active owner is ``OrganizationWithoutOwnerError``.
3. An active member with that email is ``already_member`` (AC-TEN-20).
4. The ``pending`` invitation of that email, ``FOR UPDATE``: past its expiry it becomes ``expired``
   first (``invitation.expired``, the system as its actor); still valid, ``invitation_pending``.
5. The new one, issued by the operator, with only the SHA-256 of a fresh token and seven days of
   validity (``insert_invitation``), and ``invitation.created`` with its role and ``purpose``
   (AC-TEN-23, Q-225: they have no event of their own).

Every refusal writes nothing and is not audited, as creating an invitation (none is in
RNF-TEN-04). ``IssuedAccess.accept_url`` is the only place the token exists in clear (masked in
``repr``); the command prints it once. Without ``FRONTEND_BASE_URL`` nothing is locked nor
written. Logs and events carry ids, never an email nor the token (C-06, RNF-TEN-06).
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
    expires_at_for,
    hash_token,
    is_expired,
    new_token,
)
from apps.tenancy.models import Invitation, Membership
from apps.tenancy.models.membership import MembershipStatus
from apps.tenancy.selectors.locks import active_owner_count, lock_membership_mutex
from apps.tenancy.services.audit import record_event
from apps.tenancy.services.invitations import (
    InvitationPending,
    InviteeAlreadyMember,
    accept_base_url,
    accept_url,
    expire_invitation,
    insert_invitation,
    normalized_email,
)
from apps.tenancy.services.platform_org import Operator
from apps.tenancy.services.platform_org_status import clean_reason

logger = get_logger(__name__)

SUPPORT_EVENT = "tenancy.platform_support_access_issued"
RECOVERY_EVENT = "tenancy.platform_owner_recovery_issued"
SUPPORT_ROLES = (Role.ADMIN, Role.OPERATOR, Role.VIEWER)  # Q-222: never owner
DEFAULT_SUPPORT_ROLE = Role.VIEWER


class InvalidInviteeEmailError(ValueError):
    """``--email`` is not an email address; the message never repeats the value."""

    def __init__(self) -> None:
        super().__init__("the email is not a valid email address")


class SupportRoleError(ValueError):
    """Support access is never ``owner`` (Q-222): recovery is the only operator way (Q-224)."""

    def __init__(self) -> None:
        super().__init__("support access takes admin, operator or viewer, never owner")


class OrganizationWithoutOwnerError(Exception):
    """Recovery is for an organization with an owner; without one, ``tenancy_owner_invite``."""

    def __init__(self, organization_id: uuid.UUID) -> None:
        super().__init__("the organization has no active owner")
        self.organization_id = organization_id


@dataclass(frozen=True, slots=True)
class IssuedAccess:
    invitation_id: uuid.UUID
    role: Role
    owners: int
    accept_url: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _Request:
    email: str
    role: Role
    purpose: InvitationPurpose
    reason: str
    log_event: str


def clean_invitee_email(value: object) -> str:
    email = normalized_email(value)
    if email is None:
        raise InvalidInviteeEmailError
    return email


def grant_support_access(
    organization_id: uuid.UUID,
    email: str,
    reason: str,
    operator: Operator,
    *,
    role: Role = DEFAULT_SUPPORT_ROLE,
    now: datetime | None = None,
) -> IssuedAccess:
    if role not in SUPPORT_ROLES:
        raise SupportRoleError
    request = _Request(
        clean_invitee_email(email),
        Role(role),
        InvitationPurpose.SUPPORT,
        clean_reason(reason),
        SUPPORT_EVENT,
    )
    return _issue(organization_id, request, operator, now)


def issue_owner_recovery(
    organization_id: uuid.UUID,
    email: str,
    reason: str,
    operator: Operator,
    *,
    now: datetime | None = None,
) -> IssuedAccess:
    request = _Request(
        clean_invitee_email(email),
        Role.OWNER,
        InvitationPurpose.OWNER_RECOVERY,
        clean_reason(reason),
        RECOVERY_EVENT,
    )
    return _issue(organization_id, request, operator, now)


def _issue(
    organization_id: uuid.UUID, request: _Request, operator: Operator, now: datetime | None
) -> IssuedAccess:
    if not isinstance(organization_id, uuid.UUID):
        raise TypeError("organization_id must be a UUID")
    base = accept_base_url()  # before any lock: a missing setting writes nothing
    moment = timezone.now() if now is None else now
    token = new_token()
    with transaction.atomic():
        ctx = system_context(organization_id, SystemReason.PLATFORM_COMMAND)
        with tenant_scope(ctx):
            invitation_id, owners = _issue_locked(ctx, request, operator, hash_token(token), moment)
    logger.info(
        request.log_event,
        invitation_id=str(invitation_id),
        role=request.role.value,
        purpose=request.purpose.value,
    )
    return IssuedAccess(invitation_id, request.role, owners, accept_url(base, token))


def _issue_locked(
    ctx: TenantContext, request: _Request, operator: Operator, token_hash: str, now: datetime
) -> tuple[uuid.UUID, int]:
    mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
    owners = active_owner_count(mutex)
    if request.purpose is InvitationPurpose.OWNER_RECOVERY and not owners:
        raise OrganizationWithoutOwnerError(ctx.organization_id)
    members = Membership.objects.for_tenant(ctx)
    if members.filter(user__email=request.email, status=MembershipStatus.ACTIVE.value).exists():
        raise InviteeAlreadyMember
    _expire_or_refuse_pending(ctx, request.email, now)
    invitation = insert_invitation(
        ctx,
        email=request.email,
        role=request.role.value,
        purpose=request.purpose.value,
        reason=request.reason,
        token_hash=token_hash,
        expires_at=expires_at_for(now),
        invited_by_operator=operator.email,
    )
    record_event(
        TenancyAuditAction.INVITATION_CREATED,
        ctx=ctx,
        actor=AuditActor.platform_operator(operator.email),
        reason=request.reason,
        metadata={
            "invitation_id": str(invitation.pk),
            "role": request.role.value,
            "purpose": request.purpose.value,
            "os_user": operator.os_user,
        },
    )
    return invitation.pk, owners


def _expire_or_refuse_pending(ctx: TenantContext, email: str, now: datetime) -> None:
    """Step 4, after the organization's lock, as ``services/invitations.py`` does."""
    with bounded_lock_wait():
        pending = (
            Invitation.objects.for_tenant(ctx)
            .select_for_update()
            .filter(email=email, status=InvitationStatus.PENDING.value)
            .first()
        )
    if pending is None:
        return
    if not is_expired(pending.expires_at, now):
        raise InvitationPending
    expire_invitation(ctx, pending)
