"""Rules of ``lint_migrations`` on one migration (design.md §3.2.7, RN-PLT-10, AC-PLT-18).

- Name: ``AUTO_NAME_PATTERN`` (Django's fallback ``NNNN_auto_<date>``) is rejected; names must
  say what the migration does (08 §5). ``0001_initial`` is accepted.
- Schema and data apart: a ``RunPython`` next to any operation that is not a ``RunPython`` is
  rejected, so data and schema changes can be reverted one without the other. Operations nested
  in ``SeparateDatabaseAndState`` (database and state sides) count as well. Several ``RunPython``
  together are one data migration and pass.

Pure on the migration's name and operations: it never imports, runs nor connects anything.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

from django.db.migrations.operations import RunPython, SeparateDatabaseAndState
from django.db.migrations.operations.base import Operation

# The project's own code: Django, third-party and test apps are never linted by default.
PROJECT_PACKAGE = "apps"

# design.md §3.2.7: ``^\d{4}_auto_``, ASCII digits only.
AUTO_NAME_PATTERN = re.compile(r"^\d{4}_auto_", re.ASCII)

AUTO_NAME = "auto-generated name (NNNN_auto_<date>): rename it to describe the change"
MIXED_RUNPYTHON = (
    "RunPython mixed with other operations: put schema and data changes in separate migrations"
)


def is_project_app(module: str) -> bool:
    """Whether an app's module (``AppConfig.name``) belongs to the project's ``apps`` package."""
    return module == PROJECT_PACKAGE or module.startswith(f"{PROJECT_PACKAGE}.")


def flatten(operations: Sequence[Operation]) -> Iterator[Operation]:
    """Every operation, with ``SeparateDatabaseAndState`` replaced by its nested operations."""
    for operation in operations:
        if isinstance(operation, SeparateDatabaseAndState):
            yield from flatten(operation.database_operations)
            yield from flatten(operation.state_operations)
        else:
            yield operation


def mixes_runpython(operations: Sequence[Operation]) -> bool:
    kinds = {isinstance(operation, RunPython) for operation in flatten(operations)}
    return kinds == {True, False}


def migration_problems(name: str, operations: Sequence[Operation]) -> list[str]:
    """The problems of the migration ``name`` (empty when it passes), in a fixed order."""
    problems: list[str] = []
    if AUTO_NAME_PATTERN.match(name):
        problems.append(AUTO_NAME)
    if mixes_runpython(operations):
        problems.append(MIXED_RUNPYTHON)
    return problems
