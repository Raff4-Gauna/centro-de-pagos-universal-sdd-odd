"""Celery tasks of identity (design.md §3.3). ``purge_auth_data`` runs on beat (``beat.py``)."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.identity.beat import PURGE_TASK
from apps.identity.services import purge


@shared_task(name=PURGE_TASK, ignore_result=True)
def purge_auth_data() -> None:
    """The purge at the current time; idempotent, so a repeated or late run does no harm."""
    purge.purge_auth_data(now=timezone.now())
