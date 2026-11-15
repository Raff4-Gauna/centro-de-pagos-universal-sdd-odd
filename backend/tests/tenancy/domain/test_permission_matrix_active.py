"""The permission matrix with the organization ``active`` (RN-TEN-09, design.md §3.8).

Pure: no database.

``SPEC_MATRIX`` is a literal transcription of the table of ``spec.sdd.md`` 1.0.2 §4: one row per
``TenancyAction``, one column per role plus the ERP (API key, Q-216). It is compared with what
``require()`` decides, so a change in the spec forces a change here (C-12). The checks that depend
on the target (roles of the membership or invitation, last owner) are not in the matrix: they live
in ``domain/role_rules.py`` (T-TEN-07).

``Y`` = allowed, ``N`` = ``403 forbidden``. The suspended organization is in
``test_permission_matrix_suspended.py`` (C-14).
"""

from __future__ import annotations

import uuid

import pytest

from apps.common.authz.actions import SUSPENDED_ALLOWED_KINDS, ActionKind, ActionSpec
from apps.common.authz.checks import allowed_actions, require
from apps.common.authz.roles import Role
from apps.common.tenancy.context import (
    Actor,
    ApiKeyActor,
    OrgStatus,
    SystemActor,
    SystemReason,
    TenantContext,
    UserActor,
)
from apps.common.tenancy.errors import Forbidden
from apps.tenancy.domain.permissions import TENANCY_ACTIONS, TenancyAction

Y, N = True, False
ROLES = (Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.VIEWER)
ERP_SCOPES = frozenset({"branches:read"})

# spec.sdd.md 1.0.2 §4:                 owner admin operator viewer ERP
SPEC_MATRIX: dict[str, tuple[bool, bool, bool, bool, bool]] = {
    "org.read": (Y, Y, Y, Y, N),  # Ver datos de la organización activa (Q-216)
    "org.update": (Y, Y, N, N, N),  # Editar datos de la organización (Q-209)
    "member.list": (Y, Y, N, N, N),  # Listar miembros (Q-218)
    "member.change_role": (Y, Y, N, N, N),  # Asignar rol (Q-202)
    "member.revoke": (Y, Y, N, N, N),  # Revocar membership de otro (Q-202)
    "member.leave": (Y, Y, Y, Y, N),  # Abandonar la organización (Q-203)
    "invitation.list": (Y, Y, N, N, N),  # Listar invitaciones pendientes (Q-218)
    "invitation.create": (Y, Y, N, N, N),  # Invitar (Q-202)
    "invitation.resend": (Y, Y, N, N, N),  # Reenviar invitación pendiente (Q-202)
    "invitation.revoke": (Y, Y, N, N, N),  # Revocar invitación pendiente (Q-202)
    "branch.read": (Y, Y, Y, Y, Y),  # Ver sucursales (Q-216: el ERP, en lectura)
    "branch.create": (Y, Y, N, N, N),  # Crear sucursal
    "branch.update": (Y, Y, N, N, N),  # Editar sucursal
    "branch.deactivate": (Y, Y, N, N, N),  # Desactivar sucursal
    "branch.reactivate": (Y, Y, N, N, N),  # Reactivar sucursal
}

# Actions whose effect depends on the roles of the target (owner vs admin, Q-202): AC-TEN-15.
TARGETED_ACTIONS = (
    "member.change_role",
    "member.revoke",
    "invitation.create",
    "invitation.resend",
    "invitation.revoke",
)
# Branch writes, inviting and changing a role: AC-TEN-16.
BRANCH_AND_ROLE_WRITES = (
    "branch.create",
    "branch.update",
    "branch.deactivate",
    "branch.reactivate",
    "invitation.create",
    "member.change_role",
)


def context(actor: Actor) -> TenantContext:
    return TenantContext(
        organization_id=uuid.uuid4(), organization_status=OrgStatus.ACTIVE, actor=actor
    )


def user(role: Role) -> UserActor:
    return UserActor(user_id=uuid.uuid4(), membership_id=uuid.uuid4(), role=role)


def is_allowed(ctx: TenantContext, action: str) -> bool:
    try:
        require(ctx, TENANCY_ACTIONS[TenancyAction(action)])
    except Forbidden:
        return False
    return True


MATRIX_CASES = [
    pytest.param(action, role, row[column], id=f"{action}-{role}")
    for action, row in SPEC_MATRIX.items()
    for column, role in enumerate(ROLES)
]


@pytest.mark.parametrize(("action", "role", "expected"), MATRIX_CASES)
def test_RN_TEN_09_matrix_equals_spec_for_every_role(
    action: str, role: Role, expected: bool
) -> None:
    assert is_allowed(context(user(role)), action) is expected


@pytest.mark.parametrize("action", SPEC_MATRIX)
def test_RN_TEN_09_matrix_equals_spec_for_the_erp(action: str) -> None:
    erp = ApiKeyActor(key_id=uuid.uuid4(), scopes=ERP_SCOPES)

    assert is_allowed(context(erp), action) is SPEC_MATRIX[action][4]


def test_all_actions_declared() -> None:
    assert set(TenancyAction) == set(TENANCY_ACTIONS)
    assert {action.value for action in TenancyAction} == set(SPEC_MATRIX)
    for action, spec in TENANCY_ACTIONS.items():
        assert spec.name == action.value
    assert frozenset({ActionKind.READ, ActionKind.REDUCE_ACCESS}) == SUSPENDED_ALLOWED_KINDS


def test_all_actions_declared_is_read_only() -> None:
    with pytest.raises(TypeError):
        TENANCY_ACTIONS[TenancyAction.ORG_READ] = TENANCY_ACTIONS[TenancyAction.ORG_UPDATE]  # type: ignore[index]


@pytest.mark.parametrize("action", TARGETED_ACTIONS)
def test_AC_TEN_15_matrix_admin_owner_actions(action: str) -> None:
    # The matrix lets owner and admin in; an admin touching an owner is role_rules (T-TEN-07).
    assert is_allowed(context(user(Role.OWNER)), action)
    assert is_allowed(context(user(Role.ADMIN)), action)
    assert not is_allowed(context(user(Role.OPERATOR)), action)
    assert not is_allowed(context(user(Role.VIEWER)), action)


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
@pytest.mark.parametrize("action", BRANCH_AND_ROLE_WRITES)
def test_AC_TEN_16_matrix_operator_viewer(action: str, role: Role) -> None:
    with pytest.raises(Forbidden) as denied:
        require(context(user(role)), TENANCY_ACTIONS[TenancyAction(action)])

    assert denied.value.status_code == 403
    assert denied.value.get_codes() == "forbidden"


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.VIEWER])
@pytest.mark.parametrize("action", ["member.list", "invitation.list"])
def test_AC_TEN_34_member_list_denied(action: str, role: Role) -> None:
    with pytest.raises(Forbidden) as denied:
        require(context(user(role)), TENANCY_ACTIONS[TenancyAction(action)])

    assert denied.value.status_code == 403
    assert "@" not in str(denied.value.detail)


def test_RN_TEN_09_an_api_key_without_the_scope_is_denied() -> None:
    erp = ApiKeyActor(key_id=uuid.uuid4(), scopes=frozenset({"charges:read"}))

    assert not is_allowed(context(erp), "branch.read")


@pytest.mark.parametrize("action", SPEC_MATRIX)
def test_RN_TEN_09_a_system_actor_is_denied_every_action(action: str) -> None:
    # Processes without a user never go through the matrix (design.md §3.6): deny by default.
    assert not is_allowed(context(SystemActor(reason=SystemReason.CELERY)), action)


def test_RN_TEN_09_an_action_without_roles_is_denied_to_every_role() -> None:
    nobody = ActionSpec(name="x.write", roles=frozenset(), kind=ActionKind.WRITE)

    for role in ROLES:
        with pytest.raises(Forbidden):
            require(context(user(role)), nobody)


def test_RN_TEN_09_allowed_actions_lists_what_require_lets_through() -> None:
    specs = TENANCY_ACTIONS.values()

    assert allowed_actions(context(user(Role.VIEWER)), specs) == [
        "org.read",
        "member.leave",
        "branch.read",
    ]
    assert allowed_actions(context(user(Role.OWNER)), specs) == list(SPEC_MATRIX)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "", "name must not be empty"),
        ("roles", frozenset({"owner"}), "roles must be a frozenset of Role"),
        ("roles", {Role.OWNER}, "roles must be a frozenset of Role"),
        ("kind", "read", "kind must be an ActionKind"),
    ],
)
def test_RN_TEN_09_action_spec_rejects_malformed_declarations(
    field: str, value: object, message: str
) -> None:
    fields: dict[str, object] = {
        "name": "org.read",
        "roles": frozenset({Role.OWNER}),
        "kind": ActionKind.READ,
    }
    fields[field] = value

    with pytest.raises((TypeError, ValueError), match=message):
        ActionSpec(**fields)  # type: ignore[arg-type]
