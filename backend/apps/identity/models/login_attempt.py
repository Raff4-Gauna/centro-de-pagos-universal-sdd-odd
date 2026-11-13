"""A login in progress, between "start" and Google's callback (design.md §5, ADR-0004 §2).

Global, without ``organization_id`` (spec §9), single use and short-lived: the callback deletes the
row (``DELETE ... RETURNING``, T-IDA-13) and the purge deletes the expired ones (T-IDA-19).
``state``, ``nonce`` and the browser's binding are kept as SHA-256 only, and the database refuses
anything that is not one; the PKCE ``code_verifier`` is the one value in clear, because Google needs
it back, and it lives ten minutes at most.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Cast

from apps.identity.domain.return_path import MAX_RETURN_PATH_LENGTH

LOGIN_ATTEMPT_LIFETIME = timedelta(minutes=10)
HASH_LENGTH = 64
CODE_VERIFIER_LENGTH = 128
_SHA256_HEX = "^[0-9a-f]{64}$"

# Minutes, not a day-based interval: the check means the same whatever the connection's time zone.
LOGIN_ATTEMPT_LIFETIME_SQL = Cast(
    Value(f"{int(LOGIN_ATTEMPT_LIFETIME.total_seconds()) // 60} minutes"),
    output_field=models.DurationField(),
)


class LoginAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    state_hash = models.CharField(max_length=HASH_LENGTH, unique=True)
    nonce_hash = models.CharField(max_length=HASH_LENGTH)
    binding_hash = models.CharField(max_length=HASH_LENGTH)
    code_verifier = models.CharField(max_length=CODE_VERIFIER_LENGTH)
    return_path = models.CharField(max_length=MAX_RETURN_PATH_LENGTH)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "login_attempts"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(expires_at=F("created_at") + LOGIN_ATTEMPT_LIFETIME_SQL),
                name="login_attempts_expires_in_10_minutes",
            ),
            models.CheckConstraint(
                condition=Q(state_hash__regex=_SHA256_HEX)
                & Q(nonce_hash__regex=_SHA256_HEX)
                & Q(binding_hash__regex=_SHA256_HEX),
                name="login_attempts_hashes_are_sha256_hex",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["expires_at"], name="login_attempts_expires_at_idx"),
        ]

    def __str__(self) -> str:
        return str(self.pk)
