"""AC-PLT-15 (RN-PLT-09, RF-PLT-09, C-01): no raw ``Model.objects`` in ``apps/<app>/services/``.

The rule (``ast_rules.raw_manager_violations``) runs on the real ``apps/`` and ``config/``, on the
synthetic tree under ``synthetic/`` (which stands for ``apps/``) and on one-off modules written to
``tmp_path``; nothing is imported. Business reads go through tenant-aware selectors/managers
(SPEC-02 adds them to ``ALLOWED_TENANT_MANAGERS``); until then every raw manager is a violation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.allowlists import ALLOWED_TENANT_MANAGERS, AllowEntry
from tests.architecture.ast_rules import (
    SourceTree,
    iter_sources,
    raw_manager_violations,
    real_trees,
)

BACKEND = Path(__file__).resolve().parents[2]
SYNTHETIC = SourceTree(Path(__file__).resolve().parent / "synthetic", "apps")
BAD_OBJECTS = "apps/charges/services/bad_objects.py"
HEADER = "from apps.charges.models import Charge\n\n"


def module(tmp_path: Path, relative: str, body: str) -> list[tuple[int, str]]:
    """C-01 violations (line, expression) of ``HEADER + body`` written as ``apps/<relative>``."""
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(HEADER + body, encoding="utf-8")
    violations = raw_manager_violations([SourceTree(tmp_path, "apps")], allowlist=())
    return [(v.line, v.symbol) for v in violations if v.rule == "C-01"]


def test_AC_PLT_15_objects_in_services_fails() -> None:
    violations = raw_manager_violations([SYNTHETIC], allowlist=())
    assert [(v.path, v.line, v.symbol) for v in violations] == [(BAD_OBJECTS, 12, "Charge.objects")]


@pytest.mark.parametrize("manager", ["_default_manager", "_base_manager"])
def test_AC_PLT_15_default_and_base_manager_fail(tmp_path: Path, manager: str) -> None:
    body = f"def rows():\n    return Charge.{manager}.all()\n"
    assert module(tmp_path, "charges/services/rows.py", body) == [(4, f"Charge.{manager}")]


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("M = Charge\nM.objects.all()\n", "M.objects"),
        (
            "class Repo:\n    def rows(self):\n        return self.model.objects.all()\n",
            "self.model.objects",
        ),
        ("getattr(Charge, 'objects').all()\n", "getattr(Charge, 'objects')"),
        ("getattr(Charge, '_base_manager')\n", "getattr(Charge, '_base_manager')"),
        (
            "from operator import attrgetter\nattrgetter('objects.all')(Charge)\n",
            "attrgetter('objects.all')",
        ),
        ("Charge._meta.default_manager.all()\n", "Charge._meta.default_manager"),
        ("Charge._meta.base_manager.all()\n", "Charge._meta.base_manager"),
    ],
)
def test_AC_PLT_15_manager_evasions_detected(tmp_path: Path, body: str, symbol: str) -> None:
    assert [s for _, s in module(tmp_path, "charges/services/rows.py", body)] == [symbol]


@pytest.mark.parametrize(
    "relative",
    [
        # `apps/<app>/services.py` instead of a services/ package is still a service.
        "charges/services.py",
        # A services/ nested below the app.
        "integrations/core/services/a.py",
    ],
)
def test_AC_PLT_15_services_module_and_nested_services_are_covered(
    tmp_path: Path, relative: str
) -> None:
    assert module(tmp_path, relative, "Charge.objects.all()\n") == [(3, "Charge.objects")]


@pytest.mark.parametrize(
    ("relative", "body"),
    [
        ("charges/selectors/rows.py", "Charge.objects.all()\n"),
        ("charges/models.py", "Charge.objects.all()\n"),
        # Tests of an app may build fixtures with raw managers, even under a services/ folder.
        ("charges/tests/services/test_rows.py", "Charge.objects.all()\n"),
        ("charges/services/rows.py", "Charge.for_organization(org).all()\n"),
        ("charges/services/rows.py", "getattr(Charge, 'status')\n"),
        # Opened by a tenant scope (AC-TEN-10): the queryset fails closed without it.
        ("charges/services/rows.py", "Charge.objects.for_tenant(ctx).filter(a=1)\n"),
        ("charges/services/rows.py", "Charge.objects.unscoped(reason).count()\n"),
    ],
)
def test_AC_PLT_15_outside_services_or_without_raw_manager_passes(
    tmp_path: Path, relative: str, body: str
) -> None:
    assert module(tmp_path, relative, body) == []


@pytest.mark.parametrize(
    "body",
    [
        # A scope after a clone, a scope name that is not called, a scope on another receiver.
        "Charge.objects.filter(a=1).for_tenant(ctx)\n",
        "Charge.objects.for_tenant\n",
        "Charge.objects.get_queryset().for_tenant(ctx)\n",
    ],
)
def test_AC_PLT_15_only_a_scope_call_opens_the_manager(tmp_path: Path, body: str) -> None:
    assert [s for _, s in module(tmp_path, "charges/services/rows.py", body)] == ["Charge.objects"]


def test_AC_PLT_15_allowlisted_manager_passes_and_dead_entry_fails() -> None:
    entry = AllowEntry(
        BAD_OBJECTS, "Charge.objects", "synthetic: a tenant-aware manager of SPEC-02"
    )
    assert raw_manager_violations([SYNTHETIC], allowlist=(entry,)) == []
    dead = AllowEntry(BAD_OBJECTS, "Refund.objects", "matches nothing")
    assert [v.msg for v in raw_manager_violations([SYNTHETIC], allowlist=(entry, dead))] == [
        "dead allowlist entry: matches no violation"
    ]


def test_AC_PLT_15_real_code_has_no_violations() -> None:
    trees = real_trees(BACKEND)
    assert any(True for _ in iter_sources(trees)), "the rule scanned nothing"
    assert raw_manager_violations(trees, allowlist=ALLOWED_TENANT_MANAGERS) == []
