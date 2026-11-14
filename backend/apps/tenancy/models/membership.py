"""A person in an organization, with one role (RN-TEN-07, RN-TEN-21, design.md §5, ADR-0002).

A ``TenantModel``: its manager fails closed and ``save()`` writes only in the active organization
(AC-TEN-07, AC-TEN-11). The invariants are constraints, the final net even if a service fails:

- ``membership_one_active_per_org_user``: at most one ``active`` per (organization, user); the
  ``revoked`` ones are kept as history and never block a new one (RN-TEN-07, RN-TEN-21);
- ``membership_role_valid`` and ``membership_status_valid``: the closed enums, as ``varchar``;
- ``membership_end_coherent``: an ``active`` one has no end; a ``revoked`` one says why
  (``revoked`` by someone or ``left``) and when. ``revoked`` is terminal: re-inviting creates a new
  membership (Q-203, Q-214), so no constraint and no code reactivates one. The ``revoked`` branch
  also says ``ended_reason IS NOT NULL``: design.md §5 writes only ``ended_reason IN (...)``, which
  is NULL for a NULL reason, and a CHECK that is NULL passes.

``membership_active_user_org`` is the partial index the request resolution reads in one query, and
"my organizations" with it (``INCLUDE (role)``, RNF-TEN-07). Every FK is ``PROTECT`` without
reverse accessor: a membership is never deleted (``NoHardDeleteMixin``), nor is the user it names.
``source_invitation`` arrives with ``Invitation`` (T-TEN-14).
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.authz.roles import Role
from apps.common.tenancy.models import NoHardDeleteMixin, TenantModel


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class EndedReason(StrEnum):
    """Why a membership ended: told apart in the audit trail (RN-TEN-21)."""

    REVOKED = "revoked"
    LEFT = "left"


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class Membership(NoHardDeleteMixin, TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default=MembershipStatus.ACTIVE.value)
    # NULL while active, as design.md §5 and ``membership_end_coherent`` (``IS NULL``) say.
    ended_reason = models.CharField(max_length=16, null=True, blank=True)  # noqa: DJ001
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                condition=Q(status=MembershipStatus.ACTIVE.value),
                name="membership_one_active_per_org_user",
            ),
            models.CheckConstraint(
                condition=Q(role__in=_values(Role)), name="membership_role_valid"
            ),
            models.CheckConstraint(
                condition=Q(status__in=_values(MembershipStatus)), name="membership_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(
                    status=MembershipStatus.ACTIVE.value,
                    ended_reason__isnull=True,
                    ended_at__isnull=True,
                )
                | Q(
                    status=MembershipStatus.REVOKED.value,
                    # ``NULL IN (...)`` is NULL, and a CHECK lets NULL through: say it.
                    ended_reason__isnull=False,
                    ended_reason__in=_values(EndedReason),
                    ended_at__isnull=False,
                ),
                name="membership_end_coherent",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["user", "organization"],
                include=["role"],
                condition=Q(status=MembershipStatus.ACTIVE.value),
                name="membership_active_user_org",
            ),
        ]

    def __str__(self) -> str:
        """The id: a ``Membership`` in a log carries neither the user nor the organization."""
        return str(self.pk)
