"""``manage.py lint_migrations [app_label ...]``: static checks on migration files (RN-PLT-10).

Reads the migrations from disk with ``MigrationLoader`` (no database connection) and applies the
rules of ``apps.common.migration_lint.rules`` to each one (names and schema/data apart,
AC-PLT-18; reversibility, AC-PLT-17). Without labels, as CI runs
it (job ``migrations``, step 8), it checks every installed app whose module is under ``apps``;
labels restrict the run to those apps, whatever their package (the synthetic apps of the tests).
Each problem goes to stdout as ``<app_label>.<migration>: <problem>``; any problem exits with 1.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader

from apps.common.migration_lint.rules import is_project_app, migration_problems


def target_labels(labels: list[str]) -> set[str]:
    """The app labels to check: the given ones (each must be installed) or the project's apps."""
    if not labels:
        return {config.label for config in apps.get_app_configs() if is_project_app(config.name)}
    for label in labels:
        try:
            apps.get_app_config(label)
        except LookupError as error:
            raise CommandError(str(error)) from error
    return set(labels)


class Command(BaseCommand):
    help = "Check migration names, schema/data separation and reversibility; exit 1 on a problem."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "app_labels", nargs="*", help="Apps to check (default: every app under apps.*)."
        )

    def handle(self, *args: object, app_labels: list[str], **options: object) -> None:
        targets = target_labels(app_labels)
        loader = MigrationLoader(None, ignore_no_migrations=True)
        keys = sorted(key for key in loader.disk_migrations if key[0] in targets)
        found = 0
        for app_label, name in keys:
            migration = loader.disk_migrations[app_label, name]
            for problem in migration_problems(name, migration.operations):
                self.stdout.write(f"{app_label}.{name}: {problem}")
                found += 1
        summary = f"Checked {len(keys)} migration(s)"
        if found:
            raise CommandError(f"{summary}: {found} migration problem(s)")
        self.stdout.write(f"{summary}: no problems")
