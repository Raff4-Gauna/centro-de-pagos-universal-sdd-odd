"""Django project package: settings, URLs, WSGI entry point and the Celery app.

``celery_app`` is loaded with the package, so ``shared_task`` binds to it in every process
(gunicorn, the worker, management commands and tests).
"""

from __future__ import annotations

from config.celery import app as celery_app

__all__ = ("celery_app",)
