"""WSGI entry point (gunicorn, T-PLT-25). Defaults to prod: the strictest settings fail closed."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
