"""Architecture rules of the constitution checked on the AST (RN-PLT-09; design.md §3.2.6).

Pure: a list of ``SourceTree`` in, a list of ``Violation`` out. Modules are parsed, never imported,
so the synthetic trees of the tests can name packages that do not exist.

- **C-09** (``adapter_boundary_violations``): in ``apps/**`` and ``config/**``, a module that is
  not inside ``apps/integrations/providers/<x>/`` must not reach ``apps.integrations.providers.<x>``
  (one provider importing another included). Resolved: ``import``, ``from`` (relative too),
  ``importlib.import_module``/``__import__``/``import_string`` with literal arguments, and attribute
  chains from an imported ancestor (``providers.mercadopago``).

Known gaps (not cheap on the AST): dynamic imports with computed names and ``__import__`` with
``level``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.architecture.allowlists import AllowEntry

PROVIDERS = "apps.integrations.providers"
DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__", "import_string"})


@dataclass(frozen=True)
class SourceTree:
    """A directory on disk and the dotted package it stands for (``backend/apps`` -> ``apps``)."""

    root: Path
    package: str


@dataclass(frozen=True)
class SourceFile:
    path: str  # "/"-separated, from the import root: "apps/charges/services/x.py"
    module: str
    is_package: bool
    tree: ast.Module


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    symbol: str
    msg: str


def real_trees(backend: Path) -> list[SourceTree]:
    return [SourceTree(backend / "apps", "apps"), SourceTree(backend / "config", "config")]


def iter_sources(trees: Iterable[SourceTree]) -> Iterator[SourceFile]:
    for tree in trees:
        prefix = tree.package.split(".")
        for file in sorted(tree.root.rglob("*.py")):
            relative = file.relative_to(tree.root)
            is_package = relative.name == "__init__.py"
            parts = [*prefix, *relative.with_suffix("").parts]
            yield SourceFile(
                path="/".join([*prefix, *relative.parts]),
                module=".".join(parts[:-1] if is_package else parts),
                is_package=is_package,
                tree=ast.parse(file.read_text(encoding="utf-8"), filename=str(file)),
            )


def apply_allowlist(
    violations: list[Violation], allowlist: Sequence[AllowEntry], rule: str
) -> list[Violation]:
    """Drop the allowlisted violations; an entry without a reason or that matches nothing fails."""

    def matches(entry: AllowEntry, violation: Violation) -> bool:
        return (entry.path, entry.symbol) == (violation.path, violation.symbol)

    kept = [v for v in violations if not any(matches(entry, v) for entry in allowlist)]
    for entry in allowlist:
        if not entry.reason.strip():
            msg = "allowlist entry without a reason"
        elif not any(matches(entry, v) for v in violations):
            msg = "dead allowlist entry: matches no violation"
        else:
            continue
        kept.append(Violation(entry.path, 0, rule, entry.symbol, msg))
    return sorted(kept)


# --- C-09 -----------------------------------------------------------------------------------------


def provider_of(module: str) -> str | None:
    if not module.startswith(f"{PROVIDERS}."):
        return None
    return module[len(PROVIDERS) + 1 :].split(".")[0]


def resolve_relative(source: SourceFile, module: str | None, level: int) -> str | None:
    """Absolute name of ``from <level dots><module> import``; None above the top-level package."""
    package = source.module.split(".") if source.is_package else source.module.split(".")[:-1]
    keep = len(package) - (level - 1)
    if keep <= 0:
        return None
    return ".".join([*package[:keep], *([module] if module else [])])


def literal(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[position] if len(call.args) > position else None


def dynamic_targets(call: ast.Call) -> list[str]:
    """Modules named by a literal ``import_module``/``__import__``/``import_string`` call."""
    function = call_name(call)
    name = literal(argument(call, 0, "dotted_path" if function == "import_string" else "name"))
    if name is None:
        return []
    if name.startswith("."):
        # importlib.import_module(".x", package="a.b"): relative to `package`, one dot = itself.
        package = literal(argument(call, 1, "package"))
        rest = name.lstrip(".")
        keep = len(package.split(".")) - (len(name) - len(rest) - 1) if package else 0
        if package is None or keep <= 0:
            return [name]  # unresolvable relative name: reported as such
        name = ".".join([*package.split(".")[:keep], *([rest] if rest else [])])
    targets = [name]
    fromlist = argument(call, 3, "fromlist") if function == "__import__" else None
    if isinstance(fromlist, ast.List | ast.Tuple):
        targets += [f"{name}.{item}" for item in map(literal, fromlist.elts) if item]
    return targets


def import_targets(source: SourceFile) -> Iterator[tuple[int, str, bool]]:
    """(line, module, resolved) of every import, literal dynamic import and imported-name chain."""
    bindings: dict[str, str] = {}
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, True
                head = alias.name.split(".")[0]
                bindings[alias.asname or head] = alias.name if alias.asname else head
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                resolved = resolve_relative(source, node.module, node.level)
                if resolved is None:
                    yield node.lineno, "." * node.level + base, False
                    continue
                base = resolved
            if provider_of(base) is not None:
                yield node.lineno, base, True
            for alias in node.names:
                if alias.name == "*" and base == PROVIDERS:
                    yield node.lineno, f"{base}.*", True
                elif alias.name != "*":
                    bindings[alias.asname or alias.name] = f"{base}.{alias.name}"
                    if provider_of(base) is None:
                        yield node.lineno, f"{base}.{alias.name}", True
        elif isinstance(node, ast.Call) and call_name(node) in DYNAMIC_IMPORTERS:
            for target in dynamic_targets(node):
                yield node.lineno, target, not target.startswith(".")
    yield from attribute_targets(source.tree, bindings)


def attribute_targets(
    tree: ast.Module, bindings: dict[str, str]
) -> Iterator[tuple[int, str, bool]]:
    """``providers.mercadopago.x`` where ``providers`` was imported from a non-provider module."""
    inner = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in inner:
            continue
        chain: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            chain.insert(0, current.attr)
            current = current.value
        if isinstance(current, ast.Name) and current.id in bindings:
            base = bindings[current.id]
            if provider_of(base) is None:
                yield node.lineno, ".".join([base, *chain]), True


def adapter_boundary_violations(
    trees: Iterable[SourceTree], allowlist: Sequence[AllowEntry]
) -> list[Violation]:
    violations: set[Violation] = set()
    for source in iter_sources(trees):
        own = provider_of(source.module)
        for line, target, resolved in import_targets(source):
            if not resolved:
                msg = "relative import that cannot be resolved inside the tree"
            elif (provider := provider_of(target)) is not None and provider != own:
                msg = f"imports provider {provider!r} outside integrations/providers/{provider}/"
            else:
                continue
            violations.add(Violation(source.path, line, "C-09", target, msg))
    return apply_allowlist(sorted(violations), allowlist, "C-09")
