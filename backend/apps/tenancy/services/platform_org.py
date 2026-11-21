"""The platform operator creates an organization (RF-TEN-07, RN-TEN-10, AC-TEN-22, design.md §4.5).

Only ``manage.py tenancy_create_org`` calls this: there is no HTTP way to create an organization
(AC-TEN-21, AC-IDA-32). It is how **every** organization of the MVP is born (Q-123 of SPEC-01).
The command checks ``--operator`` against ``PLATFORM_OPERATOR_EMAILS`` before it gets here
(``apps.common.platform_operators``); the operator (that email) is the actor of every event, with
the user of the operating system in ``metadata`` (``os_user``).

``create_platform_org(request, operator)``, in one transaction:

1. ``platform_creation_key`` is unique: the key already taken (by an earlier run, or by one running
   at the same time, whose ``INSERT`` this one waits for and then fails in a savepoint) is
   idempotency. Same name and same owner email as that run (its first ``first_owner`` invitation)
   → nothing is written and no token is issued: the result says ``created=False``. Other values
   → ``CreationKeyConflictError`` and nothing is written either (design.md §4.5 step 2). Every
   repeat is audited all the same (Q-235, RN-IDA-23): one ``organization.create_repeated`` with
   ``outcome`` ``no_change`` or ``conflict``, emitted after the transaction, as the audited
   rejections are (design.md §3.3), so a conflict's rollback does not take it.
2. Otherwise ``Organization(status=active, created_by_operator=<operator>)``, then, under
   ``tenant_scope(system_context(org, PLATFORM_COMMAND))``, ``Invitation(role=owner,
   purpose=first_owner, invited_by_operator=<operator>)`` with only the SHA-256 of a fresh token
   and seven days of validity, and the events ``organization.created`` and ``invitation.created``
   (ids, role and purpose; never an email nor the token).

No membership is ever created (Q-124, AC-TEN-40): if the owner's email already has a user, the
invitation is issued all the same and that person accepts it inside the Hub. The new organization
has no owner until then, the one exception to RN-TEN-14 (Q-213).

``PlatformOrg.accept_url`` is built by ``services.invitations.accept_url``, the same link as any
invitation, once: the command prints it on stdout and nothing keeps it (masked in ``repr``).
Without ``FRONTEND_BASE_URL`` nothing is written (``ImproperlyConfigured``). Logs carry ids only,
never an email nor the token (C-06, RNF-TEN-06).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.audit.port import AuditActor
from apps.common.authz.roles import Role
from apps.common.logging import get_logger
from apps.common.tenancy.context import SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.locks import system_context
from apps.common.tenancy.querysets import UnscopedReason
from apps.tenancy.domain.audit_events import TenancyAuditAction
from apps.tenancy.domain.invitations import (
    InvitationPurpose,
    expires_at_for,
    hash_token,
    new_token,
)
from apps.tenancy.models import Invitation, Organization
from apps.tenancy.services.audit import audit_trigger, record_event
from apps.tenancy.services.invitations import accept_base_url, accept_url, normalized_email

logger = get_logger(__name__)

CREATED_EVENT = "tenancy.platform_org_created"
REPEATED_EVENT = "tenancy.platform_org_repeated"
NO_CHANGE = "no_change"
CONFLICT = "conflict"
KEY_MAX_LENGTH = 64
NAME_MAX_LENGTH = 120


class InvalidOrgRequestError(ValueError):
    """A bad ``--key``, ``--name`` or ``--owner-email``; the message never repeats the value."""


class CreationKeyConflictError(Exception):
    """The key belongs to an organization created with another name or owner email."""

    def __init__(self, organization_id: uuid.UUID) -> None:
        super().__init__("that key already created an organization with other values")
        self.organization_id = organization_id


@dataclass(frozen=True, slots=True)
class OrgRequest:
    """What the operator asks for, already validated (``clean_request``)."""

    key: str
    name: str
    owner_email: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Operator:
    """Who runs the command: an email of ``PLATFORM_OPERATOR_EMAILS`` and the OS user."""

    email: str
    os_user: str


@dataclass(frozen=True, slots=True)
class PlatformOrg:
    """The organization; on a new one, its owner invitation and the link, shown only once."""

    organization_id: uuid.UUID
    created: bool
    invitation_id: uuid.UUID | None = None
    accept_url: str | None = field(default=None, repr=False)


def clean_request(*, key: object, name: object, owner_email: object) -> OrgRequest:
    clean_key = key.strip() if isinstance(key, str) else ""
    if not 0 < len(clean_key) <= KEY_MAX_LENGTH:
        raise InvalidOrgRequestError(f"the key must have between 1 and {KEY_MAX_LENGTH} characters")
    clean_name = name.strip() if isinstance(name, str) else ""
    if not 0 < len(clean_name) <= NAME_MAX_LENGTH:
        raise InvalidOrgRequestError(
            f"the name must have between 1 and {NAME_MAX_LENGTH} characters"
        )
    email = normalized_email(owner_email)
    if email is None:
        raise InvalidOrgRequestError("the owner email is not a valid email address")
    return OrgRequest(key=clean_key, name=clean_name, owner_email=email)


@audit_trigger(
    TenancyAuditAction.ORGANIZATION_CREATED, TenancyAuditAction.ORGANIZATION_CREATE_REPEATED
)
def create_platform_org(
    request: OrgRequest, operator: Operator, *, now: datetime | None = None
) -> PlatformOrg:
    base = accept_base_url()  # before anything is written: a missing setting writes nothing
    moment = timezone.now() if now is None else now
    token = new_token()
    with transaction.atomic():
        organization_id, created = _claim_key(request, operator)
        ctx = system_context(organization_id, SystemReason.PLATFORM_COMMAND)
        with tenant_scope(ctx):
            if not created:
                same = _is_same_request(ctx, request)
            else:
                invitation_id = _issue_owner_invitation(ctx, request, operator, token, moment)
    if not created:
        return _repeated(ctx, operator, same=same)
    logger.info(
        CREATED_EVENT, organization_id=str(organization_id), invitation_id=str(invitation_id)
    )
    return PlatformOrg(organization_id, True, invitation_id, accept_url(base, token))


def _claim_key(request: OrgRequest, operator: Operator) -> tuple[uuid.UUID, bool]:
    """The organization of the key and whether this run created it (step 1 above)."""
    organizations = Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND)
    existing = organizations.filter(platform_creation_key=request.key).values_list("pk", flat=True)
    found = existing.first()
    if found is not None:
        return found, False
    try:
        with transaction.atomic():  # a savepoint: a run that took the key first is not an error
            organization = organizations.create(
                name=request.name,
                platform_creation_key=request.key,
                created_by_operator=operator.email,
            )
    except IntegrityError:
        found = existing.first()
        if found is None:
            raise
        return found, False
    return organization.pk, True


def _repeated(ctx: TenantContext, operator: Operator, *, same: bool) -> PlatformOrg:
    """The audit of a repeated key (Q-235); a conflict raises after it, with nothing written."""
    outcome = NO_CHANGE if same else CONFLICT
    record_event(
        TenancyAuditAction.ORGANIZATION_CREATE_REPEATED,
        ctx=ctx,
        actor=AuditActor.platform_operator(operator.email),
        metadata={"outcome": outcome, "os_user": operator.os_user},
    )
    logger.info(REPEATED_EVENT, organization_id=str(ctx.organization_id), outcome=outcome)
    if not same:
        raise CreationKeyConflictError(ctx.organization_id)
    return PlatformOrg(ctx.organization_id, created=False)


def _is_same_request(ctx: TenantContext, request: OrgRequest) -> bool:
    """Same name and owner email as the first owner invitation of the organization."""
    name = Organization.objects.for_tenant(ctx).values_list("name", flat=True).get()
    first_owner = (
        Invitation.objects.for_tenant(ctx)
        .filter(purpose=InvitationPurpose.FIRST_OWNER.value, replaces__isnull=True)
        .order_by("created_at", "id")
        .values_list("email", flat=True)
        .first()
    )
    return name == request.name and first_owner == request.owner_email


def _issue_owner_invitation(
    ctx: TenantContext, request: OrgRequest, operator: Operator, token: str, now: datetime
) -> uuid.UUID:
    invitation = Invitation.objects.for_tenant(ctx).create(
        email=request.owner_email,
        role=Role.OWNER.value,
        purpose=InvitationPurpose.FIRST_OWNER.value,
        token_hash=hash_token(token),
        expires_at=expires_at_for(now),
        invited_by_operator=operator.email,
    )
    actor = AuditActor.platform_operator(operator.email)
    record_event(
        TenancyAuditAction.ORGANIZATION_CREATED,
        ctx=ctx,
        actor=actor,
        metadata={"os_user": operator.os_user},
    )
    record_event(
        TenancyAuditAction.INVITATION_CREATED,
        ctx=ctx,
        actor=actor,
        metadata={
            "invitation_id": str(invitation.pk),
            "role": Role.OWNER.value,
            "purpose": InvitationPurpose.FIRST_OWNER.value,
            "os_user": operator.os_user,
        },
    )
    return invitation.pk
