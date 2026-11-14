"""The closed set of roles (RN-TEN-07, design.md §3.1) and the role of a ``UserActor``.

Pure: no database.
"""

from __future__ import annotations

import uuid

import pytest

from apps.common.authz.roles import ROLE_RANK, Role
from apps.common.tenancy.context import UserActor


def test_RN_TEN_07_roles_are_exactly_the_four_of_the_spec() -> None:
    assert [role.value for role in Role] == ["owner", "admin", "operator", "viewer"]


def test_RN_TEN_07_rank_orders_every_role_from_owner_down() -> None:
    assert set(ROLE_RANK) == set(Role)
    assert sorted(Role, key=ROLE_RANK.__getitem__, reverse=True) == [
        Role.OWNER,
        Role.ADMIN,
        Role.OPERATOR,
        Role.VIEWER,
    ]
    assert len(set(ROLE_RANK.values())) == len(Role)


def test_RN_TEN_07_rank_is_read_only() -> None:
    with pytest.raises(TypeError):
        ROLE_RANK[Role.VIEWER] = 99  # type: ignore[index]


def test_RN_TEN_07_user_actor_takes_a_role() -> None:
    actor = UserActor(user_id=uuid.uuid4(), membership_id=uuid.uuid4(), role=Role.ADMIN)

    assert actor.role is Role.ADMIN


@pytest.mark.parametrize("role", ["owner", "superuser", None])
def test_RN_TEN_07_user_actor_rejects_anything_but_a_role(role: object) -> None:
    with pytest.raises(TypeError, match="role must be a Role"):
        UserActor(user_id=uuid.uuid4(), membership_id=uuid.uuid4(), role=role)  # type: ignore[arg-type]
