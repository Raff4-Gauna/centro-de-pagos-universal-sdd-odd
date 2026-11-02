"""C-02 checked on the AST: no ``float`` for money (RN-PLT-20, Q-047; design.md §3.2.6).

Its own module so ``ast_rules.py`` stays small (C-14); it reuses its trees, ``Violation`` and
allowlist. Nothing under ``apps/integrations/providers/`` is checked: C-02 puts the conversions
(cents, strings, the provider's floats) inside the adapter.

- ``FloatField`` in a ``models.py`` module or a ``models/`` package below ``apps/<app>/``: any
  ``<x>.FloatField`` (``models.``, an alias, ``django.db.models.``, a subclass base) and the bare
  or aliased name imported with ``from django.db.models import FloatField [as F]``.
- ``float`` in ``domain``, ``services``, ``selectors`` or ``api`` (package or single module, nested
  too): ``float(...)``, ``builtins.float(...)`` (``builtins`` aliased too), ``from builtins import
  float as f``, and ``float`` passed or bound as a value (``map(float, xs)``,
  ``defaultdict(float)``, ``to_number = float``). Type checks (``isinstance``/``issubclass``) and
  annotations are not flagged.

Known gaps: float literals and ``/`` on ints, annotations (``-> float``), a float field defined in
another module and used in a model, ``serializers.FloatField``, JSON parsed into floats, and names
built at runtime (``getattr(builtins, "float")``).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Sequence

from tests.architecture.allowlists import AllowEntry
from tests.architecture.ast_rules import (
    PROVIDERS,
    SourceFile,
    SourceTree,
    Violation,
    apply_allowlist,
    iter_sources,
    provider_of,
)

MONEY_LAYERS = frozenset({"domain", "services", "selectors", "api"})
TYPE_CHECKS = frozenset({"isinstance", "issubclass"})


def checked_parts(module: str) -> list[str]:
    """Package path below ``apps.<app>``; empty outside ``apps`` or inside a provider adapter."""
    parts = module.split(".")
    if parts[0] != "apps" or module == PROVIDERS or provider_of(module) is not None:
        return []
    return parts[2:]


def float_field_uses(source: SourceFile) -> list[ast.expr]:
    names = {"FloatField"}
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names if a.name == "FloatField"}
    return [
        node
        for node in ast.walk(source.tree)
        if (isinstance(node, ast.Attribute) and node.attr == "FloatField")
        or (isinstance(node, ast.Name) and node.id in names)
    ]


def not_a_value(tree: ast.Module) -> set[int]:
    """ids of the nodes where ``float`` is a type, not a converter: type checks, annotations,
    unions (``int | float``), generics (``list[float]``) and ``type`` aliases."""
    roots: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in TYPE_CHECKS:
                roots += node.args[1:]
        elif isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None:
            roots.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns:
            roots.append(node.returns)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            roots += [node.left, node.right]
        elif isinstance(node, ast.Subscript):
            roots.append(node.slice)
        elif isinstance(node, ast.TypeAlias):
            roots.append(node.value)
    return {id(inner) for root in roots for inner in ast.walk(root)}


def float_uses(source: SourceFile) -> list[ast.expr]:
    floats, builtins = {"float"}, set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            builtins |= {a.asname or a.name for a in node.names if a.name == "builtins"}
        elif isinstance(node, ast.ImportFrom) and node.module == "builtins":
            floats |= {a.asname or a.name for a in node.names if a.name == "float"}
    calls: list[ast.expr] = []
    callees: set[int] = set()
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        named = isinstance(func, ast.Name) and func.id in floats
        qualified = (
            isinstance(func, ast.Attribute)
            and func.attr == "float"
            and isinstance(func.value, ast.Name)
            and func.value.id in builtins
        )
        if named or qualified:
            calls.append(node)
            callees.add(id(func))
    skip = callees | not_a_value(source.tree)
    values = [
        node
        for node in ast.walk(source.tree)
        if isinstance(node, ast.Name) and node.id in floats and id(node) not in skip
    ]
    return calls + values


def float_money_violations(
    trees: Iterable[SourceTree], allowlist: Sequence[AllowEntry]
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        parts = checked_parts(source.module)
        found: list[tuple[ast.expr, str]] = []
        if "models" in parts:
            found += [
                (node, "FloatField in a model: use DecimalField(12, 2)")
                for node in float_field_uses(source)
            ]
        if MONEY_LAYERS.intersection(parts):
            found += [(node, "float in a money layer: use Decimal") for node in float_uses(source)]
        for node, msg in found:
            violations.add(Violation(source.path, node.lineno, "C-02", ast.unparse(node), msg))
    return apply_allowlist(sorted(violations), allowlist, "C-02")
