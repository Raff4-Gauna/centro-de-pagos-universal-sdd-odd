"""``system_context`` and ``MembershipMutex`` stay in their modules (AC-TEN-10, review of PR #117).

``system_context(organization_id, reason)`` builds a ``SystemActor`` context for any organization:
called from a view with an id of the request body, it would skip the membership and the suspension.
``MembershipMutex(...)`` built by hand would pass for a lock the transaction never took. Both are
checked like ``TenantContext`` (``tenant_instance_rules.RESTRICTED_VALUES``): any use as a value
outside the allowed modules fails; a type annotation passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.test_tenant_queries import SERVICE, symbols

SELECTOR = "tenancy/selectors/memberships.py"


@pytest.mark.parametrize(
    ("relative", "body", "flagged"),
    [
        (SERVICE, "system_context(o, SystemReason.WEBHOOK)\n", ["system_context"]),
        (SERVICE, "locks.system_context(o, r)\n", ["locks.system_context"]),
        (SERVICE, "from x import system_context as sc\nsc(o, r)\n", ["sc"]),
        (SERVICE, "f = system_context\n", ["system_context"]),
        ("tenancy/api/permissions.py", "system_context(o, r)\n", ["system_context"]),
        ("common/tenancy/current.py", "system_context(o, r)\n", ["system_context"]),
    ],
)
def test_AC_TEN_10_system_context_outside_the_task_bases_fails(
    tmp_path: Path, relative: str, body: str, flagged: list[str]
) -> None:
    assert symbols(tmp_path, body, relative) == flagged


@pytest.mark.parametrize(
    ("relative", "body", "flagged"),
    [
        (SERVICE, "MembershipMutex(ctx, s, t)\n", ["MembershipMutex"]),
        (SERVICE, "locks.MembershipMutex(ctx, s, t)\n", ["locks.MembershipMutex"]),
        (SELECTOR, "from x import MembershipMutex as M\nM(ctx, s, t)\n", ["M"]),
        ("common/tenancy/locks.py", "MembershipMutex(ctx, s, t)\n", ["MembershipMutex"]),
    ],
)
def test_AC_TEN_10_membership_mutex_built_outside_its_module_fails(
    tmp_path: Path, relative: str, body: str, flagged: list[str]
) -> None:
    assert symbols(tmp_path, body, relative) == flagged


@pytest.mark.parametrize(
    ("relative", "body"),
    [
        ("common/tenancy/celery.py", "system_context(o, SystemReason.CELERY)\n"),
        ("common/tenancy/locks.py", "def f(o, r):\n    return system_context(o, r)\n"),
        ("tenancy/selectors/locks.py", "MembershipMutex(ctx, s, t)\n"),
        (SERVICE, "def f(mutex: MembershipMutex) -> int:\n    return 1\n"),
        (SERVICE, "def f(m):\n    assert isinstance(m, MembershipMutex)\n"),
    ],
)
def test_AC_TEN_10_restricted_values_pass_in_their_modules(
    tmp_path: Path, relative: str, body: str
) -> None:
    assert symbols(tmp_path, body, relative) == []
