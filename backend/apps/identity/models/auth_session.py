"""A login of a person on one device (design.md §5): global, without ``organization_id`` (spec §9).

Its deadlines live in the row and the database guards them: the absolute one is fixed at the login
(``created_at + 30 days``) and the idle one can never pass it (AC-IDA-16, RN-IDA-11). ``active`` is
the only non-terminal status; the moves out of it are conditional updates in
``services/session_lifecycle.py``, so a terminal session never returns. Of the device only the
summarized browser and OS are kept, never the IP or the raw User-Agent (RNF-IDA-05).
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Cast

from apps.identity.domain.session_policy import ABSOLUTE_LIFETIME
from apps.identity.models.user import User

CLIENT_HINT_LENGTH = 32

# ``ABSOLUTE_LIFETIME`` in hours: ``timestamptz + '30 days'`` depends on the connection's time zone
# (a day across a DST change is 23 or 25 hours); hours do not, so the check means the same for
# every client of the database.
ABSOLUTE_LIFETIME_SQL = Cast(
    Value(f"{int(ABSOLUTE_LIFETIME.total_seconds()) // 3600} hours"),
    output_field=models.DurationField(),
)


class SessionStatus(models.TextChoices):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RevokeReason(models.TextChoices):
    """``logout`` plus the reasons of ``SessionRevocationReason`` (audit catalog, design.md §5)."""

    LOGOUT = "logout"
    USER_REVOKED = "user_revoked"
    REVOKED_OTHERS = "revoked_others"
    USER_DEACTIVATED = "user_deactivated"
    REFRESH_REUSE = "refresh_reuse"
    SUPERSEDED = "superseded"


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Only the partial index of active sessions (design.md §5): the full one would serve nothing.
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="auth_sessions", db_index=False
    )
    status = models.CharField(
        max_length=16, choices=SessionStatus.choices, default=SessionStatus.ACTIVE
    )
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField()
    idle_expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    # NULL, not '': "revoked iff a reason" (design.md §5), and '' would count as a reason.
    revoke_reason = models.CharField(  # noqa: DJ001
        max_length=32, choices=RevokeReason.choices, null=True, blank=True
    )
    client_browser = models.CharField(max_length=CLIENT_HINT_LENGTH, blank=True, default="")
    client_os = models.CharField(max_length=CLIENT_HINT_LENGTH, blank=True, default="")

    class Meta:
        db_table = "auth_sessions"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(status__in=SessionStatus.values),
                name="auth_sessions_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(revoke_reason__isnull=True) | Q(revoke_reason__in=RevokeReason.values),
                name="auth_sessions_revoke_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(absolute_expires_at=F("created_at") + ABSOLUTE_LIFETIME_SQL),
                name="auth_sessions_absolute_is_30_days",
            ),
            models.CheckConstraint(
                condition=Q(idle_expires_at__lte=F("absolute_expires_at")),
                name="auth_sessions_idle_within_absolute",
            ),
            models.CheckConstraint(
                condition=Q(status=SessionStatus.ACTIVE, ended_at__isnull=True)
                | (~Q(status=SessionStatus.ACTIVE) & Q(ended_at__isnull=False)),
                name="auth_sessions_active_iff_not_ended",
            ),
            models.CheckConstraint(
                condition=Q(status=SessionStatus.REVOKED, revoke_reason__isnull=False)
                | (~Q(status=SessionStatus.REVOKED) & Q(revoke_reason__isnull=True)),
                name="auth_sessions_revoked_iff_reason",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["user"],
                condition=Q(status=SessionStatus.ACTIVE),
                name="auth_sessions_active_user_idx",
            ),
            models.Index(
                fields=["idle_expires_at"],
                condition=Q(status=SessionStatus.ACTIVE),
                name="auth_sessions_active_idle_idx",
            ),
            models.Index(
                fields=["ended_at"],
                condition=Q(ended_at__isnull=False),
                name="auth_sessions_ended_at_idx",
            ),
        ]

    def __str__(self) -> str:
        return str(self.pk)
