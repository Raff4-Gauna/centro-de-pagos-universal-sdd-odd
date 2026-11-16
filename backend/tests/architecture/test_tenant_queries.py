"""AC-TEN-10 (RN-TEN-02, design.md §9): raw access to tenant data fails the build.

The AST rules (``tenant_rules``, ``tenant_instance_rules``) run on the real ``apps/`` and
``config/``, on the synthetic tree under ``synthetic/`` (which stands for ``apps/``) and on one-off
modules written to ``tmp_path``; nothing of those trees is imported. The real run takes the tenant
models and their managers from Django's registry (no database). The registry rules (every business
model is a tenant model, every manager of one fails closed) are in ``test_tenant_models.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.apps import apps as registry
from django.db import models

from apps.common.tenancy.querysets import TenantQuerySet
from tests.architecture.allowlists import (
    TENANT_QUERY_ALLOWLIST,
    TENANT_SCOPES,
    UNSCOPED_ALLOWLIST,
    AllowEntry,
)
from tests.architecture.ast_rules import SourceTree, iter_sources, real_trees
from tests.architecture.tenant_model_rules import tenant_names
from tests.architecture.tenant_rules import tenant_query_violations, unscoped_violations

BACKEND = Path(__file__).resolve().parents[2]
SYNTHETIC = SourceTree(Path(__file__).resolve().parent / "synthetic", "apps")
BAD_OBJECTS = "apps/charges/services/bad_objects.py"
MODELS = frozenset({"Charge", "Widget", "Organization"})
MANAGERS = frozenset({"objects", "all_objects"})
SERVICE = "charges/services/rows.py"


def write(tmp_path: Path, relative: str, body: str) -> SourceTree:
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(body, encoding="utf-8")
    return SourceTree(tmp_path, "apps")


def symbols(tmp_path: Path, body: str, relative: str = SERVICE) -> list[str]:
    """Symbols the tenant rule flags in ``body`` written as ``apps/<relative>``."""
    tree = write(tmp_path, relative, body)
    return [v.symbol for v in tenant_query_violations([tree], MODELS, (), MANAGERS)]


def test_AC_TEN_10_raw_manager_fails_naming_the_file() -> None:
    violations = tenant_query_violations([SYNTHETIC], frozenset({"Charge"}), allowlist=())
    assert [(v.path, v.line, v.symbol) for v in violations] == [
        (BAD_OBJECTS, 12, "Charge.objects.filter")
    ]
    assert "apps/charges/services/ok_scoped.py" in {s.path for s in iter_sources([SYNTHETIC])}


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("Widget.objects.filter(a=1)\n", "Widget.objects.filter"),
        ("Widget.objects.all()\n", "Widget.objects.all"),
        ("qs = Widget.objects\n", "Widget.objects"),
        ("models.Widget.objects.get(pk=1)\n", "models.Widget.objects.get"),
        ("getattr(Widget, 'objects').all()\n", "getattr(Widget, 'objects')"),
        ("Organization.objects.get(pk=1)\n", "Organization.objects.get"),
        # Every manager of a tenant model, and the names a module binds to the model.
        ("Widget.all_objects.filter(a=1)\n", "Widget.all_objects.filter"),
        ("from apps.p.models import Widget as W\nW.objects.all()\n", "W.objects.all"),
        ("M = Widget\nM.objects.all()\n", "M.objects.all"),
        ("attrgetter('objects')(Widget)\n", "attrgetter('objects')"),
        ("attrgetter('all_objects')(Widget).all()\n", "attrgetter('all_objects')"),
        # Scope first: after a clone the AST cannot tell (documented in tenant_rules).
        ("Widget.objects.filter(a=1).for_tenant(ctx)\n", "Widget.objects.filter"),
        # Unscoped subqueries (design.md §3.4, known gap of the runtime guard).
        (
            "Charge.objects.for_tenant(ctx).filter(widget_id__in=Widget.objects.values('pk'))\n",
            "Widget.objects.values",
        ),
        ("Subquery(Widget.objects.filter(pk=OuterRef('w')))\n", "Widget.objects.filter"),
        ("Exists(Widget.objects.filter(pk=OuterRef('w')))\n", "Widget.objects.filter"),
        ("Prefetch('w', queryset=Widget.objects.all())\n", "Widget.objects.all"),
        (
            "User.objects.filter(org__in=Organization.objects.values('pk'))\n",
            "Organization.objects.values",
        ),
    ],
)
def test_AC_TEN_10_manager_without_scope_fails(tmp_path: Path, body: str, symbol: str) -> None:
    assert symbols(tmp_path, body) == [symbol]


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("Widget._base_manager.all()\n", "Widget._base_manager"),
        ("Widget._default_manager.all()\n", "Widget._default_manager"),
        ("Widget._meta.base_manager.all()\n", "Widget._meta.base_manager"),
        ("Widget._meta.default_manager.all()\n", "Widget._meta.default_manager"),
        ("w.save_base(raw=True)\n", "w.save_base"),
        ("w._save_table(cls=Widget)\n", "w._save_table"),
        ("w._do_update(qs, 'default', 1, [], None, False)\n", "w._do_update"),
        ("w._do_insert(m, 'default', [], [], False)\n", "w._do_insert"),
        ("qs._insert([w], fields=[])\n", "qs._insert"),
        ("qs._batched_insert([w], [], 10)\n", "qs._batched_insert"),
        ("qs._update([])\n", "qs._update"),
        ("qs._raw_delete('default')\n", "qs._raw_delete"),
        ("super()._do_update(qs, 'default', 1, [], None, False)\n", "super()._do_update"),
        ("getattr(w, 'save_base')()\n", "getattr(w, 'save_base')"),
        ("attrgetter('_base_manager.all')(Widget)\n", "attrgetter('_base_manager.all')"),
        ("other._update()\n", "other._update"),
    ],
)
def test_AC_TEN_10_persistence_internals_fail(tmp_path: Path, body: str, symbol: str) -> None:
    assert symbols(tmp_path, body) == [symbol]


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        (
            "Widget.objects.for_tenant(ctx).raw('SELECT * FROM w')\n",
            "Widget.objects.for_tenant(ctx).raw",
        ),
        ("qs.extra(where=['1 = 1'])\n", "qs.extra"),
        ("with connection.cursor() as c:\n    pass\n", "connection.cursor"),
        ("connections['default'].cursor()\n", "connections['default'].cursor"),
        ("qs.annotate(n=RawSQL('SELECT 1', []))\n", "RawSQL"),
        ("qs.annotate(n=expressions.RawSQL('SELECT 1', []))\n", "expressions.RawSQL"),
        ("connection.chunked_cursor()\n", "connection.chunked_cursor"),
        ("connection.connection.execute('SELECT 1')\n", "connection.connection"),
        ("connections['default'].connection\n", "connections['default'].connection"),
        ("RawQuerySet('SELECT * FROM w', model=Widget)\n", "RawQuerySet"),
        ("QuerySet(Widget).all()\n", "QuerySet"),
        ("models.QuerySet(model=Widget)\n", "models.QuerySet"),
        ("qs.annotate(n=Func(F('a'), template='(SELECT 1)'))\n", "Func"),
        ("class Leak(models.Func):\n    template = '(SELECT %(expressions)s)'\n", "Leak"),
    ],
)
def test_AC_TEN_10_raw_sql_fails(tmp_path: Path, body: str, symbol: str) -> None:
    assert symbols(tmp_path, body) == [symbol]


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("def f(w, other):\n    w.pk = other\n    w.refresh_from_db()\n", "w.refresh_from_db"),
        ("def f(w, other):\n    w.id = other\n    w.refresh_from_db()\n", "w.refresh_from_db"),
        ("def f(w, o):\n    setattr(w, 'pk', o)\n    w.refresh_from_db()\n", "w.refresh_from_db"),
        ("def f(o):\n    w = Widget(pk=o)\n    w.refresh_from_db()\n", "w.refresh_from_db"),
        ("def f(o):\n    w = Widget(o)\n    w.refresh_from_db()\n", "w.refresh_from_db"),
        ("def f(o):\n    Widget(pk=o).refresh_from_db()\n", "Widget(pk=o).refresh_from_db"),
        (
            "async def f(w, o):\n    w.pk = o\n    await w.arefresh_from_db()\n",
            "w.arefresh_from_db",
        ),
        (
            "def f(self, o):\n    self.w.pk = o\n    self.w.refresh_from_db(fields=['a'])\n",
            "self.w.refresh_from_db",
        ),
        ("w.pk = other\nw.refresh_from_db()\n", "w.refresh_from_db"),
    ],
)
def test_AC_TEN_10_refresh_after_repointing_the_pk_fails(
    tmp_path: Path, body: str, symbol: str
) -> None:
    assert symbols(tmp_path, body) == [symbol]


@pytest.mark.parametrize(
    ("body", "flagged"),
    [
        ("TenantContext(organization_id=o, organization_status=s, actor=a)\n", ["TenantContext"]),
        ("from apps.common.tenancy.context import TenantContext as Ctx\nCtx(o)\n", ["Ctx"]),
        (
            "from apps.common.tenancy import context\ncontext.TenantContext(o)\n",
            ["context.TenantContext"],
        ),
        ("B = TenantContext\nB(o, s, a)\n", ["B", "TenantContext"]),
        ("partial(TenantContext, organization_id=o)\n", ["TenantContext"]),
        ("type(ctx)(o, s, a)\n", ["type(ctx)"]),
        ("ctx.__class__(o, s, a)\n", ["ctx.__class__"]),
    ],
)
def test_AC_TEN_10_tenant_context_built_outside_resolution_fails(
    tmp_path: Path, body: str, flagged: list[str]
) -> None:
    assert sorted(symbols(tmp_path, body)) == flagged


@pytest.mark.parametrize(
    ("relative", "body"),
    [
        (SERVICE, "Widget.objects.for_tenant(ctx).filter(a=1)\n"),
        (SERVICE, "Organization.objects.for_tenant(ctx).get()\n"),
        (SERVICE, "Exists(Widget.objects.for_tenant(ctx).filter(pk=OuterRef('w')))\n"),
        (SERVICE, "Charge.objects.for_tenant(ctx).filter(w__in=Widget.objects.for_tenant(ctx))\n"),
        # Global entities of SPEC-01 (C-01 checks them in services) and unknown names.
        (SERVICE, "User.objects.filter(email=e)\n"),
        # The copy idiom: a new row of the active organization.
        (SERVICE, "def f(w):\n    w.pk = None\n    w.save()\n    w.refresh_from_db()\n"),
        (SERVICE, "def f(w):\n    w.refresh_from_db()\n"),
        (SERVICE, "def f(w, o):\n    w.pk = o\n\ndef g(w):\n    w.refresh_from_db()\n"),
        # The module's own helper, not Django's.
        (
            SERVICE,
            "class S:\n    def _update(self):\n        pass\n\n"
            "    def run(self):\n        self._update()\n",
        ),
        (SERVICE, "def f(ctx: TenantContext) -> TenantContext:\n    return ctx\n"),
        (SERVICE, "def f(ctx):\n    assert isinstance(ctx, TenantContext)\n"),
        (SERVICE, "Widget.all_objects.for_tenant(ctx).count()\n"),
        (SERVICE, "db.connection\nqs.annotate(n=Func(F('a'), function='LOWER'))\n"),
        ("common/tenancy/celery.py", "TenantContext(o, s, a)\n"),
        ("tenancy/api/permissions.py", "TenantContext(o, s, a)\n"),
        # The mechanism, migrations and tests are not business code.
        ("common/tenancy/querysets.py", "Widget._base_manager.all()\n"),
        ("common/tenancy/models.py", "super()._do_update(qs, 'default', 1, [], None, False)\n"),
        ("charges/migrations/0002_data.py", "Widget.objects.all()\n"),
        ("charges/tests/test_rows.py", "Widget.objects.all()\nconnection.cursor()\n"),
    ],
)
def test_AC_TEN_10_scoped_call_passes(tmp_path: Path, relative: str, body: str) -> None:
    assert symbols(tmp_path, body, relative) == []


def test_AC_TEN_10_own_method_is_exempt_only_in_its_class(tmp_path: Path) -> None:
    body = (
        "class S:\n    def _update(self):\n        pass\n\n"
        "class W(TenantModel):\n    def run(self):\n        self._update()\n"
    )
    assert symbols(tmp_path, body) == ["self._update"]


def test_AC_TEN_10_config_is_scanned(tmp_path: Path) -> None:
    file = tmp_path / "config" / "settings" / "x.py"
    file.parent.mkdir(parents=True)
    file.write_text("from django.db import connection\nconnection.cursor()\n", encoding="utf-8")
    tree = SourceTree(tmp_path / "config", "config")
    assert [v.path for v in tenant_query_violations([tree], MODELS, ())] == ["config/settings/x.py"]


def test_AC_TEN_10_allowlisted_access_passes_and_dead_entry_fails(tmp_path: Path) -> None:
    tree = write(tmp_path, SERVICE, "connection.cursor()\n")
    path = f"apps/{SERVICE}"
    entry = AllowEntry(path, "connection.cursor", "synthetic: SELECT 1")
    assert tenant_query_violations([tree], MODELS, allowlist=(entry,)) == []
    dead = AllowEntry(path, "qs.extra", "matches nothing")
    assert [v.msg for v in tenant_query_violations([tree], MODELS, (entry, dead))] == [
        "dead allowlist entry: matches no violation"
    ]
    blank = AllowEntry(path, "connection.cursor", " ")
    assert [v.msg for v in tenant_query_violations([tree], MODELS, (blank,))][-1] == (
        "allowlist entry without a reason"
    )


def test_AC_TEN_10_allowlist_counts_occurrences(tmp_path: Path) -> None:
    tree = write(tmp_path, SERVICE, "connection.cursor()\n\nconnection.cursor()\n")
    entry = AllowEntry(f"apps/{SERVICE}", "connection.cursor", "synthetic: SELECT 1", count=1)
    assert [v.msg for v in tenant_query_violations([tree], MODELS, (entry,))] == [
        "allowlist entry expects 1 occurrence(s), found 2"
    ]
    twice = AllowEntry(f"apps/{SERVICE}", "connection.cursor", "synthetic: SELECT 1", count=2)
    assert tenant_query_violations([tree], MODELS, (twice,)) == []


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        (
            "Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND).get(pk=o)\n",
            "Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND)",
        ),
        ("qs.unscoped(reason)\n", "qs.unscoped(reason)"),
        ("getattr(qs, 'unscoped')(reason)\n", "getattr(qs, 'unscoped')"),
        ("f = qs.unscoped\nf(reason)\n", "qs.unscoped"),
        ("methodcaller('unscoped', reason)(qs)\n", "methodcaller('unscoped', reason)"),
        # A function of the module with that name does not exempt another receiver.
        ("def unscoped(self):\n    pass\n\nqs.unscoped(r)\n", "qs.unscoped(r)"),
    ],
)
def test_AC_TEN_10_unscoped_outside_allowlist_fails(tmp_path: Path, body: str, symbol: str) -> None:
    tree = write(tmp_path, SERVICE, body)
    assert [v.symbol for v in unscoped_violations([tree], allowlist=())] == [symbol]
    # The manager rule lets ``X.objects.unscoped(...)`` through: this rule is the one that decides.
    assert symbols(tmp_path, body) == []


def test_AC_TEN_10_unscoped_own_method_passes(tmp_path: Path) -> None:
    body = (
        "class S:\n    def unscoped(self):\n        pass\n\n"
        "    def run(self):\n        self.unscoped()\n"
    )
    assert unscoped_violations([write(tmp_path, SERVICE, body)], allowlist=()) == []


def test_AC_TEN_10_unscoped_entry_pins_the_reason(tmp_path: Path) -> None:
    call = "Organization.objects.unscoped(UnscopedReason.TENANT_RESOLUTION)"
    tree = write(tmp_path, "tenancy/selectors/resolution.py", f"{call}.get(pk=o)\n")
    path = "apps/tenancy/selectors/resolution.py"
    assert unscoped_violations([tree], (AllowEntry(path, call, "design.md §3.5"),)) == []
    other = AllowEntry(path, call.replace("TENANT_RESOLUTION", "PLATFORM_COMMAND"), "wrong")
    assert [v.msg for v in unscoped_violations([tree], (other,))] == [
        "dead allowlist entry: matches no violation",
        "unscoped(reason) outside UNSCOPED_ALLOWLIST",
    ]


def test_AC_TEN_10_scopes_are_tenant_queryset_methods() -> None:
    """A scope name that Django's ``QuerySet`` also has (``filter``) would open any manager."""
    for scope in TENANT_SCOPES:
        assert callable(getattr(TenantQuerySet, scope, None)), scope
        assert not hasattr(models.QuerySet, scope), scope


def test_AC_TEN_10_real_code_has_no_violations() -> None:
    tenant_models, managers = tenant_names(registry.get_models())
    assert {"Organization", "Membership"} <= tenant_models, "the registry gave no tenant model"
    trees = real_trees(BACKEND)
    assert {s.path.split("/")[0] for s in iter_sources(trees)} == {"apps", "config"}
    assert tenant_query_violations(trees, tenant_models, TENANT_QUERY_ALLOWLIST, managers) == []
    assert unscoped_violations(trees, UNSCOPED_ALLOWLIST) == []
