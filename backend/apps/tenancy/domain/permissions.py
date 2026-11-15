"""The permission matrix of SPEC-02 as code (spec §4/§4.1, RN-TEN-09, design.md §3.8).

Pure: no Django.

``TENANCY_ACTIONS`` is the only source of permissions of this module: an action that is not here
cannot be done. It says which roles get past the gate; what depends on the target (an admin never
touches an owner, nobody raises their own role, the last owner) is ``role_rules.py`` (T-TEN-07),
which each service consults. It is read-only.

The tests transcribe the tables of the spec and compare them with ``require()``
(``tests/tenancy/domain/test_permission_matrix_*.py``): a change here without a change in the
spec, or the other way round, fails (C-12).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from apps.common.authz.actions import ActionKind, ActionSpec
from apps.common.authz.roles import Role


class TenancyAction(StrEnum):
    ORG_READ = "org.read"
    ORG_UPDATE = "org.update"
    MEMBER_LIST = "member.list"
    MEMBER_CHANGE_ROLE = "member.change_role"
    MEMBER_REVOKE = "member.revoke"
    MEMBER_LEAVE = "member.leave"
    INVITATION_LIST = "invitation.list"
    INVITATION_CREATE = "invitation.create"
    INVITATION_RESEND = "invitation.resend"
    INVITATION_REVOKE = "invitation.revoke"
    BRANCH_READ = "branch.read"
    BRANCH_CREATE = "branch.create"
    BRANCH_UPDATE = "branch.update"
    BRANCH_DEACTIVATE = "branch.deactivate"
    BRANCH_REACTIVATE = "branch.reactivate"


_EVERY_ROLE = frozenset(Role)
_MANAGERS = frozenset({Role.OWNER, Role.ADMIN})

_READ, _WRITE, _REDUCE = ActionKind.READ, ActionKind.WRITE, ActionKind.REDUCE_ACCESS

_MATRIX: dict[TenancyAction, tuple[frozenset[Role], ActionKind, str | None]] = {
    TenancyAction.ORG_READ: (_EVERY_ROLE, _READ, None),
    TenancyAction.ORG_UPDATE: (_MANAGERS, _WRITE, None),
    TenancyAction.MEMBER_LIST: (_MANAGERS, _READ, None),
    TenancyAction.MEMBER_CHANGE_ROLE: (_MANAGERS, _WRITE, None),
    TenancyAction.MEMBER_REVOKE: (_MANAGERS, _REDUCE, None),
    TenancyAction.MEMBER_LEAVE: (_EVERY_ROLE, _REDUCE, None),
    TenancyAction.INVITATION_LIST: (_MANAGERS, _READ, None),
    TenancyAction.INVITATION_CREATE: (_MANAGERS, _WRITE, None),
    TenancyAction.INVITATION_RESEND: (_MANAGERS, _WRITE, None),
    TenancyAction.INVITATION_REVOKE: (_MANAGERS, _REDUCE, None),
    TenancyAction.BRANCH_READ: (_EVERY_ROLE, _READ, "branches:read"),
    TenancyAction.BRANCH_CREATE: (_MANAGERS, _WRITE, None),
    TenancyAction.BRANCH_UPDATE: (_MANAGERS, _WRITE, None),
    TenancyAction.BRANCH_DEACTIVATE: (_MANAGERS, _WRITE, None),
    TenancyAction.BRANCH_REACTIVATE: (_MANAGERS, _WRITE, None),
}

TENANCY_ACTIONS: Mapping[TenancyAction, ActionSpec] = MappingProxyType(
    {
        action: ActionSpec(name=action.value, roles=roles, kind=kind, api_key_scope=scope)
        for action, (roles, kind, scope) in _MATRIX.items()
    }
)
