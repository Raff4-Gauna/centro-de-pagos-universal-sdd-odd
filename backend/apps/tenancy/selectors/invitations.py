"""Find the invitation of a token (design.md §3.4, §4.4; RNF-TEN-03).

``find_by_token(token)`` is the first step of accepting by token: it hashes the token and reads the
one row with that hash through ``Invitation.objects.by_token_hash``, with no transaction and no
lock, as the diagram of §4.4 does. Only the hash reaches the database; the token is neither kept
nor logged. It gives the id and the organization of the row, which is where the service opens its
``tenant_scope``; everything else is read again under that scope and under the lock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.tenancy.domain.invitations import hash_token
from apps.tenancy.models import Invitation


@dataclass(frozen=True, slots=True)
class InvitationRef:
    """Which invitation and in which organization: nothing of the invitee, nothing secret."""

    invitation_id: uuid.UUID
    organization_id: uuid.UUID


def find_by_token(token: str) -> InvitationRef | None:
    row = (
        Invitation.objects.by_token_hash(hash_token(token))
        .values_list("id", "organization_id")
        .first()
    )
    return None if row is None else InvitationRef(*row)
