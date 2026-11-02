"""AC-PLT-14 (RN-PLT-09, RF-PLT-09, C-09): only ``providers/<x>/`` imports ``providers.<x>``.

The rule (``ast_rules.adapter_boundary_violations``) runs on the real ``apps/`` and ``config/``,
on the synthetic tree under ``synthetic/`` (which stands for ``apps/``) and on one-off modules
written to ``tmp_path``: every module is parsed as AST, none is imported. The synthetic cases pin
the exact violations, so a rule that flags everything or nothing fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.allowlists import ADAPTER_IMPORT_ALLOWLIST, AllowEntry
from tests.architecture.ast_rules import (
    SourceTree,
    adapter_boundary_violations,
    iter_sources,
    real_trees,
)

BACKEND = Path(__file__).resolve().parents[2]
SYNTHETIC = SourceTree(Path(__file__).resolve().parent / "synthetic", "apps")
MP = "apps.integrations.providers.mercadopago"
SERVICE = "apps/charges/services/evasion.py"


def found(trees: list[SourceTree], path: str) -> list[tuple[int, str]]:
    """(line, imported module) of the C-09 violations in one logical path, sorted."""
    return sorted(
        (v.line, v.symbol)
        for v in adapter_boundary_violations(trees, allowlist=())
        if v.path == path and v.rule == "C-09"
    )


def service_module(tmp_path: Path, source: str) -> list[SourceTree]:
    """``source`` as ``apps/charges/services/evasion.py`` of a throwaway tree."""
    module = tmp_path / "charges" / "services" / "evasion.py"
    module.parent.mkdir(parents=True)
    module.write_text(source, encoding="utf-8")
    return [SourceTree(tmp_path, "apps")]


def test_AC_PLT_14_service_importing_provider_fails() -> None:
    assert found([SYNTHETIC], "apps/charges/services/bad_provider_import.py") == [(7, MP)]


def test_AC_PLT_14_import_inside_same_provider_passes() -> None:
    path = "apps/integrations/providers/mercadopago/ok_internal_import.py"
    assert path in {source.path for source in iter_sources([SYNTHETIC])}
    assert found([SYNTHETIC], path) == []


def test_AC_PLT_14_cross_provider_import_fails() -> None:
    assert found([SYNTHETIC], "apps/integrations/providers/clover/bad_cross_provider.py") == [
        (7, f"{MP}.client"),
        (9, MP),
    ]


@pytest.mark.parametrize(
    ("source", "symbol"),
    [
        # apps.charges.services.evasion: three dots climb to `apps`.
        ("from ...integrations.providers import mercadopago\n", MP),
        ("from ...integrations.providers.mercadopago.client import Client\n", f"{MP}.client"),
        (
            "import importlib\nimportlib.import_module('apps.integrations.providers.mercadopago')",
            MP,
        ),
        (
            "from importlib import import_module\n"
            "import_module('.mercadopago', package='apps.integrations.providers')\n",
            MP,
        ),
        ("__import__('apps.integrations.providers.mercadopago')\n", MP),
        ("__import__('apps.integrations.providers', fromlist=['mercadopago'])\n", MP),
        (
            "from django.utils.module_loading import import_string\n"
            f"import_string('{MP}.client.Client')\n",
            f"{MP}.client.Client",
        ),
        # Above `apps` there is no package: Python refuses it, the rule cannot resolve it.
        ("from .... import mercadopago\n", "...."),
    ],
)
def test_AC_PLT_14_relative_and_importlib_imports_detected(
    tmp_path: Path, source: str, symbol: str
) -> None:
    assert [s for _, s in found(service_module(tmp_path, source), SERVICE)] == [symbol]


@pytest.mark.parametrize(
    ("source", "symbol"),
    [
        ("from apps.integrations.providers import mercadopago\n", MP),
        ("import apps.integrations.providers.mercadopago as mp\n", MP),
        ("from apps.integrations.providers import *\n", "apps.integrations.providers.*"),
        # Reaching the adapter through an imported ancestor package.
        ("from apps.integrations import providers\nproviders.mercadopago.Client\n", f"{MP}.Client"),
        ("import apps.integrations\napps.integrations.providers.mercadopago\n", MP),
    ],
)
def test_AC_PLT_14_import_evasions_detected(tmp_path: Path, source: str, symbol: str) -> None:
    assert [s for _, s in found(service_module(tmp_path, source), SERVICE)] == [symbol]


@pytest.mark.parametrize(
    "source",
    [
        "import apps.integrations.providersx\n",
        "from apps.integrations import core\n",
        "from . import helpers\nfrom ..models import Charge\n",
        "NAME = 'apps.integrations.providers.mercadopago'\n",
    ],
)
def test_AC_PLT_14_non_provider_imports_pass(tmp_path: Path, source: str) -> None:
    assert found(service_module(tmp_path, source), SERVICE) == []


def test_AC_PLT_14_allowlisted_import_passes() -> None:
    path = "apps/charges/services/bad_provider_import.py"
    entry = AllowEntry(path, MP, "synthetic: the registry of SPEC-03 would look like this")
    assert [
        v for v in adapter_boundary_violations([SYNTHETIC], allowlist=(entry,)) if v.path == path
    ] == []


def test_AC_PLT_14_allowlist_entry_without_reason_fails() -> None:
    path = "apps/charges/services/bad_provider_import.py"
    violations = adapter_boundary_violations([SYNTHETIC], allowlist=(AllowEntry(path, MP, " "),))
    assert [(v.path, v.symbol, v.msg) for v in violations if v.path == path] == [
        (path, MP, "allowlist entry without a reason")
    ]


def test_AC_PLT_14_dead_allowlist_entry_fails() -> None:
    entry = AllowEntry("apps/charges/services/gone.py", MP, "code that no longer exists")
    violations = adapter_boundary_violations([SYNTHETIC], allowlist=(entry,))
    assert ("apps/charges/services/gone.py", "dead allowlist entry: matches no violation") in {
        (v.path, v.msg) for v in violations
    }


def test_AC_PLT_14_real_code_has_no_violations() -> None:
    trees = real_trees(BACKEND)
    scanned = {source.path.split("/")[0] for source in iter_sources(trees)}
    assert scanned == {"apps", "config"}, "the rule scanned nothing: it would pass on anything"
    assert adapter_boundary_violations(trees, allowlist=ADAPTER_IMPORT_ALLOWLIST) == []
