"""AC-TEN-10 (RN-TEN-02, RN-TEN-01; design.md §3.4 and §9; ADR-0001) checked on the AST.

Its own module so ``ast_rules.py`` stays small (C-14); it reuses its trees, ``Violation`` and
allowlist. Business code is every module of ``apps/**`` except paths with a ``tests`` or
``migrations`` segment and ``MECHANISM_FILES``, the two modules that implement the guards and need
the internals they guard. The runtime guards of T-TEN-02/03 fail closed on what runs through a
``TenantQuerySet``; these rules catch what skips them:

- **Manager of a tenant model** (``tenant_query_violations``): ``X.objects`` with ``X`` a tenant
  model (the names come from the caller: the real run reads them from Django's registry) must be
  opened by a scope, ``X.objects.<scope>(...)`` (``allowlists.TENANT_SCOPES``).
  ``X.objects.filter``, ``X.objects.all()``, a bare ``X.objects`` and ``getattr(X, "objects")``
  fail. That is also how an unscoped queryset used as a subquery is caught:
  ``__in=X.objects.values("pk")``, ``Subquery(X.objects...)``, ``Exists(X.objects...)``,
  ``Prefetch(..., X.objects...)``.
- **Django's persistence internals** (any receiver): ``_base_manager``, ``_default_manager``,
  ``_meta.base_manager``/``default_manager``/``managers``/``managers_map``, ``save_base``,
  ``_save_table``, ``_do_update``, ``_do_insert``, ``_insert``, ``_batched_insert``, ``_update`` and
  ``_raw_delete``, also through ``getattr``/``attrgetter`` with a literal name. They skip
  ``TenantModel.save()`` or carry no scope.
- **Raw SQL** (any receiver): ``.raw(...)``, ``.extra(...)``, ``.cursor()`` and ``RawSQL``: the SQL
  is written by hand and ignores the organization filter.
- **``refresh_from_db()`` on a re-pointed instance**: in one function (or the module body), a
  ``refresh_from_db``/``arefresh_from_db`` on the same expression whose ``pk``/``id`` was assigned
  (``x.pk = other``, ``setattr(x, "pk", other)``), or on a tenant model built with a key
  (``Widget(pk=other)``, a positional argument too). It reads the row of that ``pk`` through the
  base manager, from any organization. ``x.pk = None`` (Django's copy idiom) is not flagged.
- **``TenantContext(...)``** outside ``TENANT_CONTEXT_BUILDERS`` (design.md §9), aliases included.

A ``self.<name>``/``cls.<name>`` whose ``<name>`` is defined in the same module is the module's own
helper (``def _update(self)`` of a service), not Django's, and is not flagged.

``unscoped_violations``: every ``.unscoped(...)`` call of business code (and ``getattr(x,
"unscoped")``) needs an entry in ``allowlists.UNSCOPED_ALLOWLIST``; the symbol is the whole call, so
the entry pins the model and the ``UnscopedReason``.

``untenanted_models``: every concrete model of ``apps/`` inherits ``TenantModel`` (RN-TEN-01),
except the app or model labels of ``allowlists.TENANT_EXEMPT_MODELS``; an exemption that matches
nothing fails. It reads ``ModelInfo`` built by the caller from Django's registry, so it stays pure.

To justify an exception: an ``AllowEntry`` (path from ``backend/``, the exact ``symbol`` of the
violation, a reason) in ``allowlists.py``; ``apply_allowlist`` fails an entry without a reason or
that matches nothing.

Known gaps, left to the runtime guards and to RLS (ADR-0001, a later spec): a tenant manager reached
through an alias the AST cannot resolve (``M = Widget; M.objects``, ``self.model.objects``,
``apps.get_model(...)``, ``type(obj).objects``; C-01 still flags those in ``services/``); an
unscoped queryset kept in a variable and used later as a subquery (it is flagged where it is built,
not where it is used); a scope applied after a clone (``X.objects.filter(...).for_tenant(ctx)``
fails here although it is scoped at runtime: scope first); names built at runtime
(``getattr(x, name)``, ``vars(M)``, ``__dict__``); a ``pk`` re-pointed in another function, by a
closure, through ``__dict__``, ``copy`` or a helper before ``refresh_from_db``; joins through a
forward FK to another tenant table (``branch__name=...``) and forward FK access (``charge.branch``),
which read by ``pk`` through the base manager until composite FKs (RN-TEN-15) and RLS;
``dataclasses.replace(ctx, ...)`` or ``object.__new__(TenantContext)``; raw SQL through the database
driver imported directly; and ``.pyi`` files.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from tests.architecture.allowlists import AllowEntry
from tests.architecture.ast_rules import (
    ATTRIBUTE_GETTERS,
    META_MANAGER_ATTRS,
    SourceFile,
    SourceTree,
    Violation,
    apply_allowlist,
    call_name,
    iter_sources,
    literal,
    scoped_managers,
)

RULE = "AC-TEN-10"
UNSCOPED_RULE = "AC-TEN-10/unscoped"
MODEL_RULE = "RN-TEN-01"
MECHANISM_FILES = frozenset({"apps/common/tenancy/models.py", "apps/common/tenancy/querysets.py"})
TENANT_CONTEXT_BUILDERS = ("apps/common/tenancy/", "apps/tenancy/api/permissions.py")
PERSISTENCE_INTERNALS = frozenset(
    {
        "_base_manager",
        "_default_manager",
        "save_base",
        "_save_table",
        "_do_update",
        "_do_insert",
        "_insert",
        "_batched_insert",
        "_update",
        "_raw_delete",
    }
)
RAW_SQL_METHODS = frozenset({"raw", "extra", "cursor"})
RAW_SQL_NAMES = frozenset({"RawSQL"})
RESTRICTED_SCOPES = frozenset({"unscoped"})
REFRESH_METHODS = frozenset({"refresh_from_db", "arefresh_from_db"})
ROW_KEYS = frozenset({"pk", "id"})
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

INTERNAL_MSG = "Django persistence internal in business code: it skips the tenant guards"
RAW_SQL_MSG = "raw SQL ignores the organization filter: use a scoped queryset"
MANAGER_MSG = "manager of a tenant model without a scope: open it with X.objects.for_tenant(ctx)"
REFRESH_MSG = "refresh_from_db after re-pointing the pk reads that row from any organization"
CONTEXT_MSG = "TenantContext built outside tenant resolution: take it from the request or task"
UNSCOPED_MSG = "unscoped(reason) outside UNSCOPED_ALLOWLIST"


@dataclass(frozen=True)
class ModelInfo:
    """A concrete model of Django's registry, as ``untenanted_models`` needs it."""

    label: str  # "tenancy.Organization"
    module: str  # "apps.tenancy.models.organization"
    is_tenant: bool  # inherits TenantModel


def is_business(source: SourceFile) -> bool:
    parts = source.module.split(".")
    return (
        parts[0] == "apps"
        and "tests" not in parts
        and "migrations" not in parts
        and source.path not in MECHANISM_FILES
    )


def terminal_name(node: ast.expr) -> str | None:
    """``Widget`` of ``Widget`` and of ``models.Widget``."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def literal_names(call: ast.Call) -> set[str]:
    """Every dotted part of the literal names of ``getattr(x, "a")``/``attrgetter("a.b")``."""
    if call_name(call) not in ATTRIBUTE_GETTERS:
        return set()
    return {part for arg in call.args if (name := literal(arg)) for part in name.split(".")}


def own_helper(node: ast.Attribute, defined: set[str]) -> bool:
    return (
        isinstance(node.value, ast.Name)
        and node.value.id in {"self", "cls"}
        and (node.attr in defined)
    )


def found(source: SourceFile, node: ast.AST, rule: str, symbol: str, msg: str) -> Violation:
    return Violation(source.path, getattr(node, "lineno", 0), rule, symbol, msg)


def raw_access(source: SourceFile, defined: set[str]) -> Iterator[Violation]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Attribute) and not own_helper(node, defined):
            meta = isinstance(node.value, ast.Attribute) and node.value.attr == "_meta"
            if node.attr in PERSISTENCE_INTERNALS or (meta and node.attr in META_MANAGER_ATTRS):
                yield found(source, node, RULE, ast.unparse(node), INTERNAL_MSG)
            elif node.attr in RAW_SQL_NAMES:
                yield found(source, node, RULE, ast.unparse(node), RAW_SQL_MSG)
        elif isinstance(node, ast.Name) and node.id in RAW_SQL_NAMES:
            yield found(source, node, RULE, node.id, RAW_SQL_MSG)
        elif isinstance(node, ast.Call):
            func = node.func
            if literal_names(node) & PERSISTENCE_INTERNALS:
                yield found(source, node, RULE, ast.unparse(node), INTERNAL_MSG)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in RAW_SQL_METHODS
                and not own_helper(func, defined)
            ):
                yield found(source, node, RULE, ast.unparse(func), RAW_SQL_MSG)


def tenant_managers(source: SourceFile, tenant_models: frozenset[str]) -> Iterator[Violation]:
    opened = scoped_managers(source.tree)
    parent = {
        id(child): node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)
    }
    for node in ast.walk(source.tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "objects"
            and terminal_name(node.value) in tenant_models
            and id(node) not in opened
        ):
            outer = parent.get(id(node))
            shown = outer if isinstance(outer, ast.Attribute) and outer.value is node else node
            yield found(source, node, RULE, ast.unparse(shown), MANAGER_MSG)
        elif (
            isinstance(node, ast.Call)
            and "objects" in literal_names(node)
            and node.args
            and terminal_name(node.args[0]) in tenant_models
        ):
            yield found(source, node, RULE, ast.unparse(node), MANAGER_MSG)


def scope_bodies(tree: ast.Module) -> Iterator[list[ast.AST]]:
    """The nodes of the module and of each function, without the functions nested in them."""
    for root in [tree, *(n for n in ast.walk(tree) if isinstance(n, FUNCTION_NODES))]:
        nodes: list[ast.AST] = []
        stack = list(ast.iter_child_nodes(root))
        while stack:
            node = stack.pop()
            nodes.append(node)
            if not isinstance(node, FUNCTION_NODES):
                stack.extend(ast.iter_child_nodes(node))
        yield nodes


def is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def built_with_key(node: ast.expr | None, tenant_models: frozenset[str]) -> bool:
    """``Widget(pk=x)``/``Widget(x)``: a tenant instance pointed at a row it was not read from."""
    return (
        isinstance(node, ast.Call)
        and terminal_name(node.func) in tenant_models
        and (bool(node.args) or any(kw.arg in ROW_KEYS for kw in node.keywords))
    )


def repointed(nodes: list[ast.AST], tenant_models: frozenset[str]) -> set[str]:
    """Expressions (unparsed) whose ``pk``/``id`` this body assigns to something not ``None``."""
    keys: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if (
                        isinstance(item, ast.Attribute)
                        and isinstance(item.ctx, ast.Store)
                        and item.attr in ROW_KEYS
                        and not is_none(node.value)
                    ):
                        keys.add(ast.unparse(item.value))
                if isinstance(target, ast.Name) and built_with_key(node.value, tenant_models):
                    keys.add(target.id)
        elif (
            isinstance(node, ast.Call)
            and call_name(node) == "setattr"
            and len(node.args) == 3
            and literal(node.args[1]) in ROW_KEYS
            and not is_none(node.args[2])
        ):
            keys.add(ast.unparse(node.args[0]))
    return keys


def stale_refreshes(source: SourceFile, tenant_models: frozenset[str]) -> Iterator[Violation]:
    for nodes in scope_bodies(source.tree):
        keys = repointed(nodes, tenant_models)
        for node in nodes:
            func = node.func if isinstance(node, ast.Call) else None
            if not isinstance(func, ast.Attribute) or func.attr not in REFRESH_METHODS:
                continue
            if ast.unparse(func.value) in keys or built_with_key(func.value, tenant_models):
                yield found(source, node, RULE, ast.unparse(func), REFRESH_MSG)


def context_builds(source: SourceFile) -> Iterator[Violation]:
    if any(source.path.startswith(builder) for builder in TENANT_CONTEXT_BUILDERS):
        return
    names = {"TenantContext"}
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names if a.name == "TenantContext"}
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id in names) or (
            isinstance(func, ast.Attribute) and func.attr == "TenantContext"
        ):
            yield found(source, node, RULE, ast.unparse(func), CONTEXT_MSG)


def defined_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def tenant_query_violations(
    trees: Iterable[SourceTree],
    tenant_models: frozenset[str],
    allowlist: Sequence[AllowEntry],
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        if not is_business(source):
            continue
        violations.update(raw_access(source, defined_names(source.tree)))
        violations.update(tenant_managers(source, tenant_models))
        violations.update(stale_refreshes(source, tenant_models))
        violations.update(context_builds(source))
    return apply_allowlist(sorted(violations), allowlist, RULE)


def unscoped_violations(
    trees: Iterable[SourceTree], allowlist: Sequence[AllowEntry]
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        if not is_business(source):
            continue
        defined = defined_names(source.tree)
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            scope_call = (
                isinstance(func, ast.Attribute)
                and func.attr in RESTRICTED_SCOPES
                and not own_helper(func, defined)
            )
            if scope_call or literal_names(node) & RESTRICTED_SCOPES:
                violations.add(found(source, node, UNSCOPED_RULE, ast.unparse(node), UNSCOPED_MSG))
    return apply_allowlist(sorted(violations), allowlist, UNSCOPED_RULE)


def untenanted_models(models: Iterable[ModelInfo], exempt: Mapping[str, str]) -> list[Violation]:
    """Concrete models of ``apps/`` without ``TenantModel`` and not exempted by label or app."""
    business = [m for m in models if m.module.split(".")[0] == "apps"]

    def covers(key: str, model: ModelInfo) -> bool:
        return key in (model.label, model.label.split(".")[0])

    violations = [
        Violation(m.module, 0, MODEL_RULE, m.label, "business model without TenantModel")
        for m in business
        if not m.is_tenant and not any(covers(key, m) for key in exempt)
    ]
    for key, reason in exempt.items():
        if not reason.strip():
            violations.append(Violation(key, 0, MODEL_RULE, key, "exemption without a reason"))
        elif not any(covers(key, m) for m in business):
            violations.append(Violation(key, 0, MODEL_RULE, key, "dead exemption: no model"))
    return sorted(violations)
