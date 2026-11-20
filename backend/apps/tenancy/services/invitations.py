"""Invite somebody to the active organization (RF-TEN-05, RN-TEN-12, RN-TEN-13, design.md §4.3).

``create_invitation(ctx, email, role)`` runs after the route's ``ActionPermission``
(``invitation.create``: owner or admin, a ``WRITE``). ``normalized_email`` is the one rule of the
invitee's address, for any caller (the API's serializer, the operator's commands):
``normalize_email`` (both ends trimmed, lower case, nothing else, AC-TEN-35), then at most 254
characters and Django's ``EmailValidator`` (T-TEN-14 left it to the input). The service checks it
again (``clean_email``): a wrong one is ``400 validation_error`` on ``email`` with a fixed message
that never repeats the value.

In one transaction and in the fixed lock order (organization, then invitation):

1. ``lock_membership_mutex`` locks the organization row and reads its real status: suspended is
   ``409 organization_suspended`` (AC-TEN-28). Every membership change takes the same lock, so two
   invitations to the same email run one after the other (AC-TEN-26).
2. The actor's membership is read again under the lock (RN-TEN-08): revoked since the request was
   resolved is ``404 organization_not_found``; ``domain.role_rules.decide_invite`` with the role as
   it is now decides the role it may invite with: an admin never invites an ``owner`` (``403``,
   RN-TEN-13, AC-TEN-15).
3. An active member with that email is ``409 already_member`` (AC-TEN-20, RN-TEN-07).
4. The ``pending`` invitation of that email, locked: past its expiry it becomes ``expired`` first,
   with ``invitation.expired`` and the system as its actor (lazy expiry, RNF-TEN-04); still valid,
   ``409 invitation_pending`` and nothing changes (RN-TEN-12, AC-TEN-26).
5. The new one is inserted in a savepoint with only the SHA-256 of a fresh token (RNF-TEN-03) and
   seven days of validity, and ``invitation.created`` is emitted (ids, role and purpose; never the
   email nor the token). The partial unique ``invitation_one_pending_per_org_email`` is the last
   net: a ``pending`` one written without the lock (an operator's command) is also
   ``invitation_pending``; any other integrity error goes up as the bug it is.

``CreatedInvitation.accept_url`` is ``{FRONTEND_BASE_URL}/invitacion#token=<token>`` (design.md
§6): the token goes in the fragment, which the browser sends to no server, nor in ``Referer``. It
is the only place the token exists in clear, and it is built once: the API answers it in the
``201`` and nothing keeps it (masked in ``repr``). Without ``FRONTEND_BASE_URL`` nothing is locked
nor written: ``ImproperlyConfigured``, a generic ``500``. The refusals are not audited (none is in
RNF-TEN-04). A lock not taken within ``lock_timeout`` is ``503 organization_busy`` (Q-230). Logs
carry ids, never an email nor the token (C-06, RNF-TEN-06).

``insert_invitation`` (step 5) and ``expire_invitation`` (the lazy expiry of step 4) are shared
with resending and revoking, in ``services/invitation_manage.py`` (``C-14``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError

from apps.common.audit.port import AuditActor, AuditActorKind
from apps.common.authz.actions import ActionKind
from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.errors import Forbidden, OrganizationNotFound
from apps.common.tenancy.locks import bounded_lock_wait
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import (
    InvitationPurpose,
    InvitationStatus,
    expires_at_for,
    hash_token,
    is_expired,
    new_token,
    normalize_email,
)
from apps.tenancy.domain.role_rules import Decision, decide_invite
from apps.tenancy.models import Invitation, Membership
from apps.tenancy.models.invitation import EMAIL_MAX_LENGTH
from apps.tenancy.models.membership import MembershipStatus
from apps.tenancy.selectors.locks import MembershipMutex, actor_membership, lock_membership_mutex
from apps.tenancy.services.audit import audit_trigger, record_event

logger = get_logger(__name__)

CREATED_EVENT = "tenancy.invitation_created"
ACCEPT_PATH = "/invitacion"
INVALID_EMAIL = "Tiene que ser un email válido."
PENDING_CONSTRAINT = "invitation_one_pending_per_org_email"
# ``invitation.expired`` has the system as its actor (RNF-TEN-04): the request only noticed it.
EXPIRY_ACTOR = AuditActor(kind=AuditActorKind.SYSTEM, name="invitation_expiry")
_EMAIL_VALIDATOR = EmailValidator(message=INVALID_EMAIL)


class InviteeAlreadyMember(APIException):
    """``409 already_member``: that email is an active member of the organization (AC-TEN-20)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "already_member"
    default_detail = "Esa persona ya es miembro de la organización."


class InvitationPending(APIException):
    """``409 invitation_pending``: that email has a valid ``pending`` one already (AC-TEN-26)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_pending"
    default_detail = "Ya hay una invitación pendiente para ese email: reenviala."


@dataclass(frozen=True, slots=True)
class CreatedInvitation:
    """The new invitation, the actor's role under the lock and the link, shown only once."""

    invitation_id: uuid.UUID
    actor_role: Role
    accept_url: str = field(repr=False)


def normalized_email(value: object) -> str | None:
    """The normalized address, or ``None`` if it is not one (the caller words the error)."""
    email = normalize_email(value) if isinstance(value, str) else ""
    if not email or len(email) > EMAIL_MAX_LENGTH:
        return None
    try:
        _EMAIL_VALIDATOR(email)
    except DjangoValidationError:
        return None
    return email


def clean_email(value: object) -> str:
    """The normalized address; ``ValidationError`` on ``email``, without repeating the value."""
    email = normalized_email(value)
    if email is None:
        raise ValidationError({"email": [ErrorDetail(INVALID_EMAIL, code="invalid")]})
    return email


def accept_base_url() -> str:
    """``FRONTEND_BASE_URL``, validated by the settings (an origin, https in prod)."""
    base = getattr(settings, "FRONTEND_BASE_URL", "")
    if not base:
        raise ImproperlyConfigured("FRONTEND_BASE_URL is not set: no invitation link can be built")
    return str(base)


@audit_trigger(TenancyAuditAction.INVITATION_CREATED)
def create_invitation(
    ctx: TenantContext, email: str, role: Role, *, now: datetime | None = None
) -> CreatedInvitation:
    if not isinstance(role, Role):
        raise TypeError("role must be a Role")
    address = clean_email(email)
    base = accept_base_url()  # before any lock: a missing setting writes nothing
    moment = timezone.now() if now is None else now
    token = new_token()
    with transaction.atomic():
        invitation_id, actor_role = _create_locked(ctx, address, role, hash_token(token), moment)
    logger.info(CREATED_EVENT, invitation_id=str(invitation_id), role=role.value)
    return CreatedInvitation(invitation_id, actor_role, f"{base}{ACCEPT_PATH}#token={token}")


def _create_locked(
    ctx: TenantContext, email: str, role: Role, token_hash: str, now: datetime
) -> tuple[uuid.UUID, Role]:
    mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
    actor = actor_membership(mutex)
    if actor is None:  # revoked since the resolution: what the next request would answer
        raise OrganizationNotFound
    if decide_invite(actor.role, role) is not Decision.ALLOW:  # also a role lost since then
        raise Forbidden
    members = Membership.objects.for_tenant(ctx)
    if members.filter(user__email=email, status=MembershipStatus.ACTIVE.value).exists():
        raise InviteeAlreadyMember
    _expire_or_refuse_pending(mutex, email, now)
    invitation = insert_invitation(
        ctx,
        email=email,
        role=role.value,
        token_hash=token_hash,
        expires_at=expires_at_for(now),
        invited_by_user_id=actor.user_id,
    )
    record_event(
        TenancyAuditAction.INVITATION_CREATED,
        ctx=ctx,
        metadata={
            "invitation_id": str(invitation.pk),
            "role": role.value,
            "purpose": InvitationPurpose.STANDARD.value,
        },
    )
    return invitation.pk, actor.role


def _expire_or_refuse_pending(mutex: MembershipMutex, email: str, now: datetime) -> None:
    """The ``pending`` one of that email, locked after the organization (step 4 above)."""
    ctx = mutex.ctx
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


def expire_invitation(ctx: TenantContext, invitation: Invitation) -> None:
    """A locked ``pending`` one past its expiry becomes ``expired``; the system is the actor."""
    invitation.status = InvitationStatus.EXPIRED.value
    invitation.save(update_fields=["status", "updated_at"])
    record_event(
        TenancyAuditAction.INVITATION_EXPIRED,
        ctx=ctx,
        actor=EXPIRY_ACTOR,
        metadata={"invitation_id": str(invitation.pk)},
    )


def insert_invitation(ctx: TenantContext, **values: object) -> Invitation:
    """The ``INSERT`` in a savepoint: the pending constraint is ``invitation_pending``."""
    try:
        with transaction.atomic():
            return Invitation.objects.for_tenant(ctx).create(**values)
    except IntegrityError as error:
        diagnostics = getattr(error.__cause__, "diag", None)
        if getattr(diagnostics, "constraint_name", None) != PENDING_CONSTRAINT:
            raise
        raise InvitationPending from None
