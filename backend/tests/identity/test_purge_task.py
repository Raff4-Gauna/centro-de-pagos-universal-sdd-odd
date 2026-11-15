"""The purge as a Celery task on beat (RF-IDA-10, design.md §3.3): ``tasks.py`` and ``beat.py``.

The app registers its beat entry in ``identity/beat.py`` and ``config/celery.py`` adds it to the
schedule: every hour at minute 17, the task that runs ``services/purge.py`` at the current time.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from celery.schedules import crontab
from django.utils import timezone

from apps.identity import beat
from apps.identity.models import AuthSession, RevokeReason, User
from apps.identity.services.session_lifecycle import open_session, revoke
from apps.identity.tasks import purge_auth_data
from config import celery_app

TASK_NAME = "identity.purge_auth_data"


def test_AC_IDA_38_purge_is_scheduled_every_hour_at_minute_17() -> None:
    entry = celery_app.conf.beat_schedule[TASK_NAME]

    assert entry["task"] == TASK_NAME
    assert entry["schedule"] == crontab(minute=17)
    assert beat.SCHEDULE[TASK_NAME] == entry
    # A run that waited a whole hour in the queue is dropped: the next one does the same work.
    assert 0 < entry["options"]["expires"] <= 3600


def test_AC_IDA_38_purge_task_is_registered_under_its_name() -> None:
    celery_app.loader.import_default_modules()

    # ``shared_task`` hands out a proxy; the app's registry holds the task it stands for.
    assert celery_app.tasks[TASK_NAME].run is purge_auth_data.run
    assert purge_auth_data.__module__ == "apps.identity.tasks"  # what ``autodiscover_tasks`` loads


@pytest.mark.integration
@pytest.mark.django_db
def test_AC_IDA_38_purge_task_purges_at_the_current_time() -> None:
    ana = User.objects.create_user(google_sub="sub-purge-task", email="ana@example.com")
    ended = timezone.now() - timedelta(days=91)
    session = open_session(ana, now=ended - timedelta(days=1)).session
    revoke(session.pk, reason=RevokeReason.LOGOUT, now=ended)
    kept = open_session(ana, now=timezone.now()).session

    purge_auth_data.apply().get()

    assert not AuthSession.objects.filter(pk=session.pk).exists()
    assert AuthSession.objects.filter(pk=kept.pk).exists()
    assert User.objects.filter(pk=ana.pk).exists()
