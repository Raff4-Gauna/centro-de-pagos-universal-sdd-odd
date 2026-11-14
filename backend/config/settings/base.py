"""Settings shared by dev, test and prod (design.md §3.2.2, RF-PLT-03).

Only static values live here. The values that come from the environment are set by each of
``dev``/``test``/``prod``, which validate it with their own env class (``ProdEnv`` in prod is
stricter) through ``config.settings.env.load_env``. The one exception is
``IDENTITY_BFF_CREDENTIALS``, the same in every environment, which ``config.settings.env`` reads for
this module: the module itself never touches the environment.

No ``django.contrib.*`` app (D-03): no admin, static files, Django sessions or ``auth_*`` tables.
The user is ``apps.identity``'s own; ``AbstractBaseUser`` does not need ``django.contrib.auth``
installed (``django/contrib/auth/base_user.py``).
"""

from __future__ import annotations

from pathlib import Path

from apps.common.api.schema import spectacular_settings
from apps.common.logging.setup import logging_config
from config.settings.env import load_bff_credentials

BASE_DIR = Path(__file__).resolve().parents[2]

INSTALLED_APPS = [
    "rest_framework",
    "drf_spectacular",
    "apps.common",
    "apps.identity",
    "apps.tenancy",
]

AUTH_USER_MODEL = "identity.User"
# The tenant: target of the FK of every TenantModel (SPEC-02 design.md §3.1, ADR-0001).
TENANT_MODEL = "tenancy.Organization"

# Ports of apps.identity (design.md §6.4), resolved by ports/registry.py: identity never imports
# tenancy nor audit. Fixed dotted paths, not environment variables; SPEC-02 and SPEC-10 change them.
IDENTITY_INVITATION_PORT = "apps.identity.ports.stubs.NullInvitationPort"
IDENTITY_MEMBERSHIP_SELECTOR = "apps.identity.ports.stubs.EmptyMembershipSelector"
IDENTITY_AUDIT_PORT = "apps.identity.ports.stubs.LogAuditPort"

# Sink of apps.common.audit (SPEC-02 design.md §3.1): a stub until SPEC-10 brings the transactional
# one, which is the production gate of design.md §10. A fixed dotted path, not from the environment.
AUDIT_SINK = "apps.common.audit.sinks.StructlogAuditSink"

# The BFF's credential (ADR-0004 §9), masked because error reports render settings and this name
# does not match their filter (C-06).
IDENTITY_BFF_CREDENTIALS = load_bff_credentials()

# Refreshes per client IP and minute (apps.identity.api.throttles, T-IDA-14): a ceiling for made-up
# session ids, generous so that many tabs or a NAT never meet it. Read on every request.
IDENTITY_REFRESH_IP_RATE = "60/min"

# The fake OIDC provider (IDENTITY_OIDC_PROVIDER=fake, Q-122): off here and in prod.py, the settings
# of prod and staging; only dev.py and test.py turn it on. With it off, apps.identity does not start
# with the fake provider. Its base URL is where the browser and the backend reach /dev-oidc/*.
IDENTITY_FAKE_OIDC_ALLOWED = False
IDENTITY_FAKE_OIDC_BASE_URL = ""

# RequestId first (T-PLT-12): every log event of the request carries its id. AccessLog (T-PLT-13)
# right after Security, so it times and logs everything the rest of the chain answers.
MIDDLEWARE = [
    "apps.common.middleware.request_id.RequestIdMiddleware",
    # Every request starts and ends without a tenant (SPEC-02, design.md §3.1).
    "apps.common.tenancy.middleware.TenantContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.access_log.AccessLogMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

WSGI_APPLICATION = "config.wsgi.application"

# DRF (design.md §3.2.2, §3.2.4): deny by default (SPEC-01, RF-IDA-03). The Hub's access JWT is
# the only authentication, never a Django session, cookie or Basic (ADR-0004); a view that declares
# no permission answers 401 unauthenticated. Open on purpose: /healthz and /readyz (plain Django
# views, outside DRF), the dev-only schema and Swagger UI (drf-spectacular's SERVE_PERMISSIONS,
# AllowAny), the dev-only diagnostic task (anonymous, 00 design §6) and auth/bff/* (BffAPIView,
# its own credential). No anonymous user object (no django.contrib.auth, D-03): request.user is
# None until authenticated. JSON only (no browsable API); every error as application/problem+json
# (T-PLT-15); drf-spectacular's schema (T-PLT-18); one global throttle for anonymous clients
# (T-PLT-16, RN-PLT-19) whose rate the throttle reads at runtime from API_THROTTLE_ANON_RATE, so
# DEFAULT_THROTTLE_RATES stays out. NUM_PROXIES=0 keys it on REMOTE_ADDR (DRF's None would trust
# any X-Forwarded-For); dev/test/prod set both from the environment.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.identity.api.authentication.HubJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.identity.api.authentication.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.common.api.exceptions.problem_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["apps.common.api.throttling.HubAnonRateThrottle"],
    "NUM_PROXIES": 0,
}

# OpenAPI contract (ADR-0005, T-PLT-18): what shapes it lives in apps/common/api/schema.py.
SPECTACULAR_SETTINGS = spectacular_settings()
# Only the dev-only Swagger UI (/api/dev/docs/, config.urls_dev) renders a template:
# drf-spectacular's own, found through APP_DIRS. No context processor: the API answers JSON only.
TEMPLATES = [
    {"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True}
]

# Q-046: stored in UTC, shown in Buenos Aires time by default; per-branch time zone comes with 02.
USE_TZ = True
TIME_ZONE = "America/Argentina/Buenos_Aires"
LANGUAGE_CODE = "es-ar"
USE_I18N = True

# Cache keys of every environment share this prefix (Redis is also Celery's broker). The cache is
# RedisCache on REDIS_URL in dev/prod (the throttle history lives there, T-PLT-16); LocMemCache in
# test, which integration tests replace with the job's Redis.
CACHE_KEY_PREFIX = "hub"

# Logging (design.md §3.2.3, RN-PLT-05): JSON lines on stdout through structlog. Django hands
# LOGGING to LOGGING_CONFIG, which also configures structlog. dev/test/prod rebuild LOGGING with
# the validated LOG_LEVEL; INFO is only the level of a settings module that forgets to.
LOGGING_CONFIG = "apps.common.logging.setup.configure_logging"
LOGGING = logging_config("INFO")
# Error reports and the debug page hide credentials in CACHES/URLs too (C-06, T-PLT-08 review N-9).
DEFAULT_EXCEPTION_REPORTER_FILTER = "apps.common.logging.report_filter.CredentialSafeReporterFilter"

# Celery (T-PLT-17, design.md §3.2.3): config/celery.py reads every CELERY_* setting; the broker URL
# (REDIS_URL) is set by dev/test/prod, which read the environment. The root logger stays the
# platform's (its JSON handler and LOG_LEVEL), and the worker keeps retrying the broker with
# backoff, logging each attempt, instead of exiting (Compose marks it unhealthy).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = None
