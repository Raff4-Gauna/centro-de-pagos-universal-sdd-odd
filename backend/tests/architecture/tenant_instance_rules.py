"""AC-TEN-10: the rules of ``tenant_rules`` about instances and contexts, and their AST helpers.

Split from ``tenant_rules.py`` so both stay small (C-14); ``tenant_rules.tenant_query_violations``
runs them. See that module for the scope, the allowlist and the known gaps.

- ``stale_refreshes``: ``refresh_from_db``/``arefresh_from_db`` on an expression whose ``pk``/``id``
  the same function (or the module body) assigned to something not ``None`` (``x.pk = other``,
  ``setattr(x, "pk", other)``), or on a tenant model built with a key (``Widget(pk=other)``, a
  positional argument too). It reads the row of that ``pk`` through the base manager, from any
  organization. ``x.pk = None`` (Django's copy idiom) passes.
- ``context_builds``: outside ``TENANT_CONTEXT_BUILDERS`` (design.md §9), any use of
  ``TenantContext`` as a value: a call, an alias (imported ``as`` or assigned), ``partial(
  TenantContext, ...)``. Types pass: annotations, ``isinstance``, ``case TenantContext():``. Also an
  instance built from its class at runtime, ``type(x)(...)`` and ``x.__class__(...)``, whatever
  ``x`` is: the AST cannot tell a context apart. The same rule keeps two more names in their
  modules (``RESTRICTED_VALUES``, review of PR #117): ``system_context``, which builds a
  ``SystemActor`` context for any organization (only the Celery bases and its own module), and
  ``MembershipMutex``, the proof that a transaction holds the membership lock (only
  ``tenancy/selectors/locks.py``). Not caught: ``dataclasses.replace(mutex, ...)``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from tests.architecture.ast_rules import SourceFile, Violation, call_name, literal
from tests.architecture.money_rules import not_a_value

RULE = "AC-TEN-10"
TENANT_CONTEXT_BUILDERS = ("apps/common/tenancy/", "apps/tenancy/api/permissions.py")
SYSTEM_CONTEXT_CALLERS = ("apps/common/tenancy/celery.py", "apps/common/tenancy/locks.py")
MEMBERSHIP_MUTEX_BUILDERS = ("apps/tenancy/selectors/locks.py",)
REFRESH_METHODS = frozenset({"refresh_from_db", "arefresh_from_db"})
ROW_KEYS = frozenset({"pk", "id"})
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

REFRESH_MSG = "refresh_from_db after re-pointing the pk reads that row from any organization"
CONTEXT_MSG = "TenantContext built outside tenant resolution: take it from the request or task"
SYSTEM_CONTEXT_MSG = "system_context outside the task bases: a process gets it from TenantTask"
MUTEX_MSG = "MembershipMutex built outside selectors/locks.py: take it from lock_membership_mutex"
# A name used as a value (called, aliased, passed) only under these path prefixes, and why not.
RESTRICTED_VALUES: dict[str, tuple[tuple[str, ...], str]] = {
    "TenantContext": (TENANT_CONTEXT_BUILDERS, CONTEXT_MSG),
    "system_context": (SYSTEM_CONTEXT_CALLERS, SYSTEM_CONTEXT_MSG),
    "MembershipMutex": (MEMBERSHIP_MUTEX_BUILDERS, MUTEX_MSG),
}


def found(source: SourceFile, node: ast.AST, rule: str, symbol: str, msg: str) -> Violation:
    return Violation(source.path, getattr(node, "lineno", 0), rule, symbol, msg)


def terminal_name(node: ast.expr) -> str | None:
    """``Widget`` of ``Widget`` and of ``models.Widget``."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def aliases(tree: ast.Module, names: frozenset[str]) -> frozenset[str]:
    """``names`` plus what the module binds to them: ``import X as Y``, ``Y = X``, ``Y = m.X``."""
    found_names = set(names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found_names |= {a.asname for a in node.names if a.name in names and a.asname}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name | ast.Attribute)
            and terminal_name(node.value) in found_names
        ):
            found_names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return frozenset(found_names)


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


def built_from_its_class(node: ast.Call) -> bool:
    """``type(x)(...)`` and ``x.__class__(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "__class__"
    return isinstance(func, ast.Call) and call_name(func) == "type" and len(func.args) == 1


def context_builds(source: SourceFile) -> Iterator[Violation]:
    if not any(source.path.startswith(builder) for builder in TENANT_CONTEXT_BUILDERS):
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Call) and built_from_its_class(node):
                yield found(source, node, RULE, ast.unparse(node.func), CONTEXT_MSG)
    types = not_a_value(source.tree)
    for name, (allowed, msg) in RESTRICTED_VALUES.items():
        if any(source.path.startswith(prefix) for prefix in allowed):
            continue
        names = aliases(source.tree, frozenset({name}))
        for node in ast.walk(source.tree):
            if (
                isinstance(node, ast.Name | ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and (node.id in names if isinstance(node, ast.Name) else node.attr == name)
                and id(node) not in types
            ):
                yield found(source, node, RULE, ast.unparse(node), msg)
