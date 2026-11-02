"""C-02 checked on the AST: no ``float`` for money (RN-PLT-20, Q-047; design.md §3.2.6).

Its own module so ``ast_rules.py`` stays small (C-14); it reuses its trees, ``Violation`` and
allowlist. Nothing under ``apps/integrations/providers/`` is checked: C-02 puts the conversions
(cents, strings, the provider's floats) inside the adapter.

Paths with a ``tests`` segment are skipped: tests that check floats are rejected need floats.
Migrations are not parsed: ``makemigrations --check`` (T-PLT-22) ties them to the models.

- ``FloatField`` in a ``models.py`` module or a ``models/`` package below ``apps/<app>/``, and in
  the money layers below (``serializers.FloatField``, ``forms.FloatField`` in ``api/``): any
  ``<x>.FloatField`` (``models.``, an alias, ``django.db.models.``, a subclass base) and the bare
  or aliased name imported with ``from django.db.models import FloatField [as F]``.
- ``float`` in ``domain``, ``services``, ``selectors`` or ``api`` (package or single module, nested
  too): ``float(...)``, ``builtins.float`` called or not (``builtins`` aliased too), ``from builtins
  import float as f``, and ``float`` passed or bound as a value (``map(float, xs)``,
  ``defaultdict(float)``, ``to_number = float``). ``float`` as a type is not flagged: type checks
  (``isinstance``/``issubclass``, ``type(x) is float``, ``float in kinds``), ``case float():``,
  annotations, unions, generics and ``type`` aliases.

Known gaps: float literals (``Decimal(0.21)`` is ruff ``RUF032``) and ``/`` on ints, a float field
defined in another module and used in a model, floats in the JSON that DRF emits
(``COERCE_DECIMAL_TO_STRING=False``, ``coerce_to_string=False``) or parses, names built at runtime
(``getattr(builtins, "float")``), and other uses as a type that are still flagged (``cast(float,
...)``, ``NewType``/``TypeVar``, ``@register(float)``, tuples of types): those go to the allowlist.
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
TYPE_COMPARISONS = (ast.Is, ast.IsNot, ast.Eq, ast.NotEq, ast.In, ast.NotIn)


def checked_parts(module: str) -> list[str]:
    """Package path below ``apps.<app>``; empty outside ``apps``, in an adapter or in tests."""
    parts = module.split(".")
    if parts[0] != "apps" or module == PROVIDERS or provider_of(module) is not None:
        return []
    if "tests" in parts:
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
    unions (``int | float``), generics (``list[float]``), ``type`` aliases, ``type(x) is float``
    (only a bare operand: ``sum(map(float, xs)) == 0`` is still flagged) and ``case float():``."""
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
        elif isinstance(node, ast.Compare) and all(
            isinstance(op, TYPE_COMPARISONS) for op in node.ops
        ):
            operands = [node.left, *node.comparators]
            roots += [o for o in operands if isinstance(o, ast.Name | ast.Attribute)]
        elif isinstance(node, ast.MatchClass):
            roots.append(node.cls)
    return {id(inner) for root in roots for inner in ast.walk(root)}


def float_uses(source: SourceFile) -> list[ast.expr]:
    floats, builtins = {"float"}, set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            builtins |= {a.asname or a.name for a in node.names if a.name == "builtins"}
        elif isinstance(node, ast.ImportFrom) and node.module == "builtins":
            floats |= {a.asname or a.name for a in node.names if a.name == "float"}

    def is_float(node: ast.AST) -> bool:
        """``float`` (or an alias) or ``<builtins alias>.float``, called or not."""
        if isinstance(node, ast.Name):
            return node.id in floats
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "float"
            and isinstance(node.value, ast.Name)
            and node.value.id in builtins
        )

    nodes = list(ast.walk(source.tree))
    calls = [n for n in nodes if isinstance(n, ast.Call) and is_float(n.func)]
    skip = {id(call.func) for call in calls} | not_a_value(source.tree)
    values = [
        n
        for n in nodes
        if isinstance(n, ast.Name | ast.Attribute) and is_float(n) and id(n) not in skip
    ]
    return [*calls, *values]


def float_money_violations(
    trees: Iterable[SourceTree], allowlist: Sequence[AllowEntry]
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        parts = checked_parts(source.module)
        found: list[tuple[ast.expr, str]] = []
        money_layer = bool(MONEY_LAYERS.intersection(parts))
        if "models" in parts or money_layer:
            found += [
                (node, "FloatField for money: use a DecimalField(12, 2)")
                for node in float_field_uses(source)
            ]
        if money_layer:
            found += [(node, "float in a money layer: use Decimal") for node in float_uses(source)]
        for node, msg in found:
            violations.add(Violation(source.path, node.lineno, "C-02", ast.unparse(node), msg))
    return apply_allowlist(sorted(violations), allowlist, "C-02")
