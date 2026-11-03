"""structlog processors of the platform (design.md §3.2.3, RN-PLT-05).

Each one takes and returns the event dict. For a stdlib record, ``ProcessorFormatter`` puts the
``LogRecord`` under ``_record`` while the pre-chain runs (``remove_processors_meta`` drops it before
rendering). The redaction processor of T-PLT-14 joins this module.
"""

from __future__ import annotations

import logging

from structlog.typing import EventDict, WrappedLogger

# Attributes every LogRecord has (plus the ones Formatter.format adds): anything else came in
# through ``extra=``.
_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
# Values rendered as they are. Objects are left out on purpose: Django's loggers attach the
# ``request``, whose repr carries the raw path and query string (RN-PLT-06).
_SCALARS = (str, int, float, bool, type(None))


def add_component(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """``component``: the name of the stdlib logger (``get_logger(__name__)``: the module)."""
    record = event_dict.get("_record")
    name = record.name if isinstance(record, logging.LogRecord) else getattr(logger, "name", None)
    event_dict.setdefault("component", name or "root")
    return event_dict


def add_record_extras(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """The ``extra={...}`` scalars of a stdlib call as fields (e.g. ``health.not_ready``'s
    ``check``/``error_type``). Never overrides a field already set (``level``, ``request_id``)."""
    record = event_dict.get("_record")
    if not isinstance(record, logging.LogRecord) or event_dict.get("_from_structlog"):
        return event_dict
    for key, value in vars(record).items():
        if key in _RECORD_ATTRIBUTES or key.startswith("_") or key in event_dict:
            continue
        if isinstance(value, _SCALARS):
            event_dict[key] = value
    return event_dict
