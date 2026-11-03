"""Platform tasks. ``diagnostic_ping`` (AC-PLT-11, Q-056): enqueued by ``/api/dev/diagnostic-task/``
(dev and test only) to check, end to end, that a task runs and logs with the ``request_id`` of the
request that enqueued it. No args, no side effects; the return value is never logged.
"""

from __future__ import annotations

from celery import shared_task

from apps.common.logging import get_logger

DIAGNOSTIC_EVENT = "diagnostic.ping"

logger = get_logger(__name__)


@shared_task(name="common.diagnostic_ping", ignore_result=True)
def diagnostic_ping() -> str:
    logger.info(DIAGNOSTIC_EVENT)
    return "pong"
