"""What the callback accepts from Google's verified claims (design.md §4.2, steps 5-6). Pure.

``evaluate_identity`` receives the claims the ID token verification already checked (signature,
``iss``, ``aud``, ``exp``, ``nonce``) as plain values, and returns what the Hub keeps of them:

- An unusable ``sub`` or email rejects the login as ``google_auth_failed``: the token is not one the
  Hub can use. The email is normalized as RN-IDA-05 says (``normalize_email``, Q-107) and is then
  refused if empty, too long or carrying any whitespace, control, format or unpaired surrogate code
  point. The ``users`` CHECK only trims ASCII spaces (reviewer of #65), so a tab, a NBSP or a
  U+3000 inside the address would otherwise be stored as part of it.
- ``email_verified`` is accepted only as ``True`` or ``"true"`` (RN-IDA-03); anything else is
  ``email_not_verified``. The token step comes first, as in the table.
- A name or avatar never rejects a login (``domain/profile.py``): the NUL and the unpaired
  surrogates PostgreSQL cannot store are dropped from the name before ``clamp_display_name``, and an
  avatar carrying either is unusable, so ``clean_avatar_url`` gets nothing.

A rejection carries its code and, when the person is a known user, that user's id (the actor of its
audit event, design.md §7.4); never the email nor the ``sub`` (Q-125, RNF-IDA-05).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from uuid import UUID

from apps.identity.domain.emails import normalize_email
from apps.identity.domain.errors import IdentityError, IdentityErrorCode
from apps.identity.domain.profile import clamp_display_name, clean_avatar_url

MAX_EMAIL = 254
MAX_SUB = 255
_UNSTORABLE = ("\x00",)


class LoginRejectedError(IdentityError):
    """The callback refuses the login with ``code``; ``user_id`` only for a known user."""

    def __init__(self, code: IdentityErrorCode, *, user_id: UUID | None = None) -> None:
        super().__init__(code)
        self.user_id = user_id


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """The person as the Hub will store it. ``repr`` hides the ``sub`` and the email."""

    sub: str = field(repr=False)
    email: str = field(repr=False)
    display_name: str = field(repr=False)
    avatar_url: str = field(repr=False)


def evaluate_identity(
    *, sub: str, email: str, email_verified: object, name: str, picture: str
) -> VerifiedIdentity:
    normalized = normalize_email(email) if isinstance(email, str) else ""
    if not _is_usable_sub(sub) or not _is_usable_email(normalized):
        raise LoginRejectedError(IdentityErrorCode.GOOGLE_AUTH_FAILED)
    if not _is_verified(email_verified):
        raise LoginRejectedError(IdentityErrorCode.EMAIL_NOT_VERIFIED)
    return VerifiedIdentity(
        sub=sub,
        email=normalized,
        display_name=clamp_display_name(_storable(name)),
        avatar_url=clean_avatar_url(picture if _is_storable(picture) else ""),
    )


def _is_verified(value: object) -> bool:
    """Exactly ``True`` or ``"true"``: ``1 == True`` in Python, and ``1`` is not Google's answer."""
    return value is True or (isinstance(value, str) and value == "true")


def _is_usable_sub(sub: object) -> bool:
    return isinstance(sub, str) and 0 < len(sub) <= MAX_SUB and not any(map(_is_invisible, sub))


def _is_usable_email(email: str) -> bool:
    return 0 < len(email) <= MAX_EMAIL and not any(map(_is_invisible, email))


def _is_invisible(char: str) -> bool:
    """Whitespace, or a control, format, surrogate, private-use or unassigned code point."""
    return char.isspace() or unicodedata.category(char).startswith("C")


def _is_storable(value: object) -> bool:
    return isinstance(value, str) and not any(map(_is_unstorable, value))


def _is_unstorable(char: str) -> bool:
    return char in _UNSTORABLE or unicodedata.category(char) == "Cs"


def _storable(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value if not _is_unstorable(char))
