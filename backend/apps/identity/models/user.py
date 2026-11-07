"""The person (design.md §5): global, without ``organization_id`` (the link is the membership).

``AbstractBaseUser`` comes from ``base_user``, the one module of ``django.contrib.auth`` usable
without installing it (D-03). Google is the only way in (Q-101), so the inherited ``password``
column is never usable: its default says so for every way of creating a row and ``set_password``
refuses, instead of relying on each caller to remember ``set_unusable_password``.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.hashers import make_password
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Trim

from apps.identity.domain.emails import normalize_email
from apps.identity.domain.profile import (
    MAX_AVATAR_URL,
    MAX_DISPLAY_NAME,
    clamp_display_name,
    clean_avatar_url,
)


def unusable_password() -> str:
    return make_password(None)


class UserManager(models.Manager["User"]):
    """Without ``create_superuser``: no one is created outside the invitation gate (RN-IDA-05)."""

    def create_user(
        self,
        *,
        google_sub: str,
        email: str,
        display_name: str | None = "",
        avatar_url: str | None = "",
    ) -> User:
        return self.create(
            google_sub=google_sub,
            email=normalize_email(email),
            display_name=clamp_display_name(display_name),
            avatar_url=clean_avatar_url(avatar_url),
        )


class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    google_sub = models.CharField(max_length=255, unique=True)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=MAX_DISPLAY_NAME, blank=True, default="")
    avatar_url = models.URLField(max_length=MAX_AVATAR_URL, blank=True, default="")
    password = models.CharField(max_length=128, default=unusable_password, editable=False)
    is_active = models.BooleanField(default=True)
    # Replaced by last_login_at: Django's update_last_login never runs here (D-03).
    last_login = None
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "google_sub"
    EMAIL_FIELD = "email"

    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        db_table = "users"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(email=Lower(Trim("email"))),
                name="users_email_normalized",
            ),
            models.CheckConstraint(
                condition=Q(is_active=True, deactivated_at__isnull=True)
                | Q(is_active=False, deactivated_at__isnull=False),
                name="users_active_matches_deactivated_at",
            ),
        ]

    def __str__(self) -> str:
        """The id: a ``User`` in a log must carry neither the ``sub`` nor the email (RNF-IDA-05)."""
        return str(self.pk)

    def set_password(self, raw_password: str | None) -> None:
        raise NotImplementedError("Users have no password: Google is the only way in (Q-101)")
