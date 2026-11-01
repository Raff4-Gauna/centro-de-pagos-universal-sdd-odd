"""What every log event of the current request or task carries (Q-034): structlog contextvars.

``merge_contextvars`` (first processor, ``setup.py``) copies these keys into each event, from
structlog and stdlib loggers alike. ``organization_id`` appears only once bound (module 02 binds
it when it resolves the tenant). ``clear()`` ends the context; ``bind_request`` starts an empty one.
"""

from __future__ import annotations

import uuid

from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars


def bind_request(request_id: str) -> None:
    """Start the context of a request: nothing bound by a previous one on this thread survives."""
    clear_contextvars()
    bind_contextvars(request_id=request_id)


def bind_organization(organization_id: str | uuid.UUID) -> None:
    bind_contextvars(organization_id=str(organization_id))


def current_request_id() -> str | None:
    value = get_contextvars().get("request_id")
    return value if isinstance(value, str) else None


def clear() -> None:
    clear_contextvars()
