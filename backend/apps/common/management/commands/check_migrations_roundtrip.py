"""``manage.py check_migrations_roundtrip --allow-data-loss [app_label ...]``: apply -> revert ->
reapply (C-17).

On the database of the settings, which must be throwaway (CI: the fresh PostgreSQL service of
job ``migrations``, step 8; design.md §3.2.7 and §10, AC-PLT-17), never the development one:
reverting to ``zero`` drops the tables of the checked apps and their data. Hence the explicit
``--allow-data-loss``: without it the command exits with 2 before opening any connection.

1. Apply: ``migrate`` (without labels) or ``migrate <app>`` for each given app.
2. Revert: ``migrate <app> zero`` for each checked app, the app whose migrations come last in the
   forward plan first (reverse dependency order); afterwards none of its migrations is applied.
3. Reapply: step 1 again; afterwards every leaf migration of the checked apps is applied.

Without labels the checked apps are the ones under ``apps`` that have migrations (as CI runs it);
labels restrict both the apply and the revert to those apps, so the synthetic apps of the tests
never mix. A migration that cannot be reverted fails with exit 1 naming the step and the app:
``IrreversibleError`` (``reversible is False`` at the top level) or the ``NotImplementedError`` of a
``RunPython``/``RunSQL`` without reverse nested in ``SeparateDatabaseAndState``. The static check of
the same rule is ``lint_migrations``.
"""

from __future__ import annotations

from argparse import ArgumentParser

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from apps.common.management.commands.lint_migrations import target_labels

ALLOW_DATA_LOSS_REQUIRED = (
    "check_migrations_roundtrip reverts migrations to zero and drops their tables and data: run it "
    "only on a throwaway database and pass --allow-data-loss"
)

# What Django raises when a migration cannot be reverted (see the module docstring).
NOT_REVERSIBLE = (IrreversibleError, NotImplementedError)


def revert_order(executor: MigrationExecutor, labels: list[str]) -> list[str]:
    """``labels`` with the app whose last migration comes latest in the forward plan first."""
    graph = executor.loader.graph
    leaves = [node for node in graph.leaf_nodes() if node[0] in labels]
    plan = [migration.app_label for migration, _ in executor.migration_plan(leaves, True)]
    last = {label: max(i for i, app in enumerate(plan) if app == label) for label in labels}
    return sorted(labels, key=lambda label: (-last[label], label))


class Command(BaseCommand):
    help = "Apply, revert to zero and reapply migrations on a throwaway database (C-17)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "app_labels", nargs="*", help="Apps to check (default: every app under apps.*)."
        )
        parser.add_argument(
            "--allow-data-loss",
            action="store_true",
            help="Required: confirm the database is throwaway (reverting drops tables and data).",
        )

    def handle(
        self,
        *args: object,
        app_labels: list[str],
        verbosity: int,
        allow_data_loss: bool,
        **options: object,
    ) -> None:
        # Before anything that connects: the executor already reads the applied migrations.
        if not allow_data_loss:
            raise CommandError(ALLOW_DATA_LOSS_REQUIRED, returncode=2)
        executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        graph = executor.loader.graph
        candidates = target_labels(app_labels)
        checked = sorted(label for label in candidates if label in executor.loader.migrated_apps)
        # None: the whole project (``migrate`` without labels), as CI runs it.
        scope = checked if app_labels else None

        self.apply("apply", scope, verbosity)
        for label in revert_order(executor, checked):
            self.migrate(f"revert {label}", [label, "zero"], verbosity)
            still = sorted(key for key in applied_migrations() if key[0] == label)
            if still:
                raise CommandError(f"revert {label}: still applied: {still}")
        self.apply("reapply", scope, verbosity)

        applied = applied_migrations()
        missing = sorted(
            node for node in graph.leaf_nodes() if node[0] in checked and node not in applied
        )
        if missing:
            raise CommandError(f"reapply: not applied: {missing}")
        names = ", ".join(checked) if checked else "none with migrations"
        self.stdout.write(f"Round trip passed for {len(checked)} app(s): {names}")

    def apply(self, step: str, scope: list[str] | None, verbosity: int) -> None:
        """``migrate`` for the whole project (``scope`` None) or ``migrate <app>`` for each app."""
        for args in [[]] if scope is None else [[label] for label in scope]:
            self.migrate(step, args, verbosity)

    def migrate(self, step: str, args: list[str], verbosity: int) -> None:
        try:
            call_command(
                "migrate",
                *args,
                interactive=False,
                verbosity=verbosity,
                stdout=self.stdout,
                stderr=self.stderr,
            )
        except NOT_REVERSIBLE as error:
            message = str(error) or "operation cannot be reversed"
            raise CommandError(f"{step}: {type(error).__name__}: {message}") from error


def applied_migrations() -> set[tuple[str, str]]:
    return set(MigrationRecorder(connections[DEFAULT_DB_ALIAS]).applied_migrations())
