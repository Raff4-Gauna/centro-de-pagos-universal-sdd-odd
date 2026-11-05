"""Settings of the migration-check subprocesses (design.md §3.2.7, RN-PLT-10).

``config.settings.test`` plus the synthetic apps of ``tests/migrations/synthetic_apps/``, on the
throwaway database ``hub_synthetic`` of the same server as ``DATABASE_URL`` (the ``synthetic_db``
fixture creates and drops it). Only loaded in a subprocess: the app registry of the pytest process
cannot change once Django is set up.
"""

from __future__ import annotations

from config.settings.test import *  # noqa: F403
from config.settings.test import DATABASES as _TEST_DATABASES
from config.settings.test import INSTALLED_APPS as _TEST_INSTALLED_APPS

SYNTHETIC_DATABASE = "hub_synthetic"
SYNTHETIC_APPS = [
    "tests.migrations.synthetic_apps.missing_migration",
]

INSTALLED_APPS = [*_TEST_INSTALLED_APPS, *SYNTHETIC_APPS]
DATABASES = {"default": {**_TEST_DATABASES["default"], "NAME": SYNTHETIC_DATABASE}}
