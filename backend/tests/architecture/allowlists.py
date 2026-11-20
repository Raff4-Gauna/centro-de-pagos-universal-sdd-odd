"""Exceptions to the architecture rules (RN-PLT-09; design.md §3.2.6).

Both lists start empty on purpose. An entry names one violation exactly (``path`` is the
"/"-separated path from ``backend/``, ``symbol`` the ``Violation.symbol`` it silences) and says why.
``ast_rules.apply_allowlist`` fails the run for an entry without a reason or that matches no
violation (a dead entry), so an exception can neither hide its motive nor outlive the code it was
written for. ``count``, when set, is how many times the symbol appears in that file: one more
occurrence (or one less) fails too. This module is data only: it imports nothing from the rules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowEntry:
    path: str
    symbol: str
    reason: str
    count: int | None = None


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
_PURGE = "apps/identity/services/purge.py"
_BY_DEADLINE = "entidad global, spec §9 (SPEC-01): sin organization_id, la purga filtra por plazo"
ALLOWED_TENANT_MANAGERS: tuple[AllowEntry, ...] = (
    AllowEntry(_SESSION_LIFECYCLE, "AuthSession.objects", _GLOBAL_ENTITY),
    AllowEntry(_SESSION_LIFECYCLE, "RefreshToken.objects", _GLOBAL_ENTITY),
    AllowEntry(_REFRESH, "AuthSession.objects", _BY_HASH_OR_PK),
    AllowEntry(_REFRESH, "RefreshToken.objects", _BY_HASH_OR_PK),
    AllowEntry(_LOGOUT, "AuthSession.objects", _BY_HASH_OR_PK),
    AllowEntry(_LOGOUT, "RefreshToken.objects", _BY_HASH_OR_PK),
    AllowEntry("apps/identity/services/login_start.py", "LoginAttempt.objects", _GLOBAL_ENTITY),
    AllowEntry(_PURGE, "AuthSession.objects", _BY_DEADLINE),
    AllowEntry(_PURGE, "RefreshToken.objects", _BY_DEADLINE),
    AllowEntry(_PURGE, "LoginAttempt.objects", _BY_DEADLINE),
    AllowEntry(
        "apps/tenancy/services/invitation_accept.py",
        "Invitation.objects",
        "Invitation.objects.for_session_accept(id) (design.md §3.4, §4.4): el primer paso de "
        "aceptar desde la sesión lee la fila por id sin lock; el scope lo restringe "
        "RESTRICTED_SCOPE_ALLOWLIST y el resto del archivo usa for_tenant",
        count=1,
    ),
)

# C-02: ``FloatField`` in models and ``float`` in domain/services/selectors/api (money_rules.py).
# Only for a value that is not money (a ratio, a metric) and cannot be a Decimal; never for an
# amount. Provider adapters do not need entries: the rule skips integrations/providers/.
FLOAT_ALLOWLIST: tuple[AllowEntry, ...] = ()

# --- AC-TEN-10 (RN-TEN-02, design.md §3.4 and §9; tenant_rules.py) --------------------------------

# Methods that scope a tenant queryset (``TenantQuerySet``). ``X.objects.<scope>(...)`` is the only
# way into the manager of a tenant model, and C-01 lets it through in services.
TENANT_SCOPES: frozenset[str] = frozenset({"for_tenant", "unscoped"})

# Scopes that one model declares on its own queryset (design.md §3.4): they open the manager of
# that model only, by model label. ``Invitation.by_token_hash`` came with accepting by token
# (T-TEN-15); ``pending_for_email`` with "my invitations" and ``for_session_accept`` with accepting
# from the session (T-TEN-16). The latter is restricted by file too (``RESTRICTED_SCOPES``).
MODEL_SCOPES: dict[str, frozenset[str]] = {
    "tenancy.Invitation": frozenset({"by_token_hash", "for_session_accept", "pending_for_email"}),
    "tenancy.Membership": frozenset({"for_user"}),
}

# ``unscoped(reason)`` outside the mechanism: the symbol is the whole call, so an entry pins the
# model and the ``UnscopedReason``. design.md §3.3: ``selectors/resolution.py`` (T-TEN-08) and
# ``services/platform_*.py`` (T-TEN-18) add theirs.
UNSCOPED_ALLOWLIST: tuple[AllowEntry, ...] = (
    AllowEntry(
        "apps/tenancy/selectors/resolution.py",
        "Membership.objects.unscoped(UnscopedReason.TENANT_RESOLUTION)",
        "resolución del tenant (design.md §3.5): todavía no hay TenantContext; la consulta filtra "
        "por user_id y organization_id del header, membership activa (RN-TEN-03/06)",
        count=1,
    ),
    AllowEntry(
        "apps/tenancy/services/platform_org.py",
        "Organization.objects.unscoped(UnscopedReason.PLATFORM_COMMAND)",
        "comando del operador tenancy_create_org (design.md §4.5, T-TEN-18): busca la "
        "organización por platform_creation_key (Q-123) y la crea; todavía no hay organización "
        "ni TenantContext",
        count=1,
    ),
)

# Model scopes allowed per file, not only per model (``tenant_rules.restricted_scope_violations``):
# every use in business code, called or not, needs an entry; the symbol is the receiver and the
# scope (``Invitation.objects.for_session_accept``), so the entry pins the model too. Note of
# T-TEN-04 (review of PR #104): a scope that reads any organization's row by id has one service.
RESTRICTED_SCOPES: frozenset[str] = frozenset({"for_session_accept"})
RESTRICTED_SCOPE_ALLOWLIST: tuple[AllowEntry, ...] = (
    AllowEntry(
        "apps/tenancy/services/invitation_accept.py",
        "Invitation.objects.for_session_accept",
        "aceptar desde la sesión (design.md §3.4, §4.4): lee la invitación por id, de cualquier "
        "organización, sin transacción ni lock; el servicio compara el email antes de responder y "
        "otro email o un id inexistente dan el mismo not_found",
        count=1,
    ),
)

# Raw SQL, Django's persistence internals and the restricted names of ``tenant_instance_rules``
# (``system_context``) in business code (tenant_rules.tenant_query_violations).
# ``count``: one more occurrence in the same file fails, so a second cursor needs its own review.
_NO_TABLES = "SELECT 1 de /readyz (AC-PLT-02): no lee ninguna tabla"
_THROWAWAY_DB = "herramienta del operador sobre una BD descartable (AC-PLT-17), no es negocio"
_LOGIN_ATTEMPT = (
    "DELETE ... RETURNING de LoginAttempt (entidad global de SPEC-01, sin organization_id): "
    "consume el intento en una sola sentencia"
)
TENANT_QUERY_ALLOWLIST: tuple[AllowEntry, ...] = (
    AllowEntry(
        "apps/common/health/checks.py", "connections['default'].cursor", _NO_TABLES, count=1
    ),
    AllowEntry(
        "apps/common/management/commands/check_migrations_roundtrip.py",
        "connection.cursor",
        _THROWAWAY_DB,
        count=1,
    ),
    AllowEntry(
        "apps/identity/services/login_complete.py", "connection.cursor", _LOGIN_ATTEMPT, count=1
    ),
    AllowEntry(
        "apps/common/tenancy/locks.py",
        "connection.cursor",
        "estado de la organización por id (design.md §3.1, §3.7): SELECT status ... FOR KEY SHARE "
        "y lock_timeout; common no importa Organization y su manager exige un TenantContext",
        count=1,
    ),
    AllowEntry(
        "apps/tenancy/services/invitation_accept.py",
        "system_context",
        "aceptar una invitación (design.md §4.4): la persona todavía no tiene membership, así que "
        "no hay UserActor; el scope es la organización de la invitación, con "
        "SystemReason.INVITATION_ACCEPT, y el servicio chequea la suspensión él mismo",
        count=1,
    ),
    AllowEntry(
        "apps/tenancy/services/invitation_port.py",
        "system_context",
        "puerto de invitaciones de SPEC-01 (design.md §4.4, T-TEN-17): el primer login acepta "
        "invitaciones de organizaciones donde la persona no tiene membership; mismo "
        "SystemReason.INVITATION_ACCEPT, relee la suspensión bajo el mutex y decide con "
        "accept_locked, como los otros caminos de aceptación",
        count=1,
    ),
    AllowEntry(
        "apps/tenancy/services/platform_org.py",
        "system_context",
        "comando del operador tenancy_create_org (design.md §4.5, T-TEN-18): la organización "
        "recién creada (o la de la clave repetida) no tiene ningún miembro, así que no hay "
        "UserActor; tenant_scope(system_context(org, SystemReason.PLATFORM_COMMAND)), como "
        "dice el diseño, y los eventos nombran al operador como actor",
        count=1,
    ),
)

# Concrete models of ``apps/`` that are not tenant models (RN-TEN-01; ``TenantModel`` subclasses
# and ``settings.TENANT_MODEL`` are): an app label or a model label, with its reason. An entry that
# matches no model fails. SPEC-10 adds auditoría.
# ``identity`` is exempted as an app (design.md §9); test_tenant_models.py pins its models, so a new
# one has to be looked at here.
TENANT_EXEMPT_MODELS: dict[str, str] = {
    "identity": (
        "entidades globales de SPEC-01 (spec §9): la persona existe antes que su organización"
    ),
}
