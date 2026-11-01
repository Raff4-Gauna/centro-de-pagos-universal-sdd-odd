"""Structured logging of the platform (design.md §3.2.3, RN-PLT-05, Q-034, C-16).

``get_logger(__name__)`` in application code; never ``print`` (ruff T20). Libraries and Django keep
using stdlib ``logging``: both end up as one JSON event per line on stdout (``setup.py``). The
request/task context (``request_id``, ``organization_id``) is bound with ``context``.
"""

from __future__ import annotations

import structlog


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """A structlog logger over the stdlib logger ``name``, which becomes the ``component``."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
