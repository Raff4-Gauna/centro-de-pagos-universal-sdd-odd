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


def symbols(tmp_path: Path, body: str, relative: str = SERVICE) -> list[str]:
    file = tmp_path / relative
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


def test_AC_TEN_10_no_other_model_defines_a_model_scope() -> None:
    """The AST rule trusts the class name (``Membership``): no other model may answer the same
    scope, or ``import Widget as Membership`` would open it."""
    names = {scope for scopes in MODEL_SCOPES.values() for scope in scopes}
    for model in registry.get_models():
        own = MODEL_SCOPES.get(model._meta.label, frozenset())
        querysets = {type(manager.get_queryset()) for manager in model._meta.managers}
        for name in names - own:
            assert not hasattr(model, name), (model._meta.label, name)
            assert not any(hasattr(qs, name) for qs in querysets), (model._meta.label, name)


@pytest.mark.parametrize(
    "body",
    [
        "Membership.objects.for_tenant(ctx)._model_scope('for_user', u, user_id=u)\n",
        "getattr(qs, '_model_scope')('x', 1)\n",
    ],
)
def test_AC_TEN_10_model_scope_builder_outside_models_fails(tmp_path: Path, body: str) -> None:
    assert len(symbols(tmp_path / "selectors", body)) == 1
    assert symbols(tmp_path / "models", body, "tenancy/models/thing.py") == []
