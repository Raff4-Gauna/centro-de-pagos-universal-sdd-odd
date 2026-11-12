"""The opaque refresh tokens of a session (design.md §5, RN-IDA-10): only their SHA-256 is stored.

``token_hash`` must look like a SHA-256 hex digest, so not even a bug can put a token in clear in
the table (AC-IDA-14). A session has at most one live (unused) token, and a token is replaced only
after being used. ``replaced_by`` is what tells a concurrent tab from a replay (ADR-0004 §3).
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.db.models import Q

from apps.identity.models.auth_session import AuthSession

TOKEN_HASH_LENGTH = 64
SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"


class RefreshToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(
        AuthSession, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    token_hash = models.CharField(max_length=TOKEN_HASH_LENGTH, unique=True)
    issued_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.OneToOneField(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replaces"
    )

    class Meta:
        db_table = "refresh_tokens"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["session"],
                condition=Q(used_at__isnull=True),
                name="refresh_tokens_one_live_per_session",
            ),
            models.CheckConstraint(
                condition=Q(replaced_by__isnull=True) | Q(used_at__isnull=False),
                name="refresh_tokens_replaced_only_if_used",
            ),
            models.CheckConstraint(
                condition=Q(token_hash__regex=SHA256_HEX_PATTERN),
                name="refresh_tokens_hash_is_sha256_hex",
            ),
        ]

    def __str__(self) -> str:
        """The id: never the hash, which identifies the token in a log (RNF-IDA-03)."""
        return str(self.pk)
