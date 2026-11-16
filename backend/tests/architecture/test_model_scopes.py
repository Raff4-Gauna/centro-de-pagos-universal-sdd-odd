"""AC-TEN-10: the scopes a model declares open the manager of that model only (design.md §3.4).

``allowlists.MODEL_SCOPES`` maps a model label to its own scopes (``Membership.for_user``). The
tenant rule lets ``X.objects.<scope>(...)`` through only when ``X`` is (or the module binds it to)
that model: ``Widget.objects.for_user(u)`` is a raw manager. Nothing under ``tmp_path`` is imported.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.apps import apps as registry
from django.db import models

from apps.common.tenancy.querysets import TenantQuerySet
from tests.architecture.allowlists import MODEL_SCOPES, TENANT_SCOPES
from tests.architecture.ast_rules import SourceTree
from tests.architecture.tenant_rules import tenant_query_violations

MODELS = frozenset({"Membership", "Widget"})
SERVICE = "tenancy/selectors/rows.py"


def symbols(tmp_path: Path, body: str) -> list[str]:
    file = tmp_path / SERVICE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(body, encoding="utf-8")
    tree = SourceTree(tmp_path, "apps")
    return [v.symbol for v in tenant_query_violations([tree], MODELS, ())]


def test_AC_TEN_10_model_scopes_are_methods_of_that_model_only() -> None:
    """A model scope lives on its model's queryset, never on ``TenantQuerySet`` or Django's."""
    assert MODEL_SCOPES, "no model declares a scope"
    for label, scopes in MODEL_SCOPES.items():
        queryset = type(registry.get_model(label).objects.all())
        for scope in scopes:
            assert callable(getattr(queryset, scope, None)), (label, scope)
            assert not hasattr(TenantQuerySet, scope), scope
            assert not hasattr(models.QuerySet, scope), scope
            assert scope not in TENANT_SCOPES, scope


@pytest.mark.parametrize(
    "body",
    [
        "Membership.objects.for_user(user_id).filter(status='active')\n",
        "from apps.tenancy.models import Membership as M\nM.objects.for_user(user_id)\n",
        "M = Membership\nM.objects.for_user(user_id)\n",
    ],
    ids=["model", "import-alias", "assigned-alias"],
)
def test_AC_TEN_10_model_scope_opens_its_model(tmp_path: Path, body: str) -> None:
    assert symbols(tmp_path, body) == []


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("Widget.objects.for_user(user_id)\n", "Widget.objects.for_user"),
        ("W = Widget\nW.objects.for_user(user_id)\n", "W.objects.for_user"),
    ],
)
def test_AC_TEN_10_model_scope_on_another_model_fails(
    tmp_path: Path, body: str, symbol: str
) -> None:
    assert symbols(tmp_path, body) == [symbol]
