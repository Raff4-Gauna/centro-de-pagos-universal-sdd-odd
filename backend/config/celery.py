"""The Celery app of the project (T-PLT-17, design.md §3.2.3): ``celery -A config worker|beat``.

Every ``CELERY_*`` Django setting configures it (``base.py``), and tasks are found in each
installed app's ``tasks.py``. The signal handlers that carry the ``request_id`` and log each task
are in ``apps/common/celery_signals.py`` (connected by ``CommonConfig.ready``).

Logging is the platform's, not Celery's (RN-PLT-05): connecting ``setup_logging`` tells Celery to
leave the root logger, its level and stdout alone (no text handler, no ``-l`` level, no stdout
redirection), and applies the same ``LOGGING`` as Django and gunicorn. Connected here, at import,
so it is in place for the worker and for beat (which never sends ``worker_init``).
"""

from __future__ import annotations

import os
from typing import Any

from celery import Celery
from celery.signals import setup_logging

# Like wsgi.py: without an explicit module, the strictest settings (fail closed).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect(weak=False, dispatch_uid="config.celery.setup_logging")
def configure_process_logging(**kwargs: Any) -> None:
    """The JSON logging of ``settings.LOGGING``; Celery's ``loglevel``/``format`` are ignored."""
    from django.conf import settings

    from apps.common.logging.setup import configure_logging

    configure_logging(settings.LOGGING)
