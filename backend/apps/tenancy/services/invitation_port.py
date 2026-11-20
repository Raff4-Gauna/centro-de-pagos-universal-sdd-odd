"""SPEC-01's ``InvitationPort``, implemented by tenancy (Q-108, Q-120, RN-IDA-06, design.md §4.4).

``IDENTITY_INVITATION_PORT`` names ``TenancyInvitationPort``, so the first login of a person (case
(b) of RN-IDA-05) accepts their invitations without identity importing tenancy (design.md §6.4 of
SPEC-01). Both methods run inside the caller's transaction and never commit: they fail with
``TransactionManagementError`` outside one, where a lock would end with its statement.

- ``find_valid_invitations(email, now=)``: the ``pending`` invitations of that email, valid
  (``expires_at > now``) and of an ``active`` organization, as ``list_my_pending`` filters them.
  The organizations are read first with no lock (``organizations_with_pending``) and then locked
  one by one **in ``id`` order** (the membership mutex, ``FOR NO KEY UPDATE``), each followed by its
  invitations (``FOR UPDATE``): the fixed order of ADR-0002 §3, so two logins, or a login and an
  accept from the session, never wait on each other in a cycle. Under the lock the status is read
  again: an organization suspended meanwhile gives nothing.
- ``accept_invitations(invitations, user_id, now=)``: **all or nothing**. Each one goes, in the
  same order, through ``accept_locked``, the decision and writes of every other entry point
  (ADR-0002 §5): the same checks as accepting by token, with the person's stored email. All of them
  run in one savepoint: the first that cannot be accepted (any ``InvalidReason``, a suspended
  organization, already a member, an organization that is gone, an unknown user, an empty list)
  rolls back the ones before it and raises ``InvitationsNoLongerValid``, and the caller rolls back
  the user (AC-IDA-05). Any other error, a lock timeout included (Q-230), leaves as it comes.

The scope is ``system_context(organization_id, SystemReason.INVITATION_ACCEPT)`` of each
invitation's organization, as in ``invitation_accept.py``: the person has no membership yet. The
tenancy audit (``membership.created``, ``invitation.accepted``, the person as actor) is written
inside the transaction by ``accept_locked``; identity records its own events. Logs carry ids only,
never an email (C-06, RNF-TEN-06), and an acceptance is logged only once it commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime

from django.db import transaction

from apps.common.authz.actions import ActionKind
from apps.common.logging import get_logger
from apps.common.tenancy.context import OrgStatus, SystemReason, TenantContext
from apps.common.tenancy.current import tenant_scope
from apps.common.tenancy.errors import OrganizationNotFound, OrganizationSuspended
from apps.common.tenancy.locks import require_transaction, system_context
from apps.identity.ports.invitations import InvitationRef, InvitationsNoLongerValid
from apps.identity.selectors.users import get_by_id
from apps.tenancy.selectors.invitations import lock_pending_for_email, organizations_with_pending
from apps.tenancy.selectors.locks import lock_membership_mutex
from apps.tenancy.services.invitation_accept import (
    ACCEPTED_EVENT,
    REFUSED_EVENT,
    AcceptedInvitation,
    AlreadyMember,
    Invitee,
    accept_locked,
)

logger = get_logger(__name__)

# What the port answers for a refusal that names no ``InvalidReason``.
_UNUSABLE = "unusable"


class TenancyInvitationPort:
    def find_valid_invitations(
        self, email_normalized: str, *, now: datetime
    ) -> list[InvitationRef]:
        require_transaction("find_valid_invitations")
        found: list[InvitationRef] = []
        for organization_id in organizations_with_pending(email_normalized, now=now):
            ctx = _scope(organization_id)
            with tenant_scope(ctx):
                mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
                if mutex.organization_status is not OrgStatus.ACTIVE:
                    continue  # suspended since the first read: not valid any more
                ids = lock_pending_for_email(mutex, email_normalized, now=now)
            found.extend(InvitationRef(invitation_id, organization_id) for invitation_id in ids)
        return found

    def accept_invitations(
        self, invitations: Sequence[InvitationRef], user_id: uuid.UUID, *, now: datetime
    ) -> None:
        require_transaction("accept_invitations")
        ordered = sorted(invitations, key=lambda ref: (ref.organization_id, ref.invitation_id))
        user = get_by_id(user_id)
        if not ordered or user is None:
            _refused(_UNUSABLE, user_id, None)
            raise InvitationsNoLongerValid
        invitee = Invitee(user_id=user.pk, email=user.email)
        accepted: list[tuple[uuid.UUID, AcceptedInvitation]] = []
        current: uuid.UUID | None = None
        try:
            with transaction.atomic():
                for ref in ordered:
                    current = ref.invitation_id
                    accepted.append((current, _accept_one(ref, invitee, now=now)))
        except (AlreadyMember, OrganizationNotFound, OrganizationSuspended) as refusal:
            _refused(str(refusal.default_code), user_id, current)
            raise InvitationsNoLongerValid from None
        for invitation_id, outcome in accepted:
            transaction.on_commit(_log_accepted(invitation_id, outcome, user_id))


def _accept_one(ref: InvitationRef, invitee: Invitee, *, now: datetime) -> AcceptedInvitation:
    ctx = _scope(ref.organization_id)
    with tenant_scope(ctx):
        mutex = lock_membership_mutex(ctx, ActionKind.WRITE)
        outcome = accept_locked(mutex, ref.invitation_id, invitee, now=now)
    if isinstance(outcome, AcceptedInvitation):
        return outcome
    _refused(str(outcome), invitee.user_id, ref.invitation_id)
    raise InvitationsNoLongerValid  # inside the savepoint: the ones before it roll back too


def _scope(organization_id: uuid.UUID) -> TenantContext:
    """The invitation's organization, as ``invitation_accept._accept_context`` builds it."""
    return system_context(organization_id, SystemReason.INVITATION_ACCEPT)


def _log_accepted(
    invitation_id: uuid.UUID, outcome: AcceptedInvitation, user_id: uuid.UUID
) -> Callable[[], None]:
    return lambda: logger.info(
        ACCEPTED_EVENT,
        via="login",
        invitation_id=str(invitation_id),
        membership_id=str(outcome.membership_id),
        user_id=str(user_id),
    )


def _refused(reason: str, user_id: uuid.UUID, invitation_id: uuid.UUID | None) -> None:
    logger.warning(
        REFUSED_EVENT,
        via="login",
        reason=reason,
        invitation_id=None if invitation_id is None else str(invitation_id),
        user_id=str(user_id),
    )
