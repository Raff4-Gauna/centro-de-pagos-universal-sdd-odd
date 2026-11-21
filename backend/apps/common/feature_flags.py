"""Feature flags by environment variable (RF-PLT-19, Q-052, C-17; design.md §3.2.8).

A flag exists only if it is in ``REGISTRY``: ``NAME -> what it gates and when it goes away``. Its
variable is ``FEATURE_<NAME>`` (``true``/``false``, off when unset), read once at start-up by
``config/settings/env.py`` (``load_feature_flags``) into ``settings.FEATURE_FLAGS``; an unregistered
``FEATURE_*`` variable does not start. ``is_enabled`` raises ``KeyError`` for a name that is not
registered, so a typo in code fails loudly instead of reading "off". Flags per organization come
with module 02.
"""

from __future__ import annotations

from collections.abc import Mapping

from django.conf import settings

REGISTRY: dict[str, str] = {
    "IDENTITY_GOOGLE_LOGIN": (
        "Gates login/start and login/complete (503 login_disabled); refresh, logout and open "
        "sessions go on. Goes away once login with Google is verified in production (ADR-0004 §14)."
    ),
    "TENANCY_INVITATION_EMAIL_ENABLED": (
        "Gates the invitation email (apps/tenancy/tasks.py, send_invitation_email): off, creating "
        "or resending an invitation enqueues nothing and the link is only shown once. Stays off "
        "until the ADR of the email provider (Q-207, C-13); dev prints the email to the console. "
        "Goes away once that provider sends in production."
    ),
}


def is_enabled(name: str) -> bool:
    """Whether the registered flag ``name`` is on; ``KeyError`` if it is not registered."""
    if name not in REGISTRY:
        raise KeyError(name)
    flags: Mapping[str, bool] = getattr(settings, "FEATURE_FLAGS", {})
    return flags.get(name, False) is True
