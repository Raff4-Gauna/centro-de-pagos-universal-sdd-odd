"""AC-TEN-10: a model scope allowed in one file only (design.md §3.4; note of T-TEN-04, PR #104).

``Invitation.for_session_accept(id)`` reads any organization's invitation by id: it is a scope of
``Invitation`` (``allowlists.MODEL_SCOPES``) and, on top of that, it may appear only where
``allowlists.RESTRICTED_SCOPE_ALLOWLIST`` says, ``services/invitation_accept.py``. Every other use
fails, called or not, by alias or through ``getattr``. Nothing under ``tmp_path`` is imported.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.allowlists import (
    ALLOWED_TENANT_MANAGERS,
    MODEL_SCOPES,
    RESTRICTED_SCOPE_ALLOWLIST,
    RESTRICTED_SCOPES,
    TENANT_SCOPES,
    AllowEntry,
)
from tests.architecture.ast_rules import SourceTree, real_trees
from tests.architecture.tenant_rules import restricted_scope_violations

SERVICE = "apps/tenancy/services/invitation_accept.py"
CALL = "Invitation.objects.for_session_accept(invitation_id).first()\n"


def tree_with(tmp_path: Path, relative: str, body: str) -> SourceTree:
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(body, encoding="utf-8")
    return SourceTree(tmp_path, "apps")


@pytest.mark.parametrize(
    ("relative", "body", "symbol"),
    [
        ("tenancy/selectors/invitations.py", CALL, "Invitation.objects.for_session_accept"),
        ("tenancy/services/invitation_port.py", CALL, "Invitation.objects.for_session_accept"),
        (
            "charges/services/x.py",
            "I = Invitation\nI.objects.for_session_accept(i)\n",
            "I.objects.for_session_accept",
        ),
        ("tenancy/api/views.py", "f = qs.for_session_accept\n", "qs.for_session_accept"),
        (
            "tenancy/api/views.py",
            "getattr(qs, 'for_session_accept')(i)\n",
            "getattr(qs, 'for_session_accept')",
        ),
    ],
    ids=["selector", "other-service", "alias", "uncalled", "getattr"],
)
def test_AC_TEN_10_for_session_accept_outside_its_service_fails(
    tmp_path: Path, relative: str, body: str, symbol: str
) -> None:
    tree = tree_with(tmp_path / "x", relative, body)
    violations = restricted_scope_violations([tree], RESTRICTED_SCOPE_ALLOWLIST)
    assert [v.symbol for v in violations if v.line] == [symbol]
    assert all(v.path == f"apps/{relative}" for v in violations if v.line)


def test_AC_TEN_10_for_session_accept_in_its_service_passes(tmp_path: Path) -> None:
    tree = tree_with(tmp_path, "tenancy/services/invitation_accept.py", CALL)
    entry = AllowEntry(SERVICE, "Invitation.objects.for_session_accept", "§4.4", count=1)
    assert restricted_scope_violations([tree], (entry,)) == []
    twice = tree_with(tmp_path, "tenancy/services/invitation_accept.py", CALL + CALL)
    [extra] = restricted_scope_violations([twice], (entry,))
    assert extra.msg == "allowlist entry expects 1 occurrence(s), found 2"


def test_AC_TEN_10_restricted_scope_is_a_model_scope_not_a_general_one() -> None:
    assert MODEL_SCOPES["tenancy.Invitation"] >= RESTRICTED_SCOPES
    assert not RESTRICTED_SCOPES & TENANT_SCOPES  # it never opens any other model's manager
    owners = [label for label, scopes in MODEL_SCOPES.items() if scopes & RESTRICTED_SCOPES]
    assert owners == ["tenancy.Invitation"]


def test_AC_TEN_10_real_code_uses_for_session_accept_in_its_service_only() -> None:
    trees = real_trees(Path(__file__).resolve().parents[2])
    assert restricted_scope_violations(trees, RESTRICTED_SCOPE_ALLOWLIST) == []
    assert [e.path for e in RESTRICTED_SCOPE_ALLOWLIST] == [SERVICE]
    # C-01 lets the one raw opening of this service through, and only that one.
    [c01] = [e for e in ALLOWED_TENANT_MANAGERS if e.path == SERVICE]
    assert (c01.symbol, c01.count) == ("Invitation.objects", 1)
