"""AC-TEN-10 (RN-TEN-02; design.md §3.4 and §9; ADR-0001) checked on the AST.

Its own modules so ``ast_rules.py`` stays small (C-14): this one, ``tenant_instance_rules.py``
(``refresh_from_db`` and ``TenantContext``) and ``tenant_model_rules.py`` (Django's registry: every
business model is a tenant model and every manager of one fails closed). They reuse the trees,
``Violation`` and allowlist of ``ast_rules``. Business code is every module of ``apps/**`` and
``config/**`` except paths with a ``tests`` or ``migrations`` segment and ``MECHANISM_FILES``, the
two modules that implement the guards and need the internals they guard. The runtime guards of
T-TEN-02/03 fail closed on what runs through a ``TenantQuerySet``; these rules catch what skips
them:

- **Manager of a tenant model** (``tenant_query_violations``): ``X.<manager>`` with ``X`` a tenant
  model (or a name the module binds to one: ``import X as Y``, ``Y = X``) and ``<manager>`` one of
  its managers (both from the registry, ``tenant_model_rules.tenant_names``) must be opened by a
  scope, ``X.objects.<scope>(...)`` (``allowlists.TENANT_SCOPES``, or one of ``X``'s own scopes in
  ``allowlists.MODEL_SCOPES``: ``Widget.objects.for_user`` fails). ``X.objects.filter``, a bare
  ``X.objects``, ``getattr(X, "objects")`` and ``attrgetter("objects")`` fail. So does an unscoped
  subquery: ``__in=X.objects.values("pk")``, ``Subquery``/``Exists``/``Prefetch`` of ``X.objects``.
- **Django's persistence internals** (any receiver): ``_base_manager``, ``_default_manager``,
  ``_meta.base_manager``/``default_manager``/``managers``/``managers_map``, ``save_base``,
  ``_save_table``, ``_do_update``, ``_do_insert``, ``_insert``, ``_batched_insert``, ``_update`` and
  ``_raw_delete``, also through ``getattr``/``attrgetter``/``methodcaller`` with a literal name.
- **Raw SQL and plain querysets** (any receiver): ``.raw(``, ``.extra(``, ``.cursor()``,
  ``.chunked_cursor()``, ``<connection>.connection`` (the driver's own), ``RawSQL``,
  ``RawQuerySet(...)``, ``QuerySet(...)`` (a plain queryset of any model), and SQL templates:
  ``Func(template=...)``/``Aggregate(template=...)`` and a ``Func``/``Aggregate``/``Transform``
  subclass that sets ``template``.
- ``_model_scope`` (the builder of a model's own scope, ``TenantQuerySet``) outside a ``models``
  module: called on a scoped chain it would relabel the scope (``scope_builders``).
- ``refresh_from_db`` after re-pointing the ``pk`` and ``TenantContext`` used as a value outside
  tenant resolution: ``tenant_instance_rules``.

A ``self.<name>``/``cls.<name>`` inside a class that defines ``<name>`` itself is that class's own
method (``def _update(self)`` of a service), not Django's, and is not flagged; ``super().<name>``
always is.

``unscoped_violations``: every ``unscoped`` of business code, called (``qs.unscoped(reason)``) or
not (``f = qs.unscoped``, ``getattr``/``methodcaller("unscoped", ...)``), needs an entry in
``allowlists.UNSCOPED_ALLOWLIST``; the symbol of a call is the whole call, so the entry pins the
model and the ``UnscopedReason``.

To justify an exception: an ``AllowEntry`` (path from ``backend/``, the exact ``symbol``, a reason
and, for raw SQL, ``count``) in ``allowlists.py``; ``apply_allowlist`` fails an entry without a
reason, that matches nothing or that matches another number of occurrences.

Known gaps, left to the runtime guards and to RLS (ADR-0001, a later spec): a tenant manager reached
through an expression (``self.model.objects``, ``apps.get_model(...)``, ``type(obj).objects``; C-01
still flags those in ``services/``) or through a name rebound inside a function; an unscoped
queryset kept in a variable and used later as a subquery (flagged where it is built); a scope after
a clone (``X.objects.filter(...).for_tenant(ctx)`` fails although it is scoped at runtime: scope
first); names built at runtime (``getattr(x, name)``, ``vars(M)``, ``__dict__``); a ``Manager()``
built outside a model; SQL hidden in an expression's ``as_sql`` or in a lookup; a ``pk``
re-pointed in another function, a closure, through ``copy`` or a helper before
``refresh_from_db``; joins and forward FK access to another tenant table (``charge.branch``), which
read by ``pk`` through the base manager until composite FKs (RN-TEN-15) and RLS;
``dataclasses.replace(ctx, ...)``, ``copy.copy(ctx)`` and ``object.__new__(TenantContext)``; the
database driver imported directly; and ``.pyi`` files.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Sequence

from tests.architecture.allowlists import MODEL_SCOPES, TENANT_SCOPES, AllowEntry
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
)
from tests.architecture.tenant_instance_rules import (
    aliases,
    context_builds,
    found,
    stale_refreshes,
    terminal_name,
)

RULE = "AC-TEN-10"
UNSCOPED_RULE = "AC-TEN-10/unscoped"
MECHANISM_FILES = frozenset({"apps/common/tenancy/models.py", "apps/common/tenancy/querysets.py"})
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
RAW_SQL_METHODS = frozenset({"raw", "extra", "cursor", "chunked_cursor"})
RAW_SQL_NAMES = frozenset({"RawSQL"})
PLAIN_QUERYSETS = frozenset({"RawQuerySet", "QuerySet"})
SQL_TEMPLATES = frozenset({"Func", "Aggregate", "Transform"})
CONNECTIONS = frozenset({"connection", "connections"})
RESTRICTED_SCOPES = frozenset({"unscoped"})
GETTERS = ATTRIBUTE_GETTERS | {"methodcaller"}

INTERNAL_MSG = "Django persistence internal in business code: it skips the tenant guards"
RAW_SQL_MSG = "raw SQL or a plain queryset ignores the organization filter: use a scoped queryset"
MANAGER_MSG = "manager of a tenant model without a scope: open it with X.objects.for_tenant(ctx)"
UNSCOPED_MSG = "unscoped(reason) outside UNSCOPED_ALLOWLIST"
SCOPE_BUILDER = "_model_scope"
BUILDER_MSG = "_model_scope outside a models module: declare the scope on the model's queryset"


def is_business(source: SourceFile) -> bool:
    parts = source.module.split(".")
    return (
        parts[0] in {"apps", "config"}
        and "tests" not in parts
        and "migrations" not in parts
        and source.path not in MECHANISM_FILES
    )


def literal_names(call: ast.Call) -> set[str]:
    """Dotted parts of the literal names of ``getattr(x, "a")``, ``attrgetter("a.b")`` and
    ``methodcaller("a", ...)`` (only its first argument: the rest are values)."""
    name = call_name(call)
    if name not in GETTERS:
        return set()
    args = call.args[:1] if name == "methodcaller" else call.args
    return {part for arg in args if (text := literal(arg)) for part in text.split(".")}


def own_methods(tree: ast.Module) -> set[int]:
    """ids of the ``self.x``/``cls.x`` inside a class that defines ``x`` itself."""
    ids: set[int] = set()
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        defined = {
            n.name for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        ids |= {
            id(node)
            for node in ast.walk(cls)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"self", "cls"}
            and node.attr in defined
        }
    return ids


def is_connection(node: ast.expr) -> bool:
    """``connection`` (or ``db.connection``) and ``connections[...]``."""
    if isinstance(node, ast.Subscript):
        node = node.value
    return terminal_name(node) in CONNECTIONS


def sql_template(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        named = terminal_name(node.func) in SQL_TEMPLATES
        return named and any(kw.arg == "template" for kw in node.keywords)
    if isinstance(node, ast.ClassDef):
        bases = {terminal_name(base) for base in node.bases}
        sets = {
            t.id
            for n in node.body
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        return bool(bases & SQL_TEMPLATES) and "template" in sets
    return False


def raw_access(source: SourceFile, own: set[int]) -> Iterator[Violation]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Attribute) and id(node) not in own:
            meta = isinstance(node.value, ast.Attribute) and node.value.attr == "_meta"
            if node.attr in PERSISTENCE_INTERNALS or (meta and node.attr in META_MANAGER_ATTRS):
                yield found(source, node, RULE, ast.unparse(node), INTERNAL_MSG)
            elif node.attr in RAW_SQL_NAMES or (
                node.attr == "connection" and is_connection(node.value)
            ):
                yield found(source, node, RULE, ast.unparse(node), RAW_SQL_MSG)
        elif isinstance(node, ast.Name) and node.id in RAW_SQL_NAMES:
            yield found(source, node, RULE, node.id, RAW_SQL_MSG)
        elif isinstance(node, ast.ClassDef) and sql_template(node):
            yield found(source, node, RULE, node.name, RAW_SQL_MSG)
        elif isinstance(node, ast.Call):
            func = node.func
            if literal_names(node) & PERSISTENCE_INTERNALS:
                yield found(source, node, RULE, ast.unparse(node), INTERNAL_MSG)
            elif (
                (
                    isinstance(func, ast.Attribute)
                    and func.attr in RAW_SQL_METHODS
                    and id(func) not in own
                )
                or terminal_name(func) in PLAIN_QUERYSETS
                or sql_template(node)
            ):
                yield found(source, node, RULE, ast.unparse(func), RAW_SQL_MSG)


def own_scopes(tree: ast.Module) -> dict[str, frozenset[str]]:
    """The names the module binds to each model of ``MODEL_SCOPES``, with that model's scopes."""
    scopes: dict[str, frozenset[str]] = {}
    for label, names in MODEL_SCOPES.items():
        for alias in aliases(tree, frozenset({label.rsplit(".", 1)[1]})):
            scopes[alias] = scopes.get(alias, frozenset()) | names
    return scopes


def opened_managers(tree: ast.Module, managers: frozenset[str]) -> set[int]:
    """ids of the ``X.<manager>`` that a scope call opens: ``X.objects.for_tenant(ctx)``, or
    ``X.objects.<own scope>(...)`` when ``X`` is the model that declares it."""
    declared = own_scopes(tree)
    return {
        id(node.func.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr in managers
        and (
            node.func.attr in TENANT_SCOPES
            or node.func.attr in declared.get(terminal_name(node.func.value.value) or "", ())
        )
    }


def tenant_managers(
    source: SourceFile, tenant_models: frozenset[str], managers: frozenset[str]
) -> Iterator[Violation]:
    models = aliases(source.tree, tenant_models)
    opened = opened_managers(source.tree, managers)
    parent = {
        id(child): node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)
    }
    for node in ast.walk(source.tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in managers
            and terminal_name(node.value) in models
            and id(node) not in opened
        ):
            outer = parent.get(id(node))
            shown = outer if isinstance(outer, ast.Attribute) and outer.value is node else node
            yield found(source, node, RULE, ast.unparse(shown), MANAGER_MSG)
        elif isinstance(node, ast.Call) and literal_names(node) & managers:
            getter = call_name(node) == "getattr"
            if not getter or (node.args and terminal_name(node.args[0]) in models):
                yield found(source, node, RULE, ast.unparse(node), MANAGER_MSG)


def scope_builders(source: SourceFile) -> Iterator[Violation]:
    if "models" in source.module.split("."):
        return
    for node in ast.walk(source.tree):
        if (isinstance(node, ast.Attribute) and node.attr == SCOPE_BUILDER) or (
            isinstance(node, ast.Call) and SCOPE_BUILDER in literal_names(node)
        ):
            yield found(source, node, RULE, ast.unparse(node), BUILDER_MSG)


def tenant_query_violations(
    trees: Iterable[SourceTree],
    tenant_models: frozenset[str],
    allowlist: Sequence[AllowEntry],
    managers: frozenset[str] = frozenset({"objects"}),
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        if not is_business(source):
            continue
        violations.update(raw_access(source, own_methods(source.tree)))
        violations.update(tenant_managers(source, tenant_models, managers))
        violations.update(stale_refreshes(source, tenant_models))
        violations.update(context_builds(source))
        violations.update(scope_builders(source))
    return apply_allowlist(sorted(violations), allowlist, RULE)


def unscoped_violations(
    trees: Iterable[SourceTree], allowlist: Sequence[AllowEntry]
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        if not is_business(source):
            continue
        own = own_methods(source.tree)
        calls = {id(n.func): n for n in ast.walk(source.tree) if isinstance(n, ast.Call)}
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Attribute) and node.attr in RESTRICTED_SCOPES:
                if id(node) in own:
                    continue
                shown = calls.get(id(node), node)
                violations.add(found(source, node, UNSCOPED_RULE, ast.unparse(shown), UNSCOPED_MSG))
            elif isinstance(node, ast.Call) and literal_names(node) & RESTRICTED_SCOPES:
                violations.add(found(source, node, UNSCOPED_RULE, ast.unparse(node), UNSCOPED_MSG))
    return apply_allowlist(sorted(violations), allowlist, UNSCOPED_RULE)
