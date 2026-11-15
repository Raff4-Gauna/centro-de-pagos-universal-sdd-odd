"""The permission matrix with the organization ``suspended`` (spec §4.1, Q-208, Q-221).

Pure: no database.

``SUSPENDED_MATRIX`` is a literal transcription of ``spec.sdd.md`` 1.0.2 §4.1 over the table of §4:
reads stay as they are, the writes that add or change access are rejected with
``409 organization_suspended`` and those that reduce it (revoke a membership, leave, revoke an
invitation) still pass (Q-221). A role the matrix denies gets ``403`` before the suspension is
looked at (design.md §3.5: ``403`` role, then ``409`` suspended).

``OK`` = allowed, ``F`` = ``403 forbidden``, ``S`` = ``409 organization_suspended``.
"""

from __future__ import annotations

import uuid

import pytest

from apps.common.authz.checks import allowed_actions, require
from apps.common.authz.roles import Role
from apps.common.tenancy.context import Actor, ApiKeyActor, OrgStatus, TenantContext, UserActor
from apps.common.tenancy.errors import Forbidden, OrganizationSuspended
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction

OK, F, S = "ok", "forbidden", "organization_suspended"
ROLES = (Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.VIEWER)

# spec.sdd.md 1.0.2 §4.1:                  owner admin operator viewer ERP
SUSPENDED_MATRIX: dict[str, tuple[str, str, str, str, str]] = {
    "org.read": (OK, OK, OK, OK, F),
    "org.update": (S, S, F, F, F),
    "member.list": (OK, OK, F, F, F),
    "member.change_role": (S, S, F, F, F),
    "member.revoke": (OK, OK, F, F, F),  # Q-221: reduce el acceso
    "member.leave": (OK, OK, OK, OK, F),  # Q-221: reduce el acceso
    "invitation.list": (OK, OK, F, F, F),
    "invitation.create": (S, S, F, F, F),
    "invitation.resend": (S, S, F, F, F),
    "invitation.revoke": (OK, OK, F, F, F),  # Q-221: reduce el acceso
    "branch.read": (OK, OK, OK, OK, OK),
    "branch.create": (S, S, F, F, F),
    "branch.update": (S, S, F, F, F),
    "branch.deactivate": (S, S, F, F, F),
    "branch.reactivate": (S, S, F, F, F),
}


def suspended(actor: Actor) -> TenantContext:
    return TenantContext(
        organization_id=uuid.uuid4(), organization_status=OrgStatus.SUSPENDED, actor=actor
    )


def user(role: Role) -> UserActor:
    return UserActor(user_id=uuid.uuid4(), membership_id=uuid.uuid4(), role=role)


def outcome(ctx: TenantContext, action: str) -> str:
    try:
        require(ctx, TENANCY_ACTIONS[TenancyAction(action)])
    except (Forbidden, OrganizationSuspended) as error:
        return str(error.get_codes())
    return OK


MATRIX_CASES = [
    pytest.param(action, role, row[column], id=f"{action}-{role}")
    for action, row in SUSPENDED_MATRIX.items()
    for column, role in enumerate(ROLES)
]


@pytest.mark.parametrize(("action", "role", "expected"), MATRIX_CASES)
def test_RN_TEN_18_suspended_matrix_equals_spec_for_every_role(
    action: str, role: Role, expected: str
) -> None:
    assert outcome(suspended(user(role)), action) == expected


@pytest.mark.parametrize("action", SUSPENDED_MATRIX)
def test_RN_TEN_18_suspended_matrix_equals_spec_for_the_erp(action: str) -> None:
    erp = ApiKeyActor(key_id=uuid.uuid4(), scopes=frozenset({"branches:read"}))

    assert outcome(suspended(erp), action) == SUSPENDED_MATRIX[action][4]


def test_all_actions_declared_in_the_suspended_matrix() -> None:
    assert {action.value for action in TenancyAction} == set(SUSPENDED_MATRIX)


def test_RN_TEN_18_suspended_answers_409() -> None:
    with pytest.raises(OrganizationSuspended) as rejected:
        require(suspended(user(Role.OWNER)), TENANCY_ACTIONS[TenancyAction.BRANCH_CREATE])

    assert rejected.value.status_code == 409


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
@pytest.mark.parametrize("action", ["member.list", "invitation.list"])
def test_AC_TEN_34_member_list_denied_while_suspended(action: str, role: Role) -> None:
    assert outcome(suspended(user(role)), action) == F


def test_RN_TEN_18_allowed_actions_drop_the_writes_while_suspended() -> None:
    assert allowed_actions(suspended(user(Role.ADMIN)), TENANCY_ACTIONS.values()) == [
        "org.read",
        "member.list",
        "member.revoke",
        "member.leave",
        "invitation.list",
        "invitation.revoke",
        "branch.read",
    ]
