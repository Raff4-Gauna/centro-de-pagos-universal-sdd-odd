"""Exceptions to the architecture rules (RN-PLT-09; design.md §3.2.6).

Both lists start empty on purpose. An entry names one violation exactly (``path`` is the
"/"-separated path from ``backend/``, ``symbol`` the ``Violation.symbol`` it silences) and says why.
``ast_rules.apply_allowlist`` fails the run for an entry without a reason or that matches no
violation (a dead entry), so an exception can neither hide its motive nor outlive the code it was
written for. This module is data only: it imports nothing from the rules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowEntry:
    path: str
    symbol: str
    reason: str


# C-09: imports of ``apps.integrations.providers.<x>`` from outside ``providers/<x>/``. SPEC-03 adds
# the provider registry here; nothing else is expected.
ADAPTER_IMPORT_ALLOWLIST: tuple[AllowEntry, ...] = ()

# C-01: raw manager access (``.objects``, ``._default_manager``, ``._base_manager``) in
# ``apps/<app>/services/``. SPEC-02 fills it when the tenant-aware managers exist.
# SPEC-01's entities are global (no ``organization_id``): their entries carry that reason.
_GLOBAL_ENTITY = "entidad global, spec §9 (SPEC-01): sin organization_id, se filtra por PK"
_SESSION_LIFECYCLE = "apps/identity/services/session_lifecycle.py"
_REFRESH = "apps/identity/services/refresh.py"
_BY_HASH_OR_PK = (
    "entidad global, spec §9 (SPEC-01): sin organization_id, se filtra por hash + sid o por PK"
)
ALLOWED_TENANT_MANAGERS: tuple[AllowEntry, ...] = (
    AllowEntry(_SESSION_LIFECYCLE, "AuthSession.objects", _GLOBAL_ENTITY),
    AllowEntry(_SESSION_LIFECYCLE, "RefreshToken.objects", _GLOBAL_ENTITY),
    AllowEntry(_REFRESH, "AuthSession.objects", _BY_HASH_OR_PK),
    AllowEntry(_REFRESH, "RefreshToken.objects", _BY_HASH_OR_PK),
    AllowEntry("apps/identity/services/login_start.py", "LoginAttempt.objects", _GLOBAL_ENTITY),
)

# C-02: ``FloatField`` in models and ``float`` in domain/services/selectors/api (money_rules.py).
# Only for a value that is not money (a ratio, a metric) and cannot be a Decimal; never for an
# amount. Provider adapters do not need entries: the rule skips integrations/providers/.
FLOAT_ALLOWLIST: tuple[AllowEntry, ...] = ()
