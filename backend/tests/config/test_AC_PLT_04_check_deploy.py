"""AC-PLT-04 (RNF-PLT-02): ``prod`` passes ``check --deploy`` and refuses an unsafe environment.

Every start runs in a subprocess (``run_django``) with ``config.settings.prod``. ``check --deploy
--fail-level WARNING`` must exit 0 with only ``security.W021`` silenced (HSTS preload, until there
is a domain: design.md §3.2.2, Q-020). ``DJANGO_DEBUG=true``, a weak ``DJANGO_SECRET_KEY`` or a
``*`` in ``DJANGO_ALLOWED_HOSTS`` (T-PLT-08 review N-10) do not start, and the error names the
variable without its value (C-06): each rejected value is searched in stdout + stderr.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

import pytest

from tests.config.test_AC_PLT_03_missing_required_var import SENTINEL, VALID_PROD_ENV

RunDjango = Callable[..., subprocess.CompletedProcess[str]]

PROD = "config.settings.prod"
DEPLOY_CHECK = ("manage.py", "check", "--deploy", "--fail-level", "WARNING")


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def assert_does_not_start(
    result: subprocess.CompletedProcess[str], variable: str, error_type: str, value: str
) -> None:
    assert result.returncode != 0
    assert "django.core.exceptions.ImproperlyConfigured" in result.stderr
    assert f"- {variable}: {error_type}" in result.stderr
    assert value not in output_of(result)


def test_AC_PLT_04_check_deploy_has_no_warnings(run_django: RunDjango) -> None:
    result = run_django(*DEPLOY_CHECK, settings_module=PROD, values=VALID_PROD_ENV)
    assert result.returncode == 0, output_of(result)
    assert "System check identified no issues (1 silenced)." in result.stdout
    assert SENTINEL not in output_of(result).lower()


def test_AC_PLT_04_debug_true_in_prod_does_not_start(run_django: RunDjango) -> None:
    for value in ("true", "TRUE"):
        values = {**VALID_PROD_ENV, "DJANGO_DEBUG": value}
        result = run_django(*DEPLOY_CHECK, settings_module=PROD, values=values)
        assert_does_not_start(result, "DJANGO_DEBUG", "debug_on_in_prod", "sentinel-not-a-secret")
        assert SENTINEL not in output_of(result).lower()


# (value, error type). Django's own rule (security.W009) is >= 50 characters, >= 5 distinct ones
# and no "django-insecure-" prefix; here "django-insecure" anywhere is rejected (design.md §3.2.2).
WEAK_SECRET_KEYS = (
    ("sentinel-short-key-" * 2, "secret_key_too_short"),
    ("sent" * 15, "secret_key_few_characters"),
    ("django-insecure-" + "sentinel-not-a-secret-" * 2, "secret_key_insecure"),
    ("sentinel-not-a-secret-" * 2 + "django-insecure-key", "secret_key_insecure"),
)


@pytest.mark.parametrize(
    ("value", "error_type"),
    [pytest.param(*case, id=f"{case[1]}-{index}") for index, case in enumerate(WEAK_SECRET_KEYS)],
)
def test_AC_PLT_04_weak_secret_key_in_prod_does_not_start(
    run_django: RunDjango, value: str, error_type: str
) -> None:
    values = {**VALID_PROD_ENV, "DJANGO_SECRET_KEY": value}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert_does_not_start(result, "DJANGO_SECRET_KEY", error_type, value)
    assert "sentsent" not in output_of(result)  # a part of the few-characters key neither
    assert SENTINEL not in output_of(result).lower()


@pytest.mark.parametrize("hosts", ["*", "sentinel-host.example, * "], ids=["alone", "in-list"])
def test_AC_PLT_04_wildcard_allowed_host_in_prod_does_not_start(
    run_django: RunDjango, hosts: str
) -> None:
    values = {**VALID_PROD_ENV, "DJANGO_ALLOWED_HOSTS": hosts}
    result = run_django("manage.py", "check", settings_module=PROD, values=values)
    assert_does_not_start(result, "DJANGO_ALLOWED_HOSTS", "allowed_hosts_wildcard", hosts)
    assert SENTINEL not in output_of(result).lower()


# SecurityMiddleware alone around an empty 200: the redirect and HSTS decisions without touching
# the database (/readyz would). The JSON on stdout is the only output.
READ_SECURITY = """
import json, sys, django
django.setup()
from django.conf import settings
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory
middleware = SecurityMiddleware(lambda request: HttpResponse())
factory = RequestFactory(HTTP_HOST="hub.example")
def answer(path, **extra):
    response = middleware(factory.get(path, **extra))
    hsts = response.get("Strict-Transport-Security")
    return [response.status_code, response.get("Location"), hsts]
paths = ("/healthz", "/readyz", "/healthz/", "/readyzx", "/api/v1/x")
http = {path: answer(path) for path in paths}
https = answer("/api/v1/x", HTTP_X_FORWARDED_PROTO="https")
names = ("X_FRAME_OPTIONS", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_HSTS_PRELOAD",
         "SILENCED_SYSTEM_CHECKS")
sys.stdout.write(json.dumps({"http": http, "https": https,
                             "settings": {name: getattr(settings, name) for name in names}}))
"""


def test_AC_PLT_04_http_redirects_to_https_except_health(run_django: RunDjango) -> None:
    values = {**VALID_PROD_ENV, "DJANGO_ALLOWED_HOSTS": "hub.example"}
    result = run_django("-c", READ_SECURITY, settings_module=PROD, values=values)
    assert result.returncode == 0, result.stderr
    seen = json.loads(result.stdout)
    # Internal healthchecks speak plain HTTP: exempt, matched exactly (no trailing slash).
    assert seen["http"]["/healthz"] == [200, None, None]
    assert seen["http"]["/readyz"] == [200, None, None]
    for path in ("/healthz/", "/readyzx", "/api/v1/x"):
        assert seen["http"][path] == [301, f"https://hub.example{path}", None]
    # Behind the TLS proxy (X-Forwarded-Proto): served, with HSTS for one year and subdomains.
    assert seen["https"] == [200, None, "max-age=31536000; includeSubDomains"]
    assert seen["settings"] == {
        "X_FRAME_OPTIONS": "DENY",
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_HSTS_PRELOAD": False,
        "SILENCED_SYSTEM_CHECKS": ["security.W021"],
    }
