"""Synthetic Django apps of the migration checks (design.md §3.2.7).

Installed only by ``tests.migrations.settings_synthetic``, which the tests load in a subprocess:
never by the real settings, so ``makemigrations --check`` on the project does not see them.
"""
