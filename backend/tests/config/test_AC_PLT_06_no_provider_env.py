"""AC-PLT-06 (RN-PLT-04, C-06, C-09): the Hub never reads provider credentials from the environment.

Two checks over the code of ``config/`` and ``apps/`` (design.md §3.2.2):

* AST: no environment read outside ``config/settings/env.py`` (``os.environ``/``environb``,
  ``os.getenv``/``getenvb``/``putenv``/``unsetenv``, ``from os import environ``, an aliased ``os``,
  and the env-loading libraries ``pydantic_settings``, ``dotenv``, ``environ``, ``decouple``,
  ``environs``). The one exception is Django's bootstrap in ``config/wsgi.py``/``config/celery.py``:
  ``os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)``.
* No variable the settings read and no settings name matches the provider patterns
  ``^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_`` (any case), nor equals a key of
  ``spikes/env.example`` (T-PLT-39, Q-048).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from config.settings.env import PlatformEnv
from tests.config._env_example import spike_vars

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("config", "apps")
ENV_PY = "config/settings/env.py"
BOOTSTRAP_FILES = frozenset({"config/wsgi.py", "config/celery.py"})

OS_ENV_NAMES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"})
ENV_LIBRARIES = frozenset({"pydantic_settings", "dotenv", "environ", "decouple", "environs"})
PROVIDER_PATTERN = re.compile(r"^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_", re.IGNORECASE)


def _is_bootstrap(node: ast.Attribute, parents: dict[ast.AST, ast.AST], relative: str) -> bool:
    """``os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)`` in a bootstrap file."""
    method = parents.get(node)
    call = parents.get(method) if method is not None else None
    return (
        relative in BOOTSTRAP_FILES
        and node.attr == "environ"
        and isinstance(method, ast.Attribute)
        and method.attr == "setdefault"
        and isinstance(call, ast.Call)
        and call.func is method
        and bool(call.args)
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "DJANGO_SETTINGS_MODULE"
    )


def env_reads(source: str, relative: str) -> list[str]:
    """Every environment access of ``source`` (``relative`` is its path from ``backend/``)."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    os_names = {"os"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ENV_LIBRARIES:
                    found.append(f"{relative}:{node.lineno}: import {alias.name}")
                if alias.name == "os":
                    os_names.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {alias.name for alias in node.names}
            if module.split(".")[0] in ENV_LIBRARIES:
                found.append(f"{relative}:{node.lineno}: from {module} import")
            elif module == "os" and names & (OS_ENV_NAMES | {"*"}):
                found.append(f"{relative}:{node.lineno}: from os import {sorted(names)}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in os_names
            and node.attr in OS_ENV_NAMES
            and not _is_bootstrap(node, parents, relative)
        ):
            found.append(f"{relative}:{node.lineno}: os.{node.attr}")
    return found


def scanned_files() -> list[Path]:
    return sorted(path for name in SCANNED_DIRS for path in (BACKEND_DIR / name).rglob("*.py"))


def test_AC_PLT_06_env_is_read_only_in_env_py() -> None:
    files = scanned_files()
    assert BACKEND_DIR / ENV_PY in files
    assert BACKEND_DIR / "config/wsgi.py" in files
    found = []
    for path in files:
        relative = path.relative_to(BACKEND_DIR).as_posix()
        if relative != ENV_PY:
            found += env_reads(path.read_text(encoding="utf-8"), relative)
    assert found == []


# (source, file, expected number of findings): the scanner sees each form and only the exception.
SCANNER_CASES = (
    ("import os\nos.environ['X']", "apps/a.py", 1),
    ("import os\nos.getenv('X')", "apps/a.py", 1),
    ("import os as o\no.environ.get('X')", "apps/a.py", 1),
    ("import os\ndef f():\n    os.putenv('X', 'y')", "apps/a.py", 1),
    ("from os import environ", "apps/a.py", 1),
    ("from os import getenv as g", "apps/a.py", 1),
    ("from os import *", "apps/a.py", 1),
    ("import dotenv", "apps/a.py", 1),
    ("from pydantic_settings import BaseSettings", "apps/a.py", 1),
    ("from environ import Env", "config/a.py", 1),
    ("import os\nos.environ.setdefault('DJANGO_SETTINGS_MODULE', 'x')", "apps/a.py", 1),
    ("import os\nos.environ.setdefault('MP_ACCESS_TOKEN', 'x')", "config/wsgi.py", 1),
    ("import os\nos.environ.setdefault('DJANGO_SETTINGS_MODULE', 'x')", "config/wsgi.py", 0),
    ("import os\nos.environ.setdefault('DJANGO_SETTINGS_MODULE', 'x')", "config/celery.py", 0),
    ("import os\nos.path.join('a', 'b')\nfrom os import path", "apps/a.py", 0),
)


@pytest.mark.parametrize(("source", "relative", "expected"), SCANNER_CASES)
def test_AC_PLT_06_scanner_finds_every_env_read(source: str, relative: str, expected: int) -> None:
    assert len(env_reads(source, relative)) == expected


def settings_names() -> set[str]:
    """What the settings read or define: the env fields (and aliases) of ``PlatformEnv`` and every
    name assigned in ``config/settings/*.py``, class bodies included (``ProdEnv``'s fields)."""
    names = set(PlatformEnv.model_fields)
    for field in PlatformEnv.model_fields.values():
        aliases = (field.alias, field.validation_alias)
        names |= {alias for alias in aliases if isinstance(alias, str)}
    for path in (BACKEND_DIR / "config" / "settings").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets = node.targets if isinstance(node, ast.Assign) else []
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return names


def test_AC_PLT_06_no_setting_matches_provider_patterns() -> None:
    names = settings_names()
    assert {"DJANGO_SECRET_KEY", "SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "FEATURE_FLAGS"} <= names
    assert sorted(name for name in names if PROVIDER_PATTERN.match(name)) == []


def test_AC_PLT_06_no_setting_matches_spike_keys() -> None:
    spikes = set(spike_vars())
    assert {"MP_ACCESS_TOKEN", "CLOVER_APP_SECRET"} <= spikes
    assert sorted(settings_names() & spikes) == []
    # Not even differing only in case (like the provider patterns above).
    lowered = {name.lower() for name in spikes}
    assert sorted(name for name in settings_names() if name.lower() in lowered) == []


@pytest.mark.parametrize(
    ("name", "matches"),
    [
        ("MP_ACCESS_TOKEN", True),
        ("MERCADOPAGO_CLIENT_SECRET", True),
        ("clover_api_token", True),
        ("PAYWAY_PUBLIC_KEY", True),
        ("DECIDIR_SITE_ID", True),
        ("PRISMA_KEY", True),
        ("MPX_VALUE", False),
        ("APP_VERSION", False),
        ("FEATURE_MP_REFUNDS", False),
    ],
)
def test_AC_PLT_06_provider_pattern(name: str, matches: bool) -> None:
    assert bool(PROVIDER_PATTERN.match(name)) is matches
