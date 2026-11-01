"""Settings shared by dev, test and prod (design.md §3.2.2, RF-PLT-03).

Only static values live here. The values that come from the environment are set by each of
``dev``/``test``/``prod``, which validate it with their own env class (``ProdEnv`` in prod is
stricter) through ``config.settings.env.load_env``: this module never reads the environment.

No ``django.contrib.*`` app (D-03): 00 has no users, sessions, admin or static files, so no table
other than ``django_migrations`` exists until module 01 decides auth.
"""

from __future__ import annotations

from pathlib import Path

from apps.common.logging.setup import logging_config

BASE_DIR = Path(__file__).resolve().parents[2]

INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    "apps.common",
]

# RequestId first (T-PLT-12): every log event of the request carries its id. AccessLog (T-PLT-13)
# right after Security, so it times and logs everything the rest of the chain answers.
MIDDLEWARE = [
    "apps.common.middleware.request_id.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.access_log.AccessLogMiddleware",
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

# Logging (design.md §3.2.3, RN-PLT-05): JSON lines on stdout through structlog. Django hands
# LOGGING to LOGGING_CONFIG, which also configures structlog. dev/test/prod rebuild LOGGING with
# the validated LOG_LEVEL; INFO is only the level of a settings module that forgets to.
LOGGING_CONFIG = "apps.common.logging.setup.configure_logging"
LOGGING = logging_config("INFO")
# Error reports and the debug page hide credentials in CACHES/URLs too (C-06, T-PLT-08 review N-9).
DEFAULT_EXCEPTION_REPORTER_FILTER = "apps.common.logging.report_filter.CredentialSafeReporterFilter"
