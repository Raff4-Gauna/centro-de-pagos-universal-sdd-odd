"""The beat entries of identity (design.md §3.3), added to the schedule by ``config/celery.py``.

Imported when the Celery app is built, before Django is set up: only Celery here, no models and no
settings. The task is named by its string, the one ``tasks.py`` registers.
"""

from __future__ import annotations

from typing import Any

from celery.schedules import crontab

PURGE_TASK = "identity.purge_auth_data"

# A run still queued when the next one is due is dropped: the purge is idempotent and the next
# run does the same work, so a stopped worker does not come back to a pile of them.
_PURGE_EXPIRES_SECONDS = 55 * 60

SCHEDULE: dict[str, dict[str, Any]] = {
    PURGE_TASK: {
        "task": PURGE_TASK,
        "schedule": crontab(minute=17),
        "options": {"expires": _PURGE_EXPIRES_SECONDS},
    },
}
