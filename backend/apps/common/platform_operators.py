"""Who runs a platform operator's command (Q-212, SPEC-02 design.md §4.5, SPEC-01 design.md §6.5).

Every operator command (``tenancy_create_org`` of ``apps.tenancy``; ``deactivate_user`` and
``reactivate_user`` of ``apps.identity``) takes ``--operator`` and checks it here, so they all
behave the same way. It lives in ``common`` because ``apps.identity`` does not import
``apps.tenancy``.

``allowed_operator(value)`` normalizes the address (both ends trimmed, lower case) and accepts it
only if ``settings.PLATFORM_OPERATOR_EMAILS`` lists it; with the setting empty or missing nobody is
accepted (fail closed). The refusal never repeats the value. ``os_user()`` is the user of the
operating system, which every audit event names next to the operator: ``--operator`` is declared,
having a shell on the server is what grants access (design.md §11 of SPEC-02).
"""

from __future__ import annotations

import getpass

from django.conf import settings

UNKNOWN_OS_USER = "unknown"


class OperatorNotAllowedError(ValueError):
    """``--operator`` is not in ``PLATFORM_OPERATOR_EMAILS``; it carries no value."""

    def __init__(self) -> None:
        super().__init__("the operator is not in PLATFORM_OPERATOR_EMAILS")


def allowed_operators() -> frozenset[str]:
    configured = getattr(settings, "PLATFORM_OPERATOR_EMAILS", ())
    return frozenset(str(email).strip().lower() for email in configured)


def allowed_operator(value: object) -> str:
    """The normalized operator email, if the allowlist has it; else ``OperatorNotAllowedError``."""
    email = value.strip().lower() if isinstance(value, str) else ""
    if not email or email not in allowed_operators():
        raise OperatorNotAllowedError
    return email


def os_user() -> str:
    """The user of the operating system running the command, or ``unknown`` if it has none."""
    try:
        return getpass.getuser() or UNKNOWN_OS_USER
    except (OSError, KeyError):  # no USER/LOGNAME and no passwd entry (a bare container)
        return UNKNOWN_OS_USER
