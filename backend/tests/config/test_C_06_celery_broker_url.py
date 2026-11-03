"""C-06, AC-PLT-06, AC-PLT-11: Celery's broker is ``REDIS_URL``, read only through ``env.py``.

Each settings module sets ``CELERY_BROKER_URL`` from the validated ``REDIS_URL`` (design.md
§3.2.2: one Redis for broker and cache), so Celery never falls back to reading
``CELERY_BROKER_URL`` from the process environment on its own. The URL carries the Redis password:
the error report (settings section), ``repr(settings)``, Celery's printable config (``celery
inspect conf``/``report``) and its connection URI must not show it. Each start runs in a subprocess
with the sentinel password; the subprocess prints only booleans and renderings, never the value.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

from tests.config.test_C_06_env_secrets import ENV_WITH_SECRETS
from tests.conftest import RunDjango

REDIS_PASSWORD = urlsplit(ENV_WITH_SECRETS["REDIS_URL"]).password or ""

# The report is rendered in a function of its own: the text report lists the local variables of
# each frame, and none of these holds the URL.
PROBE = """
import json, sys
import django
django.setup()
from django.conf import settings
from django.views.debug import ExceptionReporter
from config import celery_app


def render_report():
    try:
        raise RuntimeError("demo")
    except RuntimeError:
        return ExceptionReporter(None, *sys.exc_info()).get_traceback_text()


report = render_report()
sys.stdout.write(json.dumps({
    "from_redis_url": "%s" in settings.CELERY_BROKER_URL,
    "celery_uses_it": celery_app.conf.broker_url == settings.CELERY_BROKER_URL,
    "key_in_report": "CELERY_BROKER_URL" in report,
    "renderings": [
        report,
        repr(settings),
        celery_app.conf.humanize(),
        celery_app.connection_for_write().as_uri(),
    ],
}))
"""


@pytest.mark.parametrize("module", ["dev", "test", "prod"])
def test_C_06_broker_url_comes_from_redis_url_and_never_shows_its_password(
    run_django: RunDjango, module: str
) -> None:
    result = run_django(
        "-c",
        PROBE % REDIS_PASSWORD,
        settings_module=f"config.settings.{module}",
        values=ENV_WITH_SECRETS,
    )
    assert REDIS_PASSWORD.startswith("sentinel")
    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout)
    assert probe["from_redis_url"] is True
    assert probe["celery_uses_it"] is True
    assert probe["key_in_report"] is True  # the settings section was rendered, value hidden
    assert all(probe["renderings"])
    # The hosts and names of ENV_WITH_SECRETS carry "sentinel" too and may show; the password not.
    assert REDIS_PASSWORD not in " ".join(probe["renderings"])
    assert REDIS_PASSWORD not in result.stderr
    assert "sentinel-redis-host" in probe["renderings"][-1]  # the URI was rendered, host and all
