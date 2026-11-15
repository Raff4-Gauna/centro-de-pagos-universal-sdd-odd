"""Who may change, revoke, invite or leave, by role (design.md §3.8, spec §4). Pure: no Django.

The services ask these functions *after* ``ActionPermission`` let the action through and under the
organization lock, with the roles and the count of active owners they just re-read (design.md
§4.2). Each one returns a ``Decision``; the service turns it into the response:

- ``ALLOW``: apply the change; ``NOOP``: ``200`` without change nor event;
- ``FORBIDDEN``: ``403`` (RN-TEN-09, RN-TEN-13, AC-TEN-15, AC-TEN-16);
- ``LAST_OWNER``: ``409 last_owner`` plus ``owner_protection.rejected`` (RN-TEN-14, AC-TEN-13).

The rules, from the matrix of ``spec.sdd.md`` §4 and Q-201, Q-202, Q-203, Q-223:

- Only an ``owner`` invites as ``owner``, assigns or takes away ``owner``, revokes an owner and
  resends or revokes an ``owner`` invitation; an ``admin`` manages ``admin``, ``operator`` and
  ``viewer``, other admins included; an ``operator`` or a ``viewer`` manages nobody.
- Nobody raises their own role. An owner demotes itself unless it is the last one; an admin demotes
  itself to ``operator`` or ``viewer``; an operator or a viewer does not change its own role: it
  leaves. Everybody may leave, except the last owner.
- The authority is checked **before** the no-op: an admin that sets ``owner`` on an owner, or an
  operator that "changes" a role to the same one, gets ``FORBIDDEN``, not ``NOOP`` (AC-TEN-15: "nada
  cambia" *and* ``403``; RN-TEN-09: deny by default).
- A count of active owners that cannot happen (``0`` while an owner acts) never allows taking one
  away: ``<= 1`` is the last owner. A negative count, or ``is_self`` with two different roles, is a
  bug of the caller and raises ``ValueError``.

Roles are accepted as ``Role`` or as the text the database keeps; anything else raises
``ValueError`` (RN-TEN-07).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol

from apps.common.authz.roles import ROLE_RANK, Role


class Decision(StrEnum):
    ALLOW = "allow"
    NOOP = "noop"
    FORBIDDEN = "forbidden"
    LAST_OWNER = "last_owner"


class PendingInvitation(Protocol):
    """What ``invitations_to_auto_revoke`` reads of a pending invitation: only its role."""

    @property
    def role(self) -> str: ...


# What an admin cannot invite, assign, take away, revoke or manage (Q-202).
_ADMIN_OUT_OF_REACH = frozenset({Role.OWNER})
# What an admin may demote itself to (spec §4, "Degradar el propio rol").
_ADMIN_SELF_DEMOTIONS = frozenset({Role.OPERATOR, Role.VIEWER})


def _role(value: Role | str) -> Role:
    return Role(value)


def _check_owners(active_owners: int) -> None:
    if active_owners < 0:
        raise ValueError(f"active_owners cannot be negative: {active_owners}")


def _removes_last_owner(target: Role, new: Role | None, active_owners: int) -> bool:
    """Whether the change leaves the organization without an owner (``new`` None = it leaves)."""
    return target is Role.OWNER and new is not Role.OWNER and active_owners <= 1


def _manages(actor: Role, role: Role) -> bool:
    """Whether ``actor`` may invite, assign, take away or manage ``role`` (RN-TEN-13)."""
    if actor is Role.OWNER:
        return True
    if actor is Role.ADMIN:
        return role not in _ADMIN_OUT_OF_REACH
    return False


def decide_role_change(
    actor_role: Role | str,
    target_role: Role | str,
    new_role: Role | str,
    *,
    is_self: bool,
    active_owners: int,
) -> Decision:
    """Change ``target_role`` to ``new_role``; ``is_self`` when the target is the actor's own."""
    actor, target, new = _role(actor_role), _role(target_role), _role(new_role)
    _check_owners(active_owners)
    if is_self:
        return _decide_own_change(actor, target, new, active_owners)
    if not (_manages(actor, target) and _manages(actor, new)):
        return Decision.FORBIDDEN
    if new is target:
        return Decision.NOOP
    if _removes_last_owner(target, new, active_owners):
        return Decision.LAST_OWNER
    return Decision.ALLOW


def _decide_own_change(actor: Role, target: Role, new: Role, active_owners: int) -> Decision:
    if actor is not target:
        raise ValueError("is_self needs one role: the actor's own membership is the target")
    if ROLE_RANK[new] > ROLE_RANK[actor]:
        return Decision.FORBIDDEN  # nobody raises their own role (AC-TEN-16)
    if actor is Role.ADMIN:
        if new is Role.ADMIN:
            return Decision.NOOP
        return Decision.ALLOW if new in _ADMIN_SELF_DEMOTIONS else Decision.FORBIDDEN
    if actor is not Role.OWNER:
        return Decision.FORBIDDEN  # an operator or a viewer leaves instead (Q-203)
    if new is Role.OWNER:
        return Decision.NOOP
    if _removes_last_owner(actor, new, active_owners):
        return Decision.LAST_OWNER
    return Decision.ALLOW


def decide_revoke(
    actor_role: Role | str, target_role: Role | str, *, active_owners: int
) -> Decision:
    """Revoke someone else's membership. Revoking one's own is leaving (design.md §4.2, step 5)."""
    actor, target = _role(actor_role), _role(target_role)
    _check_owners(active_owners)
    if not _manages(actor, target):
        return Decision.FORBIDDEN
    if _removes_last_owner(target, None, active_owners):
        return Decision.LAST_OWNER
    return Decision.ALLOW


def decide_leave(role: Role | str, *, active_owners: int) -> Decision:
    """Leave the organization: anyone but the last owner (Q-201, Q-203)."""
    member = _role(role)
    _check_owners(active_owners)
    if _removes_last_owner(member, None, active_owners):
        return Decision.LAST_OWNER
    return Decision.ALLOW


def decide_invite(actor_role: Role | str, invite_role: Role | str) -> Decision:
    """Invite with ``invite_role``: an owner any role, an admin any but owner (RN-TEN-13)."""
    return Decision.ALLOW if _manages(_role(actor_role), _role(invite_role)) else Decision.FORBIDDEN


def decide_manage_invitation(actor_role: Role | str, invitation_role: Role | str) -> Decision:
    """Resend or revoke a pending invitation of ``invitation_role``: as inviting with it (Q-202)."""
    return decide_invite(actor_role, invitation_role)


def invitations_to_auto_revoke[InvitationT: PendingInvitation](
    new_role_or_none: Role | str | None, pending_by_inviter: Iterable[InvitationT]
) -> tuple[InvitationT, ...]:
    """The pending invitations of an inviter that its new role no longer lets it issue (Q-223).

    ``new_role_or_none`` is the inviter's role after the change, or ``None`` when it was revoked or
    left: then none of its invitations stays. ``pending_by_inviter`` holds only the ``pending``
    invitations that person issued; the ones the platform operator issued are never passed here.
    The order is kept.
    """
    if new_role_or_none is None:
        return tuple(pending_by_inviter)
    new_role = _role(new_role_or_none)
    return tuple(
        invitation
        for invitation in pending_by_inviter
        if decide_invite(new_role, invitation.role) is Decision.FORBIDDEN
    )
