"""The beat entries of tenancy (design.md §3.6), added to the schedule by ``config/celery.py``.

Imported when the Celery app is built, before Django is set up: only Celery here, no models and no
settings. The task is named by its string, the one ``tasks.py`` registers.

``expire_invitations`` is the fan-out of AC-TEN-37: every hour it lists the ``pending`` invitations
past their expiry and enqueues one per-organization task for each. Correctness does not hang on
it: a request that meets a due one expires it first (lazy expiry, ``services/invitations.py``), so
the hour only bounds how long a due invitation shows ``pending`` in a listing.
"""

from __future__ import annotations

from typing import Any

from celery.schedules import crontab

EXPIRE_TASK = "tenancy.expire_invitations"

# A run still queued when the next one is due is dropped: the expiry is idempotent and the next
# run does the same work, so a stopped worker does not come back to a pile of them.
_EXPIRE_EXPIRES_SECONDS = 55 * 60

SCHEDULE: dict[str, dict[str, Any]] = {
    EXPIRE_TASK: {
        "task": EXPIRE_TASK,
        "schedule": crontab(minute=37),
        "options": {"expires": _EXPIRE_EXPIRES_SECONDS},
    },
}
