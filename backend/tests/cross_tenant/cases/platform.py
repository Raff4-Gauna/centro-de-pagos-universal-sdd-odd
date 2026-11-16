"""SPEC-00's routes: none is tenant-scoped (design.md §3.5, "health, schema").

The probes answer the orchestrator without a user; the ``/api/dev/*`` routes exist only in
``config.urls_dev`` (D-14, Q-056) and touch no business data.
"""

from __future__ import annotations

from tests.cross_tenant.registry import Exemption

_PROBE = "sonda de salud del orquestador: sin usuario ni datos de negocio (SPEC-00)"
_DEV = "solo dev/test (config.urls_dev, D-14): sin datos de negocio"

EXEMPT = (
    Exemption("healthz", _PROBE),
    Exemption("readyz", _PROBE),
    Exemption("api/dev/diagnostic-task/", _DEV),
    Exemption("api/dev/schema/", _DEV),
    Exemption("api/dev/docs/", _DEV),
)
