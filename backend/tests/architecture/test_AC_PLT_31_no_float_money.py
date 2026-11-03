"""AC-PLT-31 (RN-PLT-20, RF-PLT-18, Q-047, C-02): no ``float`` for money outside the adapters.

The rule (``money_rules.float_money_violations``) fails on a ``FloatField`` in ``models.py`` or
``models/`` and on ``float(...)`` in ``domain/``, ``services/``, ``selectors/`` and ``api/`` of
``apps/**``, never under ``apps/integrations/providers/`` (C-02: conversions live in the adapter).
It runs on the real ``apps/`` and ``config/``, on the synthetic tree under ``synthetic/`` (which
stands for ``apps/``) and on one-off modules written to ``tmp_path``; nothing is imported.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.allowlists import FLOAT_ALLOWLIST, AllowEntry
from tests.architecture.ast_rules import SourceTree, iter_sources, real_trees
from tests.architecture.money_rules import float_money_violations

BACKEND = Path(__file__).resolve().parents[2]
SYNTHETIC = SourceTree(Path(__file__).resolve().parent / "synthetic", "apps")
BAD_MODEL = "apps/charges/models.py"
BAD_DOMAIN = "apps/charges/domain/bad_float.py"


def module(tmp_path: Path, relative: str, source: str) -> list[tuple[int, str]]:
    """C-02 violations (line, expression) of ``source`` written as ``apps/<relative>``."""
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source, encoding="utf-8")
    violations = float_money_violations([SourceTree(tmp_path, "apps")], allowlist=())
    return [(v.line, v.symbol) for v in violations if v.rule == "C-02"]


def test_AC_PLT_31_floatfield_in_model_fails() -> None:
    # The whole synthetic tree: exactly the model and the domain module, not the adapter.
    violations = float_money_violations([SYNTHETIC], allowlist=())
    assert [(v.path, v.line, v.symbol) for v in violations] == [
        (BAD_DOMAIN, 11, "float(amount)"),
        (BAD_MODEL, 11, "models.FloatField"),
    ]


@pytest.mark.parametrize(
    ("relative", "source", "symbol"),
    [
        (
            "charges/models.py",
            "from django.db.models import FloatField\nFloatField()\n",
            "FloatField",
        ),
        ("charges/models.py", "from django.db.models import FloatField as F\nF()\n", "F"),
        (
            "charges/models.py",
            "from django.db import models as m\nm.FloatField()\n",
            "m.FloatField",
        ),
        (
            "charges/models.py",
            "import django.db.models\ndjango.db.models.FloatField()\n",
            "django.db.models.FloatField",
        ),
        (
            "charges/models.py",
            "from django.db import models\nclass Amount(models.FloatField): ...\n",
            "models.FloatField",
        ),
        # A models/ package, nested below the app.
        (
            "charges/models/charge.py",
            "from django.db import models\nmodels.FloatField()\n",
            "models.FloatField",
        ),
    ],
)
def test_AC_PLT_31_floatfield_evasions_detected(
    tmp_path: Path, relative: str, source: str, symbol: str
) -> None:
    assert module(tmp_path, relative, source) == [(2, symbol)]


@pytest.mark.parametrize(
    "relative",
    [
        "charges/domain/x.py",
        "charges/services/x.py",
        "charges/selectors/x.py",
        "charges/api/views.py",
        # A layer as a single module, and a layer nested below the app.
        "charges/selectors.py",
        "integrations/core/services/x.py",
    ],
)
def test_AC_PLT_31_float_call_in_domain_services_selectors_api_fails(
    tmp_path: Path, relative: str
) -> None:
    assert module(tmp_path, relative, "def f(x):\n    return float(x)\n") == [(2, "float(x)")]


@pytest.mark.parametrize(
    ("source", "symbol"),
    [
        ("import builtins\nbuiltins.float(x)\n", "builtins.float(x)"),
        ("import builtins as b\nb.float(x)\n", "b.float(x)"),
        ("from builtins import float as f\nf(x)\n", "f(x)"),
        ("total = sum(map(float, xs))\n", "float"),
        ("from collections import defaultdict\ntotals = defaultdict(float)\n", "float"),
        ("to_number = float\n", "float"),
        # The builtins attribute bound without a call.
        ("import builtins\nf = builtins.float\nf(x)\n", "builtins.float"),
        # A comparison only exempts a bare `float` operand, not one nested in it.
        ("ok = sum(map(float, xs)) == 0\n", "float"),
    ],
)
def test_AC_PLT_31_float_evasions_detected(tmp_path: Path, source: str, symbol: str) -> None:
    assert [s for _, s in module(tmp_path, "charges/services/x.py", source)] == [symbol]


@pytest.mark.parametrize(
    ("relative", "source", "symbol"),
    [
        (
            "charges/api/serializers.py",
            "from rest_framework import serializers\nserializers.FloatField()\n",
            "serializers.FloatField",
        ),
        (
            "charges/api/forms.py",
            "from django import forms\nforms.FloatField()\n",
            "forms.FloatField",
        ),
        (
            "charges/services/x.py",
            "from rest_framework.serializers import FloatField\nFloatField()\n",
            "FloatField",
        ),
    ],
)
def test_AC_PLT_31_floatfield_in_money_layers_fails(
    tmp_path: Path, relative: str, source: str, symbol: str
) -> None:
    assert module(tmp_path, relative, source) == [(2, symbol)]


def test_AC_PLT_31_app_tests_are_not_checked(tmp_path: Path) -> None:
    # Tests that check floats are rejected need floats.
    source = "def test_rejects_float():\n    assert float('1.1')\n"
    assert module(tmp_path, "charges/tests/domain/test_x.py", source) == []
    assert module(tmp_path, "charges/tests/models.py", "models.FloatField()\n") == []


@pytest.mark.parametrize(
    "source",
    [
        "from decimal import Decimal\nDecimal('10.50')\n",
        "def check(x):\n    if isinstance(x, float):\n        raise TypeError(x)\n",
        "KIND = 'float'\nrow.float_value\n",
        # `float` as a type: annotations, unions and generics (a real type alias of apps/common).
        "def f(x: float) -> list[float]:\n    y: float = x\n    return [y]\n",
        "JsonValue = str | int | float | None | dict[str, float]\n",
        "type Number = int | float\n",
        # Type comparisons and class patterns.
        "ok = type(x) is float or type(x) != float or float in kinds\n",
        "match x:\n    case float():\n        raise TypeError(x)\n",
    ],
)
def test_AC_PLT_31_decimal_and_type_checks_pass(tmp_path: Path, source: str) -> None:
    assert module(tmp_path, "charges/services/x.py", source) == []


def test_AC_PLT_31_float_inside_providers_passes(tmp_path: Path) -> None:
    ok = "apps/integrations/providers/mercadopago/ok_float.py"
    assert ok in {source.path for source in iter_sources([SYNTHETIC])}
    assert [v for v in float_money_violations([SYNTHETIC], allowlist=()) if v.path == ok] == []
    adapter_model = "integrations/providers/mercadopago/models.py"
    source = "from django.db import models\nmodels.FloatField()\n"
    assert module(tmp_path, adapter_model, source) == []


def test_AC_PLT_31_allowlisted_entry_passes() -> None:
    entry = AllowEntry(BAD_DOMAIN, "float(amount)", "synthetic: a ratio, not money")
    paths = {v.path for v in float_money_violations([SYNTHETIC], allowlist=(entry,))}
    assert BAD_DOMAIN not in paths
    assert BAD_MODEL in paths


def test_AC_PLT_31_entry_without_reason_fails() -> None:
    entry = AllowEntry(BAD_DOMAIN, "float(amount)", "")
    violations = float_money_violations([SYNTHETIC], allowlist=(entry,))
    assert [(v.symbol, v.msg) for v in violations if v.path == BAD_DOMAIN] == [
        ("float(amount)", "allowlist entry without a reason")
    ]


def test_AC_PLT_31_dead_allowlist_entry_fails() -> None:
    entry = AllowEntry(BAD_DOMAIN, "float(other)", "matches nothing")
    violations = float_money_violations([SYNTHETIC], allowlist=(entry,))
    assert ("float(other)", "dead allowlist entry: matches no violation") in {
        (v.symbol, v.msg) for v in violations
    }


def test_AC_PLT_31_real_code_has_no_violations() -> None:
    trees = real_trees(BACKEND)
    assert any(True for _ in iter_sources(trees)), "the rule scanned nothing"
    assert float_money_violations(trees, allowlist=FLOAT_ALLOWLIST) == []
