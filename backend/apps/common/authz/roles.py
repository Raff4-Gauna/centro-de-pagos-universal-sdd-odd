"""The roles of a membership (RN-TEN-07, design.md §3.1): a closed set, per organization.

Pure: no Django. The database keeps the role as ``varchar`` with a ``CheckConstraint`` built from
this enum (``membership_role_valid``), so a role outside the four never reaches a row.

``ROLE_RANK`` orders them from ``viewer`` up to ``owner``: the role rules (T-TEN-07) read it to tell
a raise from a demotion (nobody raises their own role, RN-TEN-09). It is read-only.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


ROLE_RANK: Mapping[Role, int] = MappingProxyType(
    {Role.VIEWER: 1, Role.OPERATOR: 2, Role.ADMIN: 3, Role.OWNER: 4}
)
