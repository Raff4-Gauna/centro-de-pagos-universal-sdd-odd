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
_LOGOUT = "apps/identity/services/logout.py"
_BY_HASH_OR_PK = (
    "entidad global, spec §9 (SPEC-01): sin organization_id, se filtra por hash + sid o por PK"
)
ALLOWED_TENANT_MANAGERS: tuple[AllowEntry, ...] = (
    AllowEntry(_SESSION_LIFECYCLE, "AuthSession.objects", _GLOBAL_ENTITY),
    AllowEntry(_SESSION_LIFECYCLE, "RefreshToken.objects", _GLOBAL_ENTITY),
    AllowEntry(_REFRESH, "AuthSession.objects", _BY_HASH_OR_PK),
    AllowEntry(_REFRESH, "RefreshToken.objects", _BY_HASH_OR_PK),
    AllowEntry(_LOGOUT, "AuthSession.objects", _BY_HASH_OR_PK),
    AllowEntry(_LOGOUT, "RefreshToken.objects", _BY_HASH_OR_PK),
    AllowEntry("apps/identity/services/login_start.py", "LoginAttempt.objects", _GLOBAL_ENTITY),
)

# C-02: ``FloatField`` in models and ``float`` in domain/services/selectors/api (money_rules.py).
# Only for a value that is not money (a ratio, a metric) and cannot be a Decimal; never for an
# amount. Provider adapters do not need entries: the rule skips integrations/providers/.
FLOAT_ALLOWLIST: tuple[AllowEntry, ...] = ()

# --- AC-TEN-10 (RN-TEN-02, design.md §3.4 and §9; tenant_rules.py) --------------------------------

# Methods that scope a tenant queryset (``TenantQuerySet``). ``X.objects.<scope>(...)`` is the only
# way into the manager of a tenant model, and C-01 lets it through in services. Scopes that a
# model declares (``Membership.for_user``, ``Invitation.by_token_hash``...) are added with it.
TENANT_SCOPES: frozenset[str] = frozenset({"for_tenant", "unscoped"})

# ``unscoped(reason)`` outside the mechanism: the symbol is the whole call, so an entry pins the
# model and the ``UnscopedReason``. design.md §3.3: ``selectors/resolution.py`` (T-TEN-08) and
# ``services/platform_*.py`` (T-TEN-18) add theirs; none exists yet.
UNSCOPED_ALLOWLIST: tuple[AllowEntry, ...] = ()

# Raw SQL and Django's persistence internals in business code (tenant_rules.raw_access_violations).
_NO_TABLES = "SELECT 1 de /readyz (AC-PLT-02): no lee ninguna tabla"
_THROWAWAY_DB = "herramienta del operador sobre una BD descartable (AC-PLT-17), no es negocio"
_LOGIN_ATTEMPT = (
    "DELETE ... RETURNING de LoginAttempt (entidad global de SPEC-01, sin organization_id): "
    "consume el intento en una sola sentencia"
)
TENANT_QUERY_ALLOWLIST: tuple[AllowEntry, ...] = (
    AllowEntry("apps/common/health/checks.py", "connections['default'].cursor", _NO_TABLES),
    AllowEntry(
        "apps/common/management/commands/check_migrations_roundtrip.py",
        "connection.cursor",
        _THROWAWAY_DB,
    ),
    AllowEntry("apps/identity/services/login_complete.py", "connection.cursor", _LOGIN_ATTEMPT),
)

# Concrete models of ``apps/`` that do not inherit ``TenantModel`` (RN-TEN-01): an app label or a
# model label, with its reason. An entry that matches no model fails. SPEC-10 adds auditoría.
TENANT_EXEMPT_MODELS: dict[str, str] = {
    "identity": (
        "entidades globales de SPEC-01 (spec §9): la persona existe antes que su organización"
    ),
    "tenancy.Organization": (
        "es el tenant: la raíz de RN-TEN-01, con su propio queryset que falla cerrado"
    ),
}
