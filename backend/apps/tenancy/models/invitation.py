"""An invitation to join an organization with one role (RN-TEN-11, RN-TEN-12, design.md §5).

A ``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). The rules live in ``domain/invitations.py``; the constraints below are the
final net even if a service fails (ADR-0002 §2):

- ``invitation_one_pending_per_org_email``: at most one ``pending`` per (organization, email); the
  ``accepted``, ``revoked`` and ``expired`` ones stay as history (RN-TEN-12, AC-TEN-26);
- ``token_hash`` is unique and ``invitation_token_hash_sha256`` keeps it 64 lowercase hex: only the
  SHA-256 of the token is stored, never the token, so a raw token cannot land in this column
  (RNF-TEN-03). The column is ``varchar(64)``: with the CHECK it holds exactly what ``char(64)`` of
  design.md §5 would, without the padding of ``char``;
- ``invitation_email_normalized``: the email is stored as ``normalize_email`` leaves it (the CHECK
  says ``lower(btrim(email))``), and it is the only data of the invitee (RNF-TEN-06);
- the closed enums (status, role, purpose and ``revoked_reason``) as ``varchar`` + ``CHECK``;
- ``invitation_inviter_xor``: issued by exactly one of a user or the platform operator;
- ``invitation_operator_reason``: ``support`` and ``owner_recovery`` ones carry a reason (Q-225);
- ``invitation_accepted_coherent``: ``accepted`` if and only if it names who accepted it and when;
- ``invitation_expiry_after_creation``: ``expires_at > created_at``.

``invitation_org_status_created`` serves the listing of one organization and
``invitation_pending_email`` the pending ones of an email (port of SPEC-01, T-TEN-16/17). Every FK
is ``PROTECT`` without reverse accessor: an invitation is never deleted (``NoHardDeleteMixin``).
``replaces`` points a resent invitation at the one it revoked.

``Invitation.objects.by_token_hash(token_hash)`` is the scope of accepting by token (design.md
§3.4, §4.4): the one row with that hash, whatever its organization, read only
(``scopes.ModelScope``; ``allowlists.MODEL_SCOPES``). It takes the hash, never the token, and
refuses anything that is not 64 lowercase hex. ``pending_for_email(email)`` is the ``pending`` ones
of one email, normalized here, whatever their organization ("my invitations" and the port of
SPEC-01; the reader adds the expiry and the organization's status). ``for_session_accept(id)`` is
one row by id, whatever its organization (accepting from the session, §4.4): the service decides by
the email before it answers anything, and the architecture test allows it in that one file only
(``allowlists.RESTRICTED_SCOPE_ALLOWLIST``). All three are reads: a write under them fails closed.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim

from apps.common.authz.roles import Role
from apps.common.tenancy.models import NoHardDeleteMixin, TenantModel
from apps.common.tenancy.querysets import TenantQuerySet
from apps.tenancy.domain.invitations import (
    OPERATOR_PURPOSES,
    TOKEN_HASH_LENGTH,
    InvitationPurpose,
    InvitationStatus,
    RevokedReason,
    normalize_email,
)

EMAIL_MAX_LENGTH = 254


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


_TOKEN_HASH = re.compile(rf"[0-9a-f]{{{TOKEN_HASH_LENGTH}}}")


class InvitationQuerySet(TenantQuerySet["Invitation"]):
    def by_token_hash(self, token_hash: str) -> InvitationQuerySet:
        if not isinstance(token_hash, str) or not _TOKEN_HASH.fullmatch(token_hash):
            raise ValueError("by_token_hash needs the SHA-256 of a token, in hex")
        return self._model_scope("by_token_hash", token_hash, token_hash=token_hash)

    def pending_for_email(self, email: str) -> InvitationQuerySet:
        if not isinstance(email, str) or not (normalized := normalize_email(email)):
            raise ValueError("pending_for_email needs an email")
        pending = InvitationStatus.PENDING.value
        return self._model_scope("pending_for_email", normalized, email=normalized, status=pending)

    def for_session_accept(self, invitation_id: uuid.UUID) -> InvitationQuerySet:
        if not isinstance(invitation_id, uuid.UUID):
            raise TypeError("for_session_accept needs the invitation's UUID")
        return self._model_scope("for_session_accept", invitation_id, pk=invitation_id)


InvitationManager = models.Manager.from_queryset(InvitationQuerySet)


class Invitation(NoHardDeleteMixin, TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.CharField(max_length=EMAIL_MAX_LENGTH)
    role = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default=InvitationStatus.PENDING.value)
    purpose = models.CharField(max_length=16, default=InvitationPurpose.STANDARD.value)
    reason = models.CharField(max_length=200, blank=True, default="")
    token_hash = models.CharField(max_length=TOKEN_HASH_LENGTH, unique=True)
    expires_at = models.DateTimeField()
    invited_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    invited_by_operator = models.CharField(max_length=EMAIL_MAX_LENGTH, blank=True, default="")
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # NULL unless revoked, as design.md §5 says.
    revoked_reason = models.CharField(max_length=32, null=True, blank=True)  # noqa: DJ001
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    replaces = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[InvitationManager] = InvitationManager()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=Q(status=InvitationStatus.PENDING.value),
                name="invitation_one_pending_per_org_email",
            ),
            models.CheckConstraint(
                condition=Q(token_hash__regex=rf"^[0-9a-f]{{{TOKEN_HASH_LENGTH}}}$"),
                name="invitation_token_hash_sha256",
            ),
            models.CheckConstraint(
                condition=Q(email=Lower(Trim("email"))), name="invitation_email_normalized"
            ),
            models.CheckConstraint(
                condition=Q(status__in=_values(InvitationStatus)), name="invitation_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(role__in=_values(Role)), name="invitation_role_valid"
            ),
            models.CheckConstraint(
                condition=Q(purpose__in=_values(InvitationPurpose)),
                name="invitation_purpose_valid",
            ),
            models.CheckConstraint(
                condition=Q(revoked_reason__isnull=True)
                | Q(revoked_reason__in=_values(RevokedReason)),
                name="invitation_revoked_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(invited_by_user__isnull=False, invited_by_operator="")
                | (Q(invited_by_user__isnull=True) & ~Q(invited_by_operator="")),
                name="invitation_inviter_xor",
            ),
            models.CheckConstraint(
                condition=~Q(purpose__in=sorted(p.value for p in OPERATOR_PURPOSES))
                | ~Q(reason=""),
                name="invitation_operator_reason",
            ),
            models.CheckConstraint(
                condition=Q(
                    status=InvitationStatus.ACCEPTED.value,
                    accepted_by__isnull=False,
                    accepted_at__isnull=False,
                )
                | (
                    ~Q(status=InvitationStatus.ACCEPTED.value)
                    & Q(accepted_by__isnull=True, accepted_at__isnull=True)
                ),
                name="invitation_accepted_coherent",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="invitation_expiry_after_creation",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["organization", "status", "created_at"],
                name="invitation_org_status_created",
            ),
            models.Index(
                fields=["email"],
                condition=Q(status=InvitationStatus.PENDING.value),
                name="invitation_pending_email",
            ),
        ]

    def __str__(self) -> str:
        """The id: an ``Invitation`` in a log carries neither the email nor the token hash."""
        return str(self.pk)
