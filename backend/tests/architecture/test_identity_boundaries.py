"""Boundaries of ``apps.identity`` (design.md §3.1, C-09, ADR-0011), checked on the AST.

``apps.identity`` reaches ``apps.tenancy`` and ``apps.audit`` only through ``ports/registry.py``, by
settings; its ``domain/`` stays pure. Both rules run on the real code and on throwaway modules, so a
rule that flags nothing fails here. They reuse the import resolution of ``ast_rules``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.architecture.ast_rules import (
    SourceFile,
    SourceTree,
    import_targets,
    iter_sources,
    resolve_relative,
)

BACKEND = Path(__file__).resolve().parents[2]
IDENTITY = SourceTree(BACKEND / "apps" / "identity", "apps.identity")
FORBIDDEN_MODULES = ("apps.tenancy", "apps.audit")
IMPURE_PACKAGES = frozenset({"django", "rest_framework", "httpx", "jwt"})


def imported_names(source: SourceFile) -> Iterator[str]:
    """What a module imports: ``ast_rules`` skips ``import *``, which reaches a module anyway."""
    yield from (target for _, target, _ in import_targets(source))
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            module = (
                resolve_relative(source, node.module, node.level) if node.level else node.module
            )
            yield module or "." * node.level


def forbidden_imports(tree: SourceTree) -> set[tuple[str, str]]:
    return {
        (source.path, name)
        for source in iter_sources([tree])
        for name in imported_names(source)
        if any(name == module or name.startswith(f"{module}.") for module in FORBIDDEN_MODULES)
    }


def impure_domain_imports(tree: SourceTree) -> set[tuple[str, str]]:
    return {
        (source.path, name)
        for source in iter_sources([tree])
        if "domain" in source.module.split(".")
        for name in imported_names(source)
        if name.split(".")[0] in IMPURE_PACKAGES
    }


def throwaway(tmp_path: Path, relative: str, source: str) -> SourceTree:
    module = tmp_path / relative
    module.parent.mkdir(parents=True)
    module.write_text(source, encoding="utf-8")
    return SourceTree(tmp_path, "apps.identity")


def test_identity_does_not_import_tenancy_or_audit() -> None:
    assert "apps/identity/ports/registry.py" in {s.path for s in iter_sources([IDENTITY])}
    assert forbidden_imports(IDENTITY) == set()


def test_domain_has_no_django_imports() -> None:
    assert "apps/identity/domain/audit_events.py" in {s.path for s in iter_sources([IDENTITY])}
    assert impure_domain_imports(IDENTITY) == set()


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("import apps.tenancy.models\n", "apps.tenancy.models"),
        ("from apps.tenancy.selectors import invitations\n", "apps.tenancy.selectors.invitations"),
        ("from apps import audit\n", "apps.audit"),
        ("from ...tenancy import services\n", "apps.tenancy.services"),
        ("from apps.tenancy.models import *\n", "apps.tenancy.models"),
        ("def f():\n    import apps.audit.sinks\n", "apps.audit.sinks"),
        (
            "from django.utils.module_loading import import_string\n"
            "import_string('apps.tenancy.services.invitation_port.TenancyInvitationPort')\n",
            "apps.tenancy.services.invitation_port.TenancyInvitationPort",
        ),
    ],
)
def test_identity_boundary_rule_flags_every_import_form(
    tmp_path: Path, source: str, name: str
) -> None:
    tree = throwaway(tmp_path, "services/evasion.py", source)
    assert forbidden_imports(tree) == {("apps/identity/services/evasion.py", name)}


@pytest.mark.parametrize(
    "source",
    ["from apps.common.logging import get_logger\n", "from ..ports import audit\n"],
)
def test_identity_boundary_rule_lets_other_imports_pass(tmp_path: Path, source: str) -> None:
    assert forbidden_imports(throwaway(tmp_path, "services/fine.py", source)) == set()


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("import django\n", "django"),
        ("from django.db import models\n", "django.db.models"),
        ("from rest_framework import serializers\n", "rest_framework.serializers"),
        ("import jwt\n", "jwt"),
        ("def f():\n    import httpx\n", "httpx"),
    ],
)
def test_domain_purity_rule_flags_impure_imports(tmp_path: Path, source: str, name: str) -> None:
    tree = throwaway(tmp_path, "domain/impure.py", source)
    assert impure_domain_imports(tree) == {("apps/identity/domain/impure.py", name)}


def test_domain_purity_rule_is_only_about_domain(tmp_path: Path) -> None:
    tree = throwaway(tmp_path, "services/fine.py", "from django.db import transaction\n")
    assert impure_domain_imports(tree) == set()


# --- The expired-JWT reading is logout's alone (RN-IDA-14, AC-IDA-35; reviewer of T-IDA-16) ------

APPS = SourceTree(BACKEND / "apps", "apps")
IGNORING_EXPIRY = "apps.identity.tokens.access_token.verify_access_token_ignoring_expiry"
IGNORING_EXPIRY_USERS = frozenset({"apps/identity/services/logout.py"})


def ignoring_expiry_imports(tree: SourceTree) -> set[str]:
    """Modules that reach the reading of a JWT without ``exp``: it must never authenticate."""
    return {
        source.path
        for source in iter_sources([tree])
        for name in imported_names(source)
        if name == IGNORING_EXPIRY or name.startswith(f"{IGNORING_EXPIRY}.")
    }


def test_only_logout_reads_a_jwt_ignoring_its_expiry() -> None:
    assert ignoring_expiry_imports(APPS) == IGNORING_EXPIRY_USERS


@pytest.mark.parametrize(
    "source",
    [
        "from apps.identity.tokens.access_token import verify_access_token_ignoring_expiry\n",
        "from ..tokens.access_token import verify_access_token_ignoring_expiry as read\n",
        "from apps.identity.tokens import access_token\n"
        "access_token.verify_access_token_ignoring_expiry('x')\n",
        "import apps.identity.tokens.access_token as at\n"
        "at.verify_access_token_ignoring_expiry('x')\n",
    ],
)
def test_ignoring_expiry_rule_flags_every_import_form(tmp_path: Path, source: str) -> None:
    tree = throwaway(tmp_path, "api/authentication.py", source)
    assert ignoring_expiry_imports(tree) == {"apps/identity/api/authentication.py"}


def test_ignoring_expiry_rule_lets_the_checked_reading_pass(tmp_path: Path) -> None:
    source = "from apps.identity.tokens.access_token import verify_access_token\n"
    assert ignoring_expiry_imports(throwaway(tmp_path, "api/authentication.py", source)) == set()
