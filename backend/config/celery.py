"""The Celery app of the project (T-PLT-17, design.md §3.2.3): ``celery -A config worker|beat``.

Every ``CELERY_*`` Django setting configures it (``base.py``; the broker URL comes from
``REDIS_URL`` in dev/test/prod), and tasks are found in each installed app's ``tasks.py``. The
signal handlers that carry the ``request_id`` and log each task are in
``apps/common/celery_signals.py`` (connected by ``CommonConfig.ready``).

Celery sees **only** the ``CELERY_*`` settings (``CelerySettings``). Given the whole Django settings
object, its printable config (``celery report``, ``celery inspect conf``) lists every setting and
masks only keys like ``KEY``/``PASS``/``broker_url``: ``CACHES["default"]["LOCATION"]``
(``REDIS_URL`` with its password) came out in clear (C-06).

Logging is the platform's, not Celery's (RN-PLT-05): connecting ``setup_logging`` tells Celery to
leave the root logger, its level and stdout alone (no text handler, no ``-l`` level, no stdout
redirection), and applies the same ``LOGGING`` as Django and gunicorn. Connected here, at import,
so it is in place for the worker and for beat (which never sends ``worker_init``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from typing import Any

from celery import Celery
from celery.signals import setup_logging

# Like wsgi.py: without an explicit module, the strictest settings (fail closed).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

SETTINGS_PREFIX = "CELERY_"


class CelerySettings(Mapping[str, Any]):
    """The ``CELERY_*`` Django settings, read lazily (settings load after this module)."""

    def _names(self) -> list[str]:
        from django.conf import settings

        return [name for name in dir(settings) if name.startswith(SETTINGS_PREFIX)]

    def __getitem__(self, key: str) -> Any:
        from django.conf import settings

        if not key.startswith(SETTINGS_PREFIX) or not hasattr(settings, key):
            raise KeyError(key)
        return getattr(settings, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._names())

    def __len__(self) -> int:
        return len(self._names())


app = Celery("config")
app.config_from_object(CelerySettings(), namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect(weak=False, dispatch_uid="config.celery.setup_logging")
def configure_process_logging(**kwargs: Any) -> None:
    """The JSON logging of ``settings.LOGGING``; Celery's ``loglevel``/``format`` are ignored."""
    from django.conf import settings

    from apps.common.logging.setup import configure_logging

    configure_logging(settings.LOGGING)
