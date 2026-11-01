"""Settings shared by dev, test and prod (design.md §3.2.2, RF-PLT-03).

Only static values live here. The values that come from the environment are set by each of
``dev``/``test``/``prod``, which validate it with their own env class (``ProdEnv`` in prod is
stricter) through ``config.settings.env.load_env``: this module never reads the environment.

No ``django.contrib.*`` app (D-03): 00 has no users, sessions, admin or static files, so no table
other than ``django_migrations`` exists until module 01 decides auth.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    "apps.common",
]

# RequestId (T-PLT-12) goes first and AccessLog (T-PLT-13) after Security when they exist.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

WSGI_APPLICATION = "config.wsgi.application"

# Q-046: stored in UTC, shown in Buenos Aires time by default; per-branch time zone comes with 02.
USE_TZ = True
TIME_ZONE = "America/Argentina/Buenos_Aires"
LANGUAGE_CODE = "es-ar"
USE_I18N = True

# Cache keys of every environment share this prefix (Redis is also Celery's broker).
CACHE_KEY_PREFIX = "hub"
