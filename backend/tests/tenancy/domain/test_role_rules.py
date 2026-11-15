"""The role rules of SPEC-02 (design.md §3.8, spec §4, RN-TEN-13, RN-TEN-14, Q-201..Q-203, Q-223).

Pure: no database. The expected decisions are a literal transcription of the matrix of
``spec.sdd.md`` 1.0.2 §4, written as one grid per row of the table: the columns of a grid are the
new role (or the invited role) in the order ``owner, admin, operator, viewer``, and each letter is
a ``Decision``: ``A`` allow, ``N`` no-op, ``F`` forbidden, ``L`` last owner. A change in the spec
has to change these grids (C-12). ``decide_role_change`` is swept over the whole table
``Role x Role x Role x is_self x owners in {1, 2}``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import pytest

from apps.common.authz.roles import ROLE_RANK, Role
from apps.tenancy.domain.role_rules import (
    Decision,
    decide_invite,
    decide_leave,
    decide_manage_invitation,
    decide_revoke,
    decide_role_change,
    invitations_to_auto_revoke,
)

ORDER = (Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.VIEWER)
LETTER = {
    "A": Decision.ALLOW,
    "N": Decision.NOOP,
    "F": Decision.FORBIDDEN,
    "L": Decision.LAST_OWNER,
}
OWNER_COUNTS = (1, 2)

# Changing someone else's role: actor -> owners -> target -> grid over the new role.
OTHERS: dict[Role, dict[int, dict[Role, str]]] = {
    # An owner manages every role; taking away the last owner is refused (Q-201). With one owner the
    # target owner cannot be someone else: the row is there so the rule holds even on bad input.
    Role.OWNER: {
        1: {Role.OWNER: "NLLL", Role.ADMIN: "ANAA", Role.OPERATOR: "AANA", Role.VIEWER: "AAAN"},
        2: {Role.OWNER: "NAAA", Role.ADMIN: "ANAA", Role.OPERATOR: "AANA", Role.VIEWER: "AAAN"},
    },
    # An admin never assigns nor takes away owner, and never touches an owner, not even to leave it
    # as it is (AC-TEN-15); it manages other admins (Q-202).
    Role.ADMIN: {
        n: {Role.OWNER: "FFFF", Role.ADMIN: "FNAA", Role.OPERATOR: "FANA", Role.VIEWER: "FAAN"}
        for n in OWNER_COUNTS
    },
    # An operator or a viewer changes no role (AC-TEN-16).
    Role.OPERATOR: {n: dict.fromkeys(ORDER, "FFFF") for n in OWNER_COUNTS},
    Role.VIEWER: {n: dict.fromkeys(ORDER, "FFFF") for n in OWNER_COUNTS},
}

# Changing one's own role: role -> owners -> grid over the new role ("Degradar / Elevar el propio
# rol"). Nobody raises their own role; an admin demotes itself only to operator or viewer; an
# operator does not change its own role, it leaves (Q-203); the last owner does not demote itself.
SELF: dict[Role, dict[int, str]] = {
    Role.OWNER: {1: "NLLL", 2: "NAAA"},
    Role.ADMIN: {1: "FNAA", 2: "FNAA"},
    Role.OPERATOR: {1: "FFFF", 2: "FFFF"},
    Role.VIEWER: {1: "FFFF", 2: "FFFF"},
}

# Revoking someone else: actor -> owners -> grid over the target role.
REVOKE: dict[Role, dict[int, str]] = {
    Role.OWNER: {1: "LAAA", 2: "AAAA"},
    Role.ADMIN: {1: "FAAA", 2: "FAAA"},
    Role.OPERATOR: {1: "FFFF", 2: "FFFF"},
    Role.VIEWER: {1: "FFFF", 2: "FFFF"},
}

# Leaving: owners -> grid over the role of who leaves (Q-203).
LEAVE: dict[int, str] = {1: "LAAA", 2: "AAAA"}

# Inviting, and resending or revoking a pending invitation: actor -> grid over its role.
INVITE: dict[Role, str] = {
    Role.OWNER: "AAAA",
    Role.ADMIN: "FAAA",
    Role.OPERATOR: "FFFF",
    Role.VIEWER: "FFFF",
}


def expected(grid: str, column: Role) -> Decision:
    return LETTER[grid[ORDER.index(column)]]


def test_AC_TEN_16_grids_cover_every_role() -> None:
    assert set(OTHERS) == set(SELF) == set(REVOKE) == set(INVITE) == set(Role)
    grids = [*SELF.values(), *REVOKE.values(), LEAVE]
    assert all(len(grid) == len(ORDER) for row in grids for grid in row.values())
    assert all(set(by_target) == set(Role) for row in OTHERS.values() for by_target in row.values())


@pytest.mark.parametrize(
    ("actor", "target", "new", "is_self", "owners"),
    list(itertools.product(Role, Role, Role, (False, True), OWNER_COUNTS)),
)
def test_AC_TEN_16_role_change_full_table(
    actor: Role, target: Role, new: Role, is_self: bool, owners: int
) -> None:
    if is_self and actor is not target:
        # One's own membership has one role: a call that says otherwise is a bug, not a decision.
        with pytest.raises(ValueError, match="own membership"):
            decide_role_change(actor, target, new, is_self=is_self, active_owners=owners)
        return
    grid = SELF[actor][owners] if is_self else OTHERS[actor][owners][target]

    decision = decide_role_change(actor, target, new, is_self=is_self, active_owners=owners)

    assert decision is expected(grid, new)


@pytest.mark.parametrize(("role", "new"), list(itertools.product(Role, Role)))
@pytest.mark.parametrize("owners", OWNER_COUNTS)
def test_AC_TEN_16_no_self_elevation(role: Role, new: Role, owners: int) -> None:
    decision = decide_role_change(role, role, new, is_self=True, active_owners=owners)

    if ROLE_RANK[new] > ROLE_RANK[role]:
        assert decision is Decision.FORBIDDEN


@pytest.mark.parametrize("actor", [Role.OPERATOR, Role.VIEWER])
@pytest.mark.parametrize(("target", "new"), list(itertools.product(Role, Role)))
def test_AC_TEN_16_operator_and_viewer_change_no_role_and_invite_nobody(
    actor: Role, target: Role, new: Role
) -> None:
    assert decide_role_change(actor, target, new, is_self=False, active_owners=2) is (
        Decision.FORBIDDEN
    )
    assert decide_revoke(actor, target, active_owners=2) is Decision.FORBIDDEN
    assert decide_invite(actor, new) is Decision.FORBIDDEN
    assert decide_manage_invitation(actor, new) is Decision.FORBIDDEN


@pytest.mark.parametrize("owners", OWNER_COUNTS)
@pytest.mark.parametrize("other", [Role.ADMIN, Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_15_admin_never_touches_owner(owners: int, other: Role) -> None:
    def change(target: Role, new: Role) -> Decision:
        return decide_role_change(Role.ADMIN, target, new, is_self=False, active_owners=owners)

    assert change(other, Role.OWNER) is Decision.FORBIDDEN  # assign owner
    assert change(Role.OWNER, other) is Decision.FORBIDDEN  # take owner away
    assert change(Role.OWNER, Role.OWNER) is Decision.FORBIDDEN  # not even a no-op
    assert decide_revoke(Role.ADMIN, Role.OWNER, active_owners=owners) is Decision.FORBIDDEN
    assert decide_invite(Role.ADMIN, Role.OWNER) is Decision.FORBIDDEN
    assert decide_manage_invitation(Role.ADMIN, Role.OWNER) is Decision.FORBIDDEN
    # ...and still manages admin, operator and viewer, other admins included (Q-202).
    assert decide_invite(Role.ADMIN, other) is Decision.ALLOW
    assert decide_manage_invitation(Role.ADMIN, other) is Decision.ALLOW
    assert decide_revoke(Role.ADMIN, other, active_owners=owners) is Decision.ALLOW


@pytest.mark.parametrize(("actor", "target"), list(itertools.product(Role, Role)))
@pytest.mark.parametrize("owners", OWNER_COUNTS)
def test_AC_TEN_15_revoke_table(actor: Role, target: Role, owners: int) -> None:
    decision = decide_revoke(actor, target, active_owners=owners)

    assert decision is expected(REVOKE[actor][owners], target)


@pytest.mark.parametrize(("actor", "role"), list(itertools.product(Role, Role)))
def test_AC_TEN_15_invite_and_manage_invitation_table(actor: Role, role: Role) -> None:
    assert decide_invite(actor, role) is expected(INVITE[actor], role)
    assert decide_manage_invitation(actor, role) is expected(INVITE[actor], role)


@pytest.mark.parametrize(("role", "owners"), list(itertools.product(Role, OWNER_COUNTS)))
def test_AC_TEN_13_leave_table(role: Role, owners: int) -> None:
    assert decide_leave(role, active_owners=owners) is expected(LEAVE[owners], role)


@pytest.mark.parametrize("new", [Role.ADMIN, Role.OPERATOR, Role.VIEWER])
def test_AC_TEN_13_last_owner_decision(new: Role) -> None:
    # Demoted, revoked or leaving: the only owner stays (Q-201).
    assert decide_role_change(Role.OWNER, Role.OWNER, new, is_self=True, active_owners=1) is (
        Decision.LAST_OWNER
    )
    assert decide_leave(Role.OWNER, active_owners=1) is Decision.LAST_OWNER
    assert decide_revoke(Role.OWNER, Role.OWNER, active_owners=1) is Decision.LAST_OWNER
    # A count that cannot happen (no owner left) is refused the same way, never allowed.
    assert decide_leave(Role.OWNER, active_owners=0) is Decision.LAST_OWNER


def test_AC_TEN_13_negative_owner_count_is_a_bug() -> None:
    with pytest.raises(ValueError, match="active_owners"):
        decide_leave(Role.OWNER, active_owners=-1)
    with pytest.raises(ValueError, match="active_owners"):
        decide_revoke(Role.OWNER, Role.ADMIN, active_owners=-1)
    with pytest.raises(ValueError, match="active_owners"):
        decide_role_change(Role.OWNER, Role.ADMIN, Role.VIEWER, is_self=False, active_owners=-1)


def test_AC_TEN_27_transfer_decision() -> None:
    # U, the only owner, promotes the admin V to owner...
    promote = decide_role_change(Role.OWNER, Role.ADMIN, Role.OWNER, is_self=False, active_owners=1)
    # ...and then, with two owners, demotes itself to admin: both go through (Q-202).
    demote = decide_role_change(Role.OWNER, Role.OWNER, Role.ADMIN, is_self=True, active_owners=2)

    assert (promote, demote) == (Decision.ALLOW, Decision.ALLOW)
    # Leaving instead of demoting is the other way to finish the transfer.
    assert decide_leave(Role.OWNER, active_owners=2) is Decision.ALLOW
    # Without the promotion first, the demotion is refused.
    refused = decide_role_change(Role.OWNER, Role.OWNER, Role.ADMIN, is_self=True, active_owners=1)
    assert refused is Decision.LAST_OWNER


def test_RN_TEN_07_a_role_outside_the_four_is_refused() -> None:
    with pytest.raises(ValueError, match="superuser"):
        decide_invite("superuser", Role.VIEWER)
    with pytest.raises(ValueError, match="superuser"):
        decide_leave("superuser", active_owners=2)


def test_RN_TEN_07_a_role_read_as_text_decides_like_the_enum() -> None:
    # The database keeps the role as varchar: its text decides exactly as the enum does.
    assert decide_invite("admin", "owner") is Decision.FORBIDDEN
    refused = decide_role_change("owner", "owner", "admin", is_self=True, active_owners=1)
    assert refused is Decision.LAST_OWNER


@dataclass(frozen=True)
class Pending:
    id: int
    role: str


PENDING = (
    Pending(1, Role.OWNER.value),
    Pending(2, Role.ADMIN.value),
    Pending(3, Role.OPERATOR.value),
    Pending(4, Role.VIEWER.value),
    Pending(5, Role.OWNER.value),
)


@pytest.mark.parametrize(
    ("new_role", "revoked_ids"),
    [
        (None, (1, 2, 3, 4, 5)),  # revoked or left: none of theirs stays
        (Role.OWNER, ()),
        (Role.ADMIN, (1, 5)),  # an owner demoted to admin loses only the owner ones
        (Role.OPERATOR, (1, 2, 3, 4, 5)),
        (Role.VIEWER, (1, 2, 3, 4, 5)),
    ],
)
def test_Q_223_invitations_to_auto_revoke(
    new_role: Role | None, revoked_ids: tuple[int, ...]
) -> None:
    revoked = invitations_to_auto_revoke(new_role, PENDING)

    assert tuple(invitation.id for invitation in revoked) == revoked_ids
    assert all(invitation in PENDING for invitation in revoked)


def test_Q_223_nothing_pending_revokes_nothing() -> None:
    assert invitations_to_auto_revoke(None, []) == ()
    assert invitations_to_auto_revoke(Role.VIEWER, iter(())) == ()


def test_Q_223_auto_revoke_agrees_with_decide_invite() -> None:
    for new_role in Role:
        revoked = invitations_to_auto_revoke(new_role, PENDING)
        kept = [invitation for invitation in PENDING if invitation not in revoked]

        assert all(decide_invite(new_role, Role(i.role)) is Decision.FORBIDDEN for i in revoked)
        assert all(decide_invite(new_role, Role(i.role)) is Decision.ALLOW for i in kept)
