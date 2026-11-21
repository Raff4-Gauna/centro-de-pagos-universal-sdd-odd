"""System checks of tenancy (RF-TEN-05, Q-207, C-13, design.md §7, §10).

They run with ``manage.py check`` and before every ``migrate`` (the container command of dev, CI
and prod), and an ``Error`` stops it. Every message names settings, never a value (C-06).

* ``tenancy.E001``: the invitation email is on (``FEATURE_TENANCY_INVITATION_EMAIL_ENABLED``) and
  ``EMAIL_BACKEND`` is still Django's default, the SMTP of ``localhost:25``. No provider is chosen
  yet (Q-207, its ADR comes first, C-13): the worker would hand the invitation link to whatever
  answers on that port. Dev sets the console backend and the tests the in-memory one, so it only
  stops an environment that turned the flag on without a provider. Off, it says nothing: prod
  starts as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from django.apps import AppConfig
from django.conf import global_settings, settings
from django.core.checks import CheckMessage, Error, Tags, register

from apps.common import feature_flags

EMAIL_WITHOUT_PROVIDER: Final = "tenancy.E001"
EMAIL_FLAG: Final = "TENANCY_INVITATION_EMAIL_ENABLED"


@register(Tags.security)
def invitation_email_has_a_backend(
    app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    if not feature_flags.is_enabled(EMAIL_FLAG):
        return []
    if settings.EMAIL_BACKEND != global_settings.EMAIL_BACKEND:
        return []
    return [
        Error(
            "FEATURE_TENANCY_INVITATION_EMAIL_ENABLED is on and EMAIL_BACKEND is Django's default",
            hint="Leave the flag off until the email provider's ADR configures it (Q-207, C-13).",
            id=EMAIL_WITHOUT_PROVIDER,
        )
    ]
