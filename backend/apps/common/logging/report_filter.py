"""Error reports without credentials in settings or ``request.META`` (C-06; T-PLT-08 review N-9).

The debug page (``DEBUG=true``, dev only) and any error report render the settings and
``request.META`` through ``DEFAULT_EXCEPTION_REPORTER_FILTER``. Django's filter hides the keys that
look like secrets (``KEY``, ``PASS``, ``TOKEN``...) but not ``CACHES["default"]["LOCATION"]``, which
is ``REDIS_URL`` with its password, nor ``REDIS_URL``/``DATABASE_URL`` themselves, which
``runserver`` copies from the process environment into ``request.META``. This filter hides them,
and any key ending in ``URI`` too (T-PLT-12 review N-5: ``CELERY_RESULT_BACKEND_URI``-style names),
and ``CREDENTIAL``: the BFF sends its own in ``X-Hub-Bff-Credential`` (``request.META``, SPEC-01).

Kept apart from ``setup.py``: importing ``django.views.debug`` there would load the template engine
in every process that configures logging (gunicorn's master, Celery), with settings or not.
"""

from __future__ import annotations

import re

from django.views.debug import SafeExceptionReporterFilter

# Django's list plus cache locations, DSNs and any key ending in URL or URI (REDIS_URL,
# DATABASE_URL, CELERY_BROKER_URL, *_URI): any of them may embed user:password. CREDENTIAL:
# HTTP_X_HUB_BFF_CREDENTIAL and the setting it is compared with.
_HIDDEN = SafeExceptionReporterFilter.hidden_settings.pattern + "|LOCATION|DSN|URL$|URI$|CREDENTIAL"


class CredentialSafeReporterFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(_HIDDEN, flags=re.IGNORECASE)
