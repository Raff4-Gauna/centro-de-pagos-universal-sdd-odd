"""Celery tasks of tenancy (RF-TEN-05, AC-TEN-37, Q-207, Q-225, design.md §3.6, §7).

Expiry (AC-TEN-37), on beat (``beat.py``):

- ``expire_invitations`` is a ``SystemFanoutTask``: with no tenant it **only** lists
  ``(organization_id, id)`` of the ``pending`` invitations past their expiry, with
  ``unscoped(SYSTEM_FANOUT)`` (``allowlists.UNSCOPED_ALLOWLIST``), and enqueues one
  ``expire_invitation`` per pair through ``fan_out``. It reads nothing else and writes nothing.
- ``expire_invitation`` is a ``TenantTask``: in its organization's scope it runs
  ``services.invitations.expire_due_invitation``, which re-reads the row under the locks and only
  expires it if it is still due, with ``invitation.expired`` and ``SystemReason.INVITATION_EXPIRY``
  as the actor (Q-225). A pair that changed since the listing (accepted, revoked, renewed) is a
  no-op, so a late or repeated run does no harm.

Invitation email (Q-207), behind the flag ``TENANCY_INVITATION_EMAIL_ENABLED`` (off):

- ``queue_invitation_email`` is called by the API after creating or resending. With the flag off
  it returns at once: nothing is enqueued, so the token never goes through the broker. With the
  flag on it enqueues ``send_invitation_email`` after the commit, as design.md §7 says: the link is
  in the message, ``kwargsrepr`` shows it as ``[redacted]`` (worker events, ``inspect``) and the
  message ``expires`` in 15 minutes, so a stopped worker does not keep it for long.
- ``send_invitation_email`` reads the flag again, and sends only if the invitation is still
  ``pending`` and valid: a revoked or renewed one is skipped (its link no longer works). There is
  no email provider yet (Q-207): dev uses Django's console backend. It has no automatic retry: a
  Celery retry re-publishes the kwargs without ``kwargsrepr``, so the link would reach the worker's
  events in clear; a failed send is a ``FAILURE`` (logged without kwargs, ``celery_signals.py``)
  and the owner or admin resends (the link was shown once anyway).

Logs carry ids, never an email, the link nor the token (C-06, RNF-TEN-06).
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from celery import shared_task
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.common.feature_flags import is_enabled
from apps.common.logging import get_logger
from apps.common.tenancy.celery import ORGANIZATION_KWARG, SystemFanoutTask, TenantTask
from apps.common.tenancy.context import TenantContext
from apps.common.tenancy.current import require_current_tenant
from apps.common.tenancy.querysets import UnscopedReason
from apps.tenancy.beat import EXPIRE_TASK
from apps.tenancy.domain.invitations import InvitationStatus, is_expired
from apps.tenancy.models import Invitation
from apps.tenancy.selectors.invitations import get_invitation
from apps.tenancy.selectors.organizations import get_organization
from apps.tenancy.services.invitations import expire_due_invitation

logger = get_logger(__name__)

EXPIRE_ONE_TASK = "tenancy.expire_invitation"
EMAIL_TASK = "tenancy.send_invitation_email"
EMAIL_FLAG = "TENANCY_INVITATION_EMAIL_ENABLED"
EMAIL_EXPIRES_SECONDS = 15 * 60
REDACTED = "[redacted]"
LINK_KWARG = "accept_url"
EMAIL_SENT_EVENT = "tenancy.invitation_email_sent"
EMAIL_SKIPPED_EVENT = "tenancy.invitation_email_skipped"
FANOUT_EVENT = "tenancy.invitation_expiry_fanout"
SUBJECT = "Te invitaron a {organization} en el Centro de Pagos"
BODY = (
    "Te invitaron a sumarte a {organization} en el Centro de Pagos.\n\n"
    "Para aceptar, entrá con tu cuenta de Google en este link:\n{link}\n\n"
    "El link es personal, se usa una sola vez y vence el {expires} (UTC).\n"
    "Si no esperabas esta invitación, ignorá este email.\n"
)


@shared_task(base=TenantTask, name=EXPIRE_ONE_TASK, ignore_result=True)
def expire_invitation(*, organization_id: str, invitation_id: str) -> bool:
    """One due invitation of the task's organization; ``False`` if it is no longer due."""
    return expire_due_invitation(require_current_tenant(), uuid.UUID(invitation_id))


@shared_task(base=SystemFanoutTask, bind=True, name=EXPIRE_TASK, ignore_result=True)
def expire_invitations(self: Any) -> int:
    """Enqueue one ``expire_invitation`` per due ``pending`` invitation; how many."""
    due = Invitation.objects.unscoped(UnscopedReason.SYSTEM_FANOUT).filter(
        status=InvitationStatus.PENDING.value, expires_at__lte=timezone.now()
    )
    count = 0
    for organization_id, invitation_id in due.values_list("organization_id", "id"):
        self.fan_out(expire_invitation, organization_id, invitation_id=str(invitation_id))
        count += 1
    logger.info(FANOUT_EVENT, enqueued=count)
    return count


def queue_invitation_email(ctx: TenantContext, invitation_id: uuid.UUID, accept_url: str) -> bool:
    """Enqueue the email of a just created or resent invitation, after the commit, if the flag
    is on; ``False`` (and nothing enqueued, nothing registered) if it is off."""
    if not is_enabled(EMAIL_FLAG):
        return False
    kwargs = {
        ORGANIZATION_KWARG: str(ctx.organization_id),
        "invitation_id": str(invitation_id),
        LINK_KWARG: accept_url,
    }
    # ``kwargsrepr`` is a message option the stubs of ``apply_async`` do not list.
    options: dict[str, Any] = {
        "kwargsrepr": repr({**kwargs, LINK_KWARG: REDACTED}),
        "expires": EMAIL_EXPIRES_SECONDS,
    }
    transaction.on_commit(lambda: send_invitation_email.apply_async(kwargs=kwargs, **options))
    return True


@shared_task(base=TenantTask, name=EMAIL_TASK, ignore_result=True)
def send_invitation_email(*, organization_id: str, invitation_id: str, accept_url: str) -> bool:
    """Send the link to the invitee if the flag is on and the invitation still works."""
    if not is_enabled(EMAIL_FLAG):  # turned off after it was enqueued
        logger.info(EMAIL_SKIPPED_EVENT, invitation_id=invitation_id, reason="flag_off")
        return False
    ctx = require_current_tenant()
    invitation = get_invitation(ctx, uuid.UUID(invitation_id))
    if (
        invitation is None
        or invitation.status != InvitationStatus.PENDING
        or is_expired(invitation.expires_at, timezone.now())
    ):
        logger.info(EMAIL_SKIPPED_EVENT, invitation_id=invitation_id, reason="not_pending")
        return False
    organization = get_organization(ctx).name
    expires = invitation.expires_at.astimezone(UTC).strftime("%d/%m/%Y %H:%M")
    send_mail(
        SUBJECT.format(organization=organization),
        BODY.format(organization=organization, link=accept_url, expires=expires),
        None,  # DEFAULT_FROM_EMAIL, until the provider's ADR (Q-207)
        [invitation.email],
    )
    logger.info(EMAIL_SENT_EVENT, invitation_id=invitation_id)
    return True
