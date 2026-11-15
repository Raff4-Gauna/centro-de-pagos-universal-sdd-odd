"""How a module declares what an action needs (RN-TEN-09, design.md §3.1, §3.8). Pure: no Django.

Every action of every module is an ``ActionSpec``: the roles that may run it, its ``ActionKind``
and, if an ERP may call it, the scope of the API key (SPEC-11). What a module does not declare
cannot be done (deny by default, ``checks.require``).

``SUSPENDED_ALLOWED_KINDS`` is the one place that says what still runs with the organization
``suspended`` (Q-208, Q-221): reads and the writes that reduce access. Every other kind is
rejected with ``409 organization_suspended``, so a module that adds a write cannot forget the
suspension: it has to give the action a kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apps.common.authz.roles import Role


class ActionKind(StrEnum):
    READ = "read"
    WRITE = "write"
    REDUCE_ACCESS = "reduce_access"


SUSPENDED_ALLOWED_KINDS: frozenset[ActionKind] = frozenset(
    {ActionKind.READ, ActionKind.REDUCE_ACCESS}
)


@dataclass(frozen=True, slots=True)
class ActionSpec:
    name: str
    roles: frozenset[Role]
    kind: ActionKind
    api_key_scope: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")
        if not isinstance(self.roles, frozenset) or not all(
            isinstance(role, Role) for role in self.roles
        ):
            raise TypeError("roles must be a frozenset of Role")
        if not isinstance(self.kind, ActionKind):
            raise TypeError("kind must be an ActionKind")
