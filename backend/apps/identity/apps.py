"""Who the person is and how their session lives (SPEC-01): ``users`` and, later, its sessions."""

from __future__ import annotations

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class IdentityConfig(AppConfig):
    name = "apps.identity"
    label = "identity"

    def ready(self) -> None:
        """Registers the system checks; refuses the fake OIDC provider outside dev and test.

        Raised here, not as a system check: gunicorn and Celery never run checks, and a process
        with the fake provider in prod or staging must not even start (Q-122, RNF-IDA-06).
        """
        from apps.identity import checks  # noqa: F401 - registers on import
        from apps.identity.oidc import provider

        if settings.IDENTITY_OIDC_PROVIDER == provider.FAKE and not provider.fake_oidc_allowed():
            raise ImproperlyConfigured(provider.FAKE_NOT_ALLOWED)
