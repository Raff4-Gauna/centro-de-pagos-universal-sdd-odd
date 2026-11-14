---
spec: SPEC-02
actualizado: 2026-11-12
---
# Tareas — Módulo de Organizaciones, Sucursales y Roles (tenancy + RBAC)

Reglas: rebanada vertical · ≤ ~300 líneas de diff · mergeable sola · cita AC · lista archivos esperados · incluye su plan de pruebas.

> Entradas: `spec.sdd.md` **Approved 1.0.2**, `design.md` **Aprobado** (con los ajustes que indica su cabecera),
> `clarifications.md` (incluida "Confirmación (2026-11-06)"), ADR-0001 y ADR-0002 **Aceptados**, `context/08-control-de-versiones-ci-cd.md`.
> **Se cierra junto con SPEC-01 (Q-108):** ninguno de los dos pasa a `Verified` sin el otro. `Invitation` vive acá, y
> acá se implementan los dos puertos que define SPEC-01: `T-TEN-12` (memberships) y `T-TEN-17` (invitaciones). Esta
> lista depende de `T-IDA-01`, `T-IDA-06`, `T-IDA-07`, `T-IDA-13`, `T-IDA-27` y `T-IDA-29`.

## Convenciones de esta lista
- **Tamaño** (líneas de diff, **sin** lockfiles ni los generados `specs/_contracts/openapi.yaml` y
  `frontend/src/types/api.d.ts`): **S** ≤ 100 · **M** ≤ 200 · **L** ≤ 300.
- **Zona roja = reviewer obligatorio.** Todo `backend/apps/tenancy/**` lo es por `.github/zona-roja-paths.txt`.
  `backend/apps/common/{tenancy,authz,audit}/**` no están en esa lista hasta `T-TEN-01`, que los agrega: son roles y
  aislamiento. Las pantallas no son zona roja (la UI no decide permisos), salvo las de invitación.
- **Ninguna tarea toca `.github/workflows/`** (Q-063).
- **DoD de todo endpoint tenant-scoped:** registra su `CrossTenantCase` en `backend/tests/cross_tenant/cases/tenancy.py`
  en el mismo PR; si no, `T-TEN-09` falla. Corre `export_openapi` y `openapi:types` y commitea el resultado (AC-PLT-23).
- **DoD de toda tarea de servicio:** emite sus eventos dentro de la transacción y los registra en `AUDIT_TRIGGERS`.
- **Tests:** `test_AC_TEN_NN_<caso>`; lo que no tiene AC propio se nombra por su RF, RN o Q.
- **C-14:** `design.md §3.2` estima ningún archivo sobre ~250 líneas. Los tests de `T-TEN-06` y `T-TEN-07` se parten
  por tabla, y la suite cross-tenant por módulo (`cases/<app>.py`).

### Estados de una tarea
Los de `specs/00-platform/tasks.md`: ☐ pendiente · 🔄 en curso · 🟡 en revisión · ✅ mergeada (PR **y** SHA) · 🧪 verificada
· ⛔ bloqueada (`Q-xxx`). Camino: `☐ → 🔄 → 🟡 → ✅ → 🧪`. La fila se actualiza en el mismo PR que cambia el estado.

## Ramas, PR y merge
- **Prerrequisito:** esta lista, los diseños y las specs 1.0.1 se mergean a `main` antes de abrir `task/T-TEN-…`.
- Cada tarea en `task/T-TEN-NN-slug` desde `main` actualizado; un PR por tarea; merge squash con
  `--match-head-commit <sha>`. Quién mergea: Q-057 (`AGENTS.md`).

## Ajustes al diseño
Donde el diseño y el código de SPEC-00, o el orden real, difieren, manda esta tabla.

| `design.md` dice | Se implementa | Por qué |
|---|---|---|
| Orden: `TenantModel` antes que `Organization` | `Organization` entra en `T-TEN-02`, antes que `TenantModel` | `TenantModel` tiene FK a `settings.TENANT_MODEL`: sin `Organization` no migra. `design.md §5` ya nombra las cuatro migraciones |
| Cada módulo prohíbe `.objects` crudo con un test nuevo | Regla nueva en `backend/tests/architecture/tenant_rules.py`, enganchada a `ast_rules.py` | `ast_rules.py` tiene 273 líneas (`C-14`) y su regla C-01 marca **todo** `.objects`; hay que permitir los scopes |
| Humo E2E con Playwright | Script por HTTP sin navegador, `scripts/e2e_tenancy.py` | Playwright es dependencia nueva (`C-13`, ADR) y no hace falta para estos AC |
| `/sin-organizacion` con `EmptyState` propio | Página que reutiliza `NoOrganizationState` de `T-IDA-29`, con contacto del operador | SPEC-01 y SPEC-02 describen la misma pantalla (Q-109, Q-205) |
| `admin.py` de solo lectura | **Sin tarea** | Q-228 decidida (2026-11-07): sin admin en el MVP |
| `TENANT_MODEL`, `PLATFORM_OPERATOR_EMAILS`, etc. | Campos en `PlatformEnv` los que vienen del entorno; constantes en `base.py` los demás | `env.py` es el único que lee el entorno (RN-PLT-02) |
| Auditoría `apps/common/audit` y `AuditPort` de identity | Conviven; los dos escriben al canal `audit` | El diseño aprobado define ambos; unificarlos queda para SPEC-10, que aporta el sink real |

## Resumen

> T-TEN-01, T-TEN-02 y T-TEN-10 en revisión; las demás sin empezar. La columna **Evidencia** es obligatoria para `✅` y la verifica `scripts/check_spec_state.py`.

| ID | Título | AC | Capa | Archivos esperados (ver detalle) | Depende de | Agente | Tamaño | Zona roja | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|---|---|
| T-TEN-01 | `TenantContext`, `tenant_scope` y errores | — (RF-TEN-01, RF-TEN-08) | Base | `apps/common/tenancy/{context,current,middleware,errors}.py`, `.github/zona-roja-paths.txt` | — | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-01-tenant-context`, sin PR |
| T-TEN-02 | Queryset que falla cerrado + `Organization` + migración 0001 | AC-TEN-11 | DB | `apps/common/tenancy/querysets.py`, `apps/tenancy/models/organization.py` | T-TEN-01 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-02-organization`, sin PR |
| T-TEN-03 | `TenantModel` y app de prueba `tenant_probe` | AC-TEN-07 (guarda), AC-TEN-11 | Base | `apps/common/tenancy/models.py`, `tests/testapps/tenant_probe/` | T-TEN-02 | backend-dev | M | Sí | ☐ | |
| T-TEN-04 | Test de arquitectura de accesos crudos | AC-TEN-10 | Arquitectura | `backend/tests/architecture/tenant_rules.py`, `test_tenant_queries.py` | T-TEN-03 | backend-dev | L | Sí | ☐ | |
| T-TEN-05 | `Membership` + migración 0002 | — (RN-TEN-07, RN-TEN-21) | DB | `apps/tenancy/models/membership.py`, `apps/common/authz/roles.py` | T-TEN-03, T-IDA-01 | backend-dev | M | Sí | ☐ | |
| T-TEN-06 | Matriz de permisos como código | AC-TEN-15, AC-TEN-16, AC-TEN-34 (matriz) | Dominio | `apps/common/authz/{actions,checks}.py`, `apps/tenancy/domain/permissions.py` | T-TEN-01, T-TEN-05 | backend-dev | L | Sí | ☐ | |
| T-TEN-07 | Reglas de roles (`decide_*`) | AC-TEN-13, AC-TEN-15, AC-TEN-16, AC-TEN-27 (decisión) | Dominio | `apps/tenancy/domain/role_rules.py` | T-TEN-05 | backend-dev | L | Sí | ☐ | |
| T-TEN-08 | Resolución de organización por request | AC-TEN-03, AC-TEN-04, AC-TEN-06, AC-TEN-33 | API | `apps/tenancy/api/{permissions,base}.py`, `apps/tenancy/selectors/resolution.py` | T-TEN-05, T-TEN-06, T-IDA-06 | backend-dev | L | Sí | ☐ | |
| T-TEN-09 | Suite cross-tenant parametrizada | AC-TEN-12, AC-TEN-33 | Aislamiento | `backend/tests/cross_tenant/*` | T-TEN-08 | backend-dev | L | Sí | ☐ | |
| T-TEN-10 | Puerto de auditoría y catálogo | AC-TEN-23 (base) | Base | `apps/common/audit/{port,sinks}.py`, `apps/tenancy/domain/audit_events.py` | T-TEN-01 | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-10-audit-port`, sin PR |
| T-TEN-11 | Locks y tareas por organización | AC-TEN-28 (s2s) | Base | `apps/common/tenancy/{locks,celery}.py`, `apps/tenancy/selectors/locks.py` | T-TEN-08 | backend-dev | L | Sí | ☐ | |
| T-TEN-12 | `GET /api/organizations/` y selector para `/api/me` | AC-TEN-08, AC-TEN-21, AC-IDA-21 | API | `apps/tenancy/api/organizations.py`, `selectors/memberships.py`, `services/membership_selector.py` | T-TEN-08, T-IDA-07 | backend-dev | M | Sí | ☐ | |
| T-TEN-13 | Datos de la organización activa | AC-TEN-29 (API) | API | `apps/tenancy/api/organizations.py`, `services/organizations.py`, `domain/tax_id.py` | T-TEN-10, T-TEN-11, T-TEN-12 | backend-dev | L | Sí | ☐ | |
| T-TEN-14 | `Invitation` + migración 0003 + reglas puras | AC-TEN-25, AC-TEN-35 (unidad) | DB | `apps/tenancy/models/invitation.py`, `domain/invitations.py` | T-TEN-05 | backend-dev | L | Sí | ☐ | |
| T-TEN-15 | Aceptar invitación con token | AC-TEN-17, AC-TEN-18, AC-TEN-19, AC-TEN-25, AC-TEN-35 | Servicio/API | `services/invitation_accept.py`, `api/invitations.py` | T-TEN-10, T-TEN-11, T-TEN-14 | backend-dev | L | Sí | ☐ | |
| T-TEN-16 | Mis invitaciones y aceptar desde la sesión (Q-124) | AC-TEN-39, AC-TEN-28, AC-TEN-10 | Servicio/API | `selectors/invitations.py`, `api/invitations.py`, `services/invitation_accept.py` | T-TEN-15 | backend-dev | L | Sí | ☐ | |
| T-TEN-17 | `TenancyInvitationPort` (puerto de SPEC-01) | AC-TEN-17 (vía puerto), AC-IDA-02, AC-IDA-04, AC-IDA-05, AC-IDA-31 | Servicio | `services/invitation_port.py`, `config/settings/base.py` | T-TEN-15, T-IDA-13 | backend-dev | M | Sí | ☐ | |
| T-TEN-18 | Comando `tenancy_create_org` | AC-TEN-22, AC-TEN-40, AC-IDA-32 | Comandos | `services/platform_org.py`, `management/commands/tenancy_create_org.py` | T-TEN-16, T-TEN-17 | backend-dev | L | Sí | ☐ | |
| T-TEN-19 | Comandos de suspensión y primer owner | AC-TEN-28, AC-TEN-29 | Comandos | `management/commands/{tenancy_set_org_status,tenancy_owner_invite}.py` | T-TEN-18 | backend-dev | M | Sí | ☐ | |
| T-TEN-20 | Crear y listar invitaciones | AC-TEN-15, AC-TEN-20, AC-TEN-24, AC-TEN-26, AC-TEN-34 | Servicio/API | `services/invitations.py`, `api/invitations.py`, `api/serializers/invitations.py` | T-TEN-07, T-TEN-15 | backend-dev | L | Sí | ☐ | |
| T-TEN-21 | Reenviar y revocar invitaciones | AC-TEN-02, AC-TEN-15, AC-TEN-24, AC-TEN-26, AC-TEN-37 | Servicio/API | `services/invitations.py`, `api/invitations.py` | T-TEN-20 | backend-dev | M | Sí | ☐ | |
| T-TEN-22 | Listar memberships y cambiar rol | AC-TEN-02, AC-TEN-05, AC-TEN-13, AC-TEN-15, AC-TEN-16, AC-TEN-27, AC-TEN-34 | Servicio/API | `services/memberships.py`, `api/memberships.py` | T-TEN-07, T-TEN-11 | backend-dev | L | Sí | ☐ | |
| T-TEN-23 | Revocar, abandonar y autorrevocar invitaciones | AC-TEN-04, AC-TEN-13, AC-TEN-14, AC-TEN-15, AC-TEN-31, AC-TEN-36 | Servicio/API | `services/memberships.py`, `api/memberships.py` | T-TEN-21, T-TEN-22 | backend-dev | L | Sí | ☐ | |
| T-TEN-24 | `Branch` + migración 0004 + crear y listar | AC-TEN-07, AC-TEN-16, AC-TEN-30, AC-TEN-38 | DB/API | `models/branch.py`, `services/branches.py`, `api/branches.py` | T-TEN-08, T-TEN-11 | backend-dev | L | Sí | ☐ | |
| T-TEN-25 | Ver, editar, desactivar y reactivar `Branch`, filtro | AC-TEN-01, AC-TEN-05, AC-TEN-09, AC-TEN-30, AC-TEN-32, AC-TEN-37, AC-TEN-38 | Servicio/API | `services/branches.py`, `api/branches.py`, `api/filters.py` | T-TEN-24 | backend-dev | L | Sí | ☐ | |
| T-TEN-26 | Vencimiento de invitaciones y email por flag | AC-TEN-37 | Asíncrono | `apps/tenancy/tasks.py` | T-TEN-11, T-TEN-21 | backend-dev | M | Sí | ☐ | |
| T-TEN-27 | Completitud de auditoría y suspendida genérica | AC-TEN-23, AC-TEN-28 | Aislamiento | `backend/tests/cross_tenant/*`, `apps/tenancy/tests/test_audit_triggers.py` | T-TEN-13, T-TEN-23, T-TEN-25, T-TEN-26 | backend-dev | M | Sí | ☐ | |
| T-TEN-28 | Comandos de soporte y recuperación de owner | AC-TEN-23 (`purpose`) | Comandos | `services/platform_access.py`, `management/commands/{tenancy_support_access,tenancy_owner_recovery}.py` | T-TEN-18 | backend-dev | M | Sí | ☐ | |
| T-TEN-29 | Organización activa en el frontend y selector | — (RF-TEN-02, spec §14) | UI | `src/modules/tenancy/context/ActiveOrgProvider.tsx`, `src/lib/api-client.ts`, `context/07-frontend-ui-guidelines.md` | T-TEN-12, T-IDA-27 | frontend-dev | L | No | ☐ | |
| T-TEN-30 | Sin organización y aviso de invitaciones (Q-124) | AC-TEN-39 (UI) | UI | `app/(dashboard)/sin-organizacion/page.tsx`, `src/modules/tenancy/components/PendingInvitationsNotice.tsx` | T-TEN-16, T-TEN-29, T-IDA-29 | frontend-dev | M | Sí | ☐ | |
| T-TEN-31 | Pantalla `/invitacion` | AC-TEN-17 (UI) | UI | `app/invitacion/page.tsx`, `src/modules/tenancy/components/AcceptInvitation.tsx` | T-TEN-15, T-TEN-29 | frontend-dev | M | Sí | ☐ | |
| T-TEN-32 | Datos de la empresa y abandonar | — (RF-TEN-03, RF-TEN-04, spec §14) | UI | `app/(dashboard)/configuracion/empresa/page.tsx`, `src/modules/tenancy/components/CompanyDataForm.tsx` | T-TEN-13, T-TEN-23, T-TEN-29 | frontend-dev | M | No | ☐ | |
| T-TEN-33 | Sucursales | — (RF-TEN-06, spec §14) | UI | `app/(dashboard)/configuracion/sucursales/page.tsx`, `BranchesTable.tsx`, `BranchFormDialog.tsx` | T-TEN-25, T-TEN-29 | frontend-dev | L | No | ☐ | |
| T-TEN-34 | Colaboradores: miembros | — (RF-TEN-04, spec §14) | UI | `app/(dashboard)/configuracion/colaboradores/page.tsx`, `MembersTable.tsx` | T-TEN-23, T-TEN-29 | frontend-dev | L | No | ☐ | |
| T-TEN-35 | Colaboradores: invitaciones y link de una sola vez | AC-TEN-24 (UI) | UI | `InviteDialog.tsx`, `InvitationLinkDialog.tsx` | T-TEN-21, T-TEN-34 | frontend-dev | M | Sí | ☐ | |
| T-TEN-36 | E2E y cierre conjunto con SPEC-01 | AC-TEN-08, AC-TEN-22, AC-TEN-39 | E2E | `scripts/e2e_tenancy.py`, `scripts/tests/test_e2e_tenancy.py` | T-TEN-30, T-TEN-31, T-TEN-35, T-IDA-31 | backend-dev | M | Sí | ☐ | |

## Cobertura AC → tareas
| AC | Tareas |
|---|---|
| AC-TEN-01 | T-TEN-25 |
| AC-TEN-02 | T-TEN-21 (invitación), T-TEN-22 (membership) |
| AC-TEN-03 | T-TEN-08 |
| AC-TEN-04 | T-TEN-08, T-TEN-23 |
| AC-TEN-05 | T-TEN-22, T-TEN-25 |
| AC-TEN-06 | T-TEN-08 |
| AC-TEN-07 | T-TEN-03, T-TEN-24 |
| AC-TEN-08 | T-TEN-12, T-TEN-36 |
| AC-TEN-09 | T-TEN-25 |
| AC-TEN-10 | T-TEN-04, T-TEN-16 |
| AC-TEN-11 | T-TEN-02, T-TEN-03 |
| AC-TEN-12 | T-TEN-09 |
| AC-TEN-13 | T-TEN-07, T-TEN-22, T-TEN-23 |
| AC-TEN-14 | T-TEN-23 |
| AC-TEN-15 | T-TEN-06, T-TEN-07, T-TEN-20, T-TEN-21, T-TEN-22, T-TEN-23 |
| AC-TEN-16 | T-TEN-06, T-TEN-07, T-TEN-22, T-TEN-24 |
| AC-TEN-17 | T-TEN-15, T-TEN-17 (vía puerto), T-TEN-31 |
| AC-TEN-18 | T-TEN-15 |
| AC-TEN-19 | T-TEN-15 |
| AC-TEN-20 | T-TEN-20 |
| AC-TEN-21 | T-TEN-12 |
| AC-TEN-22 | T-TEN-18, T-TEN-36 |
| AC-TEN-23 | T-TEN-10, T-TEN-27, T-TEN-28 |
| AC-TEN-24 | T-TEN-20, T-TEN-21, T-TEN-35 |
| AC-TEN-25 | T-TEN-14, T-TEN-15 |
| AC-TEN-26 | T-TEN-20, T-TEN-21 |
| AC-TEN-27 | T-TEN-07, T-TEN-22 |
| AC-TEN-28 | T-TEN-11, T-TEN-16, T-TEN-19, T-TEN-27 |
| AC-TEN-29 | T-TEN-13, T-TEN-19 |
| AC-TEN-30 | T-TEN-24, T-TEN-25 |
| AC-TEN-31 | T-TEN-23 |
| AC-TEN-32 | T-TEN-25 |
| AC-TEN-33 | T-TEN-08, T-TEN-09 |
| AC-TEN-34 | T-TEN-06, T-TEN-20, T-TEN-22 |
| AC-TEN-35 | T-TEN-14, T-TEN-15 |
| AC-TEN-36 | T-TEN-23 |
| AC-TEN-37 | T-TEN-21, T-TEN-25, T-TEN-26 |
| AC-TEN-38 | T-TEN-24, T-TEN-25 |
| AC-TEN-39 | T-TEN-16, T-TEN-30, T-TEN-36 |
| AC-TEN-40 | T-TEN-18 |

**RF → tareas:** RF-TEN-01 → T-TEN-01, T-TEN-08 · RF-TEN-02 → T-TEN-12, T-TEN-29 · RF-TEN-03 → T-TEN-13, T-TEN-32 ·
RF-TEN-04 → T-TEN-22, T-TEN-23, T-TEN-34 · RF-TEN-05 → T-TEN-14, T-TEN-15, T-TEN-16, T-TEN-20, T-TEN-21, T-TEN-26,
T-TEN-35 · RF-TEN-06 → T-TEN-24, T-TEN-25, T-TEN-33 · RF-TEN-07 → T-TEN-18, T-TEN-19, T-TEN-28 · RF-TEN-08 → T-TEN-01,
T-TEN-02, T-TEN-03, T-TEN-06, T-TEN-08, T-TEN-11 · RF-TEN-09 → T-TEN-10, T-TEN-27.

**RNF → tareas:** RNF-TEN-01 → T-TEN-04, T-TEN-09 · RNF-TEN-02 → T-TEN-08 · RNF-TEN-03 → T-TEN-14, T-TEN-20 ·
RNF-TEN-04 → T-TEN-10, T-TEN-27 · RNF-TEN-05 → T-TEN-02, T-TEN-05, T-TEN-14, T-TEN-24 · RNF-TEN-06 → T-TEN-14 ·
RNF-TEN-07 → T-TEN-08.

**Spec §14 → tareas:** selector → T-TEN-29 · Colaboradores → T-TEN-34, T-TEN-35 · Datos de la empresa → T-TEN-32 ·
Sucursales → T-TEN-33 · Aceptar invitación → T-TEN-31 · Invitaciones en la sesión → T-TEN-30 · sin organización →
T-TEN-30 · suspendida → T-TEN-29.

**Huecos:** ningún AC ni RF sin tarea. Dos salvedades:
- **Q-220 (Caja):** no es de este módulo. RN-TEN-15 queda cubierta del lado de 02 por `branch_org_id_uniq` en `T-TEN-24`;
  la FK compuesta la agrega SPEC-04/05.

## Orden y paralelismo
| Ola | Tareas | Notas |
|---|---|---|
| 0 | T-TEN-01 → T-TEN-02 → T-TEN-03 → T-TEN-04 · T-TEN-10 | No necesitan a SPEC-01 |
| 1 | T-TEN-05 (tras T-IDA-01) → {T-TEN-06, T-TEN-07, T-TEN-14} | |
| 2 | T-TEN-08 (tras T-IDA-06) → {T-TEN-09, T-TEN-11, T-TEN-12} | Con T-TEN-08 hay aislamiento real sobre `tenant_probe` |
| 3 | T-TEN-13 · T-TEN-15 → {T-TEN-16, T-TEN-17, T-TEN-20} | T-TEN-17 espera a T-IDA-13: desde ahí un invitado entra de verdad |
| 4 | T-TEN-18 → {T-TEN-19, T-TEN-28} · T-TEN-20 → T-TEN-21 · T-TEN-22 → T-TEN-23 · T-TEN-24 → T-TEN-25 · T-TEN-26 | Con T-TEN-18 existe la primera organización real |
| 5 | T-TEN-27 · T-TEN-29 → {T-TEN-30, T-TEN-31, T-TEN-32, T-TEN-33, T-TEN-34} → T-TEN-35 | T-TEN-29 espera a T-IDA-27 |
| 6 | T-TEN-36 | Cierre conjunto (Q-108): después se verifican 01 y 02 en la misma pasada |

---

## Detalle por tarea

### T-TEN-01 — `TenantContext`, `tenant_scope` y errores
- **AC:** — (RF-TEN-01, RF-TEN-08). **Zona roja:** sí.
- **Archivos:** `apps/common/tenancy/{context,current,middleware,errors}.py`, `config/settings/base.py`,
  `.github/zona-roja-paths.txt`, `backend/tests/tenancy/test_context.py`.
- **Cambios:** `design.md §3.1`. Agrega `backend/apps/common/{tenancy,authz,audit}/**` a la zona roja.
- **Fuera:** queryset, modelos.
- **Pruebas:** `test_RF_TEN_01_context_is_frozen`, `test_RF_TEN_01_scope_resets_on_exit`,
  `test_RF_TEN_01_organization_id_bound_to_logs`.

### T-TEN-02 — Queryset que falla cerrado + `Organization` + migración 0001
- **AC:** AC-TEN-11. RN-TEN-02, RNF-TEN-05. **Zona roja:** sí.
- **Archivos:** `apps/common/tenancy/{querysets,models}.py` (`NoHardDeleteMixin`), `apps/tenancy/{__init__,apps}.py`,
  `models/{__init__,organization}.py`, `migrations/0001_organization.py`, `config/settings/base.py`,
  `backend/tests/tenancy/test_AC_TEN_11_fail_closed.py`, `backend/tests/tenancy/test_AC_TEN_11_scoped_writes.py`.
- **Cambios:** `design.md §3.4` y tabla `tenancy_organization` de §5. Con scope de tenant, `bulk_create` con
  `ignore_conflicts`/`update_conflicts`, o con instancias de otra organización, y `raw` fallan cerrado; asignar
  `qs.query` limpia el scope.
- **Pruebas:** `test_AC_TEN_11_every_terminal_method_raises` (parametrizado, sin ir a la BD),
  `test_AC_TEN_11_clone_keeps_scope`, `test_hard_delete_is_forbidden`,
  `test_AC_TEN_11_bulk_create_under_a_tenant_leaves_other_organizations`.

### T-TEN-03 — `TenantModel` y app de prueba `tenant_probe`
- **AC:** AC-TEN-07 (guarda), AC-TEN-11. RN-TEN-01, RN-TEN-04. **Zona roja:** sí.
- **Archivos:** `apps/common/tenancy/models.py`, `backend/tests/testapps/tenant_probe/{models,views,tasks}.py` y migración,
  `config/settings/test.py`, tests.
- **Cambios:** FK `PROTECT`, `related_name="+"`, guarda de `save()`; `Widget` solo en settings de test.
- **Pruebas:** `test_AC_TEN_07_save_rejects_other_org`, `test_AC_TEN_11_tenant_model_without_scope_raises`,
  `test_organization_id_is_immutable`.
- **Pendiente heredado de T-TEN-02 (revisión del PR #89):** `Organization.save()` con el `pk` cambiado
  (`org.pk = b.pk; org.save()`) sobrescribe la otra organización, porque `save()` usa `_base_manager`. La guarda de
  `save()` de `TenantModel` no cubre a `Organization`: resolverlo acá o en los servicios de organización.

### T-TEN-04 — Test de arquitectura de accesos crudos
- **AC:** AC-TEN-10. RN-TEN-02, RNF-TEN-01. **Zona roja:** sí.
- **Archivos:** `backend/tests/architecture/tenant_rules.py` (nuevo), `ast_rules.py`, `allowlists.py`,
  `test_tenant_queries.py`, `test_AC_PLT_15_no_raw_objects_in_services.py`, `synthetic/charges/services/`.
- **División (`C-14`), obligatoria:** `ast_rules.py` tiene 273 líneas; las reglas nuevas van en `tenant_rules.py`, como
  `money_rules.py`.
- **Cambios:** `X.objects.<attr>` solo con scopes permitidos; `unscoped(` y `TenantContext(` fuera de lista blanca fallan;
  todo modelo de negocio hereda `TenantModel` (exentos: `Organization`, `identity`, auditoría). AC-PLT-15 sigue en verde.
- **Pruebas:** `test_AC_TEN_10_raw_manager_fails_naming_the_file` (archivo sintético), `test_AC_TEN_10_scoped_call_passes`,
  `test_AC_TEN_10_unscoped_outside_allowlist_fails`.

### T-TEN-05 — `Membership` + migración 0002
- **AC:** — (RN-TEN-07, RN-TEN-21, RNF-TEN-05). **Zona roja:** sí.
- **Archivos:** `models/membership.py`, `migrations/0002_membership.py`, `apps/common/authz/roles.py`, tests.
- **Cambios:** constraints e índice parcial de §5; `source_invitation` entra en `T-TEN-14`.
- **Pruebas:** `test_RN_TEN_07_one_active_per_org_and_user`, `test_RN_TEN_21_end_fields_are_coherent`,
  `test_RN_TEN_07_two_orgs_are_allowed`.

### T-TEN-06 — Matriz de permisos como código
- **AC:** AC-TEN-15, 16, 34 (matriz). RN-TEN-09, Q-218, Q-221. **Zona roja:** sí.
- **Archivos:** `apps/common/authz/{actions,checks}.py`, `apps/tenancy/domain/permissions.py`,
  `backend/tests/tenancy/domain/test_permission_matrix_active.py`, `test_permission_matrix_suspended.py`.
- **División (`C-14`):** la tabla literal se parte en dos archivos, `active` y `suspended`.
- **Cambios:** `design.md §3.8`; `SUSPENDED_ALLOWED_KINDS` en un solo lugar.
- **Pruebas:** `test_AC_TEN_15_matrix_admin_owner_actions`, `test_AC_TEN_16_matrix_operator_viewer`,
  `test_AC_TEN_34_member_list_denied`, `test_all_actions_declared`.

### T-TEN-07 — Reglas de roles (`decide_*`)
- **AC:** AC-TEN-13, 15, 16, 27 (decisión). RN-TEN-13, RN-TEN-14. **Zona roja:** sí.
- **Archivos:** `apps/tenancy/domain/role_rules.py`, `backend/tests/tenancy/domain/test_role_rules.py`.
- **Cambios:** funciones de `design.md §3.8`, incluida `invitations_to_auto_revoke`.
- **Pruebas:** tabla completa `Role × Role × Role × is_self × owners∈{1,2}`: `test_AC_TEN_13_last_owner_decision`,
  `test_AC_TEN_15_admin_never_touches_owner`, `test_AC_TEN_16_no_self_elevation`, `test_AC_TEN_27_transfer_decision`.

### T-TEN-08 — Resolución de organización por request
- **AC:** AC-TEN-03, 04, 06, 33. RF-TEN-01, RN-TEN-03, 06, 08, 20, RNF-TEN-02, RNF-TEN-07. **Zona roja:** sí.
- **Archivos:** `apps/tenancy/api/{permissions,base}.py`, `selectors/resolution.py`, `apps/common/api/problems.py`,
  `backend/tests/tenancy/api/test_resolution.py`.
- **Cambios:** `design.md §3.5`; cuerpo constante en el `404`.
- **Pruebas:** `test_AC_TEN_03_foreign_equals_nonexistent`, `test_AC_TEN_04_revoked_membership_with_valid_jwt`,
  `test_AC_TEN_06_missing_header`, `test_AC_TEN_33_superuser_without_membership`,
  `test_RNF_TEN_07_one_query_per_request`, `test_RNF_TEN_02_denial_is_logged`.

### T-TEN-09 — Suite cross-tenant parametrizada
- **AC:** AC-TEN-12, AC-TEN-33. RNF-TEN-01. **Zona roja:** sí.
- **Archivos:** `backend/tests/cross_tenant/{conftest,classifier,harness,test_routes}.py`, `cases/{tenant_probe,tenancy,identity}.py`.
- **Cambios:** `design.md §9`. Clasifica también las rutas de 00 y 01 como exentas, con justificación.
- **Pruebas:** `test_AC_TEN_12_new_route_without_case_fails`, `test_AC_TEN_12_every_case_runs`,
  `test_AC_TEN_33_superuser_body_identical`.

### T-TEN-10 — Puerto de auditoría y catálogo
- **AC:** AC-TEN-23 (base). RF-TEN-09, RN-TEN-17. **Zona roja:** sí.
- **Archivos:** `apps/common/audit/{port,sinks}.py`, `apps/tenancy/domain/audit_events.py`, `services/audit.py`,
  `config/settings/{base,test}.py`, tests.
- **Cambios:** `TenancyAuditAction` con toda la lista de RNF-TEN-04 (incluye `invitation.expired`,
  `invitation.auto_revoked`, `transition.rejected`); `RecordingSink`, `StructlogAuditSink`, registro `AUDIT_TRIGGERS`.
- **Pruebas:** `test_AC_TEN_23_catalog_equals_spec_list`, `test_recording_sink_keeps_events`.

### T-TEN-11 — Locks y tareas por organización
- **AC:** AC-TEN-28 (s2s). RN-TEN-18, RF-TEN-08. **Zona roja:** sí.
- **Archivos:** `apps/common/tenancy/{locks,celery}.py`, `apps/tenancy/selectors/locks.py`,
  `backend/tests/testapps/tenant_probe/tasks.py`, tests.
- **Cambios:** `design.md §3.6` y §3.7; `lock_timeout` de 5 s. Como todavía no hay cobros, AC-TEN-28 s2s se prueba con una
  `TenantTask` de `tenant_probe`.
- **Pruebas:** `test_AC_TEN_28_system_task_runs_on_suspended_org`, `test_ensure_writable_blocks_user_actor`,
  `test_suspend_waits_for_write_in_flight` (hilos).

### T-TEN-12 — `GET /api/organizations/` y selector para `/api/me`
- **AC:** AC-TEN-08, AC-TEN-21, AC-IDA-21. RF-TEN-02, RF-IDA-06. **Zona roja:** sí.
- **Archivos:** `api/organizations.py`, `api/urls.py`, `selectors/memberships.py`, `services/membership_selector.py`,
  `config/settings/base.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** implementa `MembershipSelectorPort`; fija `MembershipSummary`; `POST/PUT/DELETE` → `405`.
- **Pruebas:** `test_AC_TEN_08_exactly_my_orgs_and_roles`, `test_AC_TEN_21_no_org_creation_via_api`,
  `test_AC_IDA_21_me_uses_real_selector`.

### T-TEN-13 — Datos de la organización activa
- **AC:** AC-TEN-29 (API). RF-TEN-03, Q-209. **Zona roja:** sí.
- **Archivos:** `api/organizations.py`, `api/serializers/organizations.py`, `services/organizations.py`, `domain/tax_id.py`,
  `openapi.yaml`, `api.d.ts`, tests.
- **Pruebas:** `test_AC_TEN_29_status_is_not_writable`, `test_RF_TEN_03_owner_and_admin_edit`, `test_tax_id_check_digit`,
  caso `tenancy.py` para `current`.

### T-TEN-14 — `Invitation` + migración 0003 + reglas puras
- **AC:** AC-TEN-25, AC-TEN-35 (unidad). RNF-TEN-03, 05, 06. **Zona roja:** sí.
- **Archivos:** `models/invitation.py`, `models/membership.py` (`source_invitation`), `migrations/0003_invitation.py`,
  `domain/invitations.py`, tests.
- **Cambios:** tabla de §5; `normalize_email` comparte contrato con el de identity, sin importarlo (`domain` puro).
- **Pruebas:** `test_AC_TEN_25_expiry_edge_with_injected_clock`, `test_AC_TEN_35_normalization`,
  `test_RNF_TEN_03_only_hash_is_stored`, `test_one_pending_per_org_and_email`.

### T-TEN-15 — Aceptar invitación con token
- **AC:** AC-TEN-17, 18, 19, 25, 35. RN-TEN-11, RN-TEN-12. **Zona roja:** sí.
- **Archivos:** `services/invitation_accept.py`, `api/invitations.py`, `api/serializers/invitations.py`, `api/urls.py`,
  `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `design.md §4.4`. Servicio único: lo reusan `T-TEN-16` y `T-TEN-17`.
- **Pruebas:** `test_AC_TEN_17_accept_creates_membership`, `test_AC_TEN_17_double_accept_in_parallel` (hilos),
  `test_AC_TEN_18_other_email_keeps_pending`, `test_AC_TEN_19_expired_or_revoked`, `test_AC_TEN_25_at_seven_days`,
  `test_AC_TEN_35_case_and_alias`.

### T-TEN-16 — Mis invitaciones y aceptar desde la sesión (Q-124)
- **AC:** AC-TEN-39, AC-TEN-28 (ruta exenta), AC-TEN-10 (scope limitado). RF-TEN-05, RN-TEN-11, Q-121, Q-124. **Zona roja:** sí.
- **Archivos:** `models/invitation.py` (scope `for_session_accept`), `backend/tests/architecture/allowlists.py`, `tenant_rules.py`,
  `selectors/invitations.py`, `services/invitation_accept.py`, `api/invitations.py`, `api/urls.py`,
  `backend/tests/cross_tenant/cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `GET /api/invitations/mine/` y `POST /api/invitations/{id}/accept/` (`design.md §4.4`, con su orden de
  tres pasos); exentas de organización activa. Sin token en ninguna respuesta. `for_session_accept` **no** entra en la
  lista general de scopes de `T-TEN-04`: se permite solo en `services/invitation_accept.py`, con una entrada que cite el
  motivo. Si al releer bajo lock el email ya no coincide, responde `not_found`, sin membership y con `invitation.rejected`
  fuera del `atomic`.
- **Fuera:** UI (`T-TEN-30`).
- **Pruebas:** `test_AC_TEN_39_lists_only_my_email`, `test_AC_TEN_39_response_has_no_token`,
  `test_AC_TEN_39_accept_from_session`, `test_AC_TEN_39_other_email_is_invalid_and_stays_pending`,
  `test_AC_TEN_39_expired_and_suspended_are_not_listed`, `test_AC_TEN_39_foreign_and_missing_same_body`,
  `test_AC_TEN_39_foreign_attempt_is_audited` (`transaction=True`: el evento debe quedar confirmado),
  `test_AC_TEN_28_accept_from_session_is_409`, `test_AC_TEN_39_double_accept_one_membership`,
  `test_AC_TEN_39_accept_vs_revoke_in_parallel` (hilos), `test_AC_TEN_39_email_changed_under_lock_is_not_found`,
  `test_AC_TEN_10_for_session_accept_outside_its_service_fails`.

### T-TEN-17 — `TenancyInvitationPort` (puerto de SPEC-01)
- **AC:** AC-TEN-17 (vía puerto); AC-IDA-02, 04, 05, 31 con puerto real. RN-TEN-11, RN-IDA-06, Q-108, Q-120. **Zona roja:** sí.
- **Archivos:** `services/invitation_port.py`, `selectors/invitations.py`, `config/settings/base.py`,
  `backend/tests/tenancy/test_invitation_port_contract.py`, `backend/tests/identity/test_login_with_real_port.py`.
- **Cambios:** firma de `specs/01-identity-access/design.md §6.4`, **todo o nada**; locks en orden de `id`. `apps/identity`
  sigue sin importar `apps/tenancy`.
- **Pruebas:** `test_AC_TEN_17_accept_via_port`, `test_AC_IDA_02_invited_login_creates_membership`, `test_AC_IDA_04_expired_invitation`,
  `test_AC_IDA_05_one_invalid_rolls_back_all`, `test_AC_IDA_31_normalized_email_matches`,
  `test_Q_120_all_valid_invitations_accepted`.

### T-TEN-18 — Comando `tenancy_create_org`
- **AC:** AC-TEN-22, AC-TEN-40, AC-IDA-32 (bootstrap). RF-TEN-07, RF-IDA-08, RN-TEN-10, Q-123, Q-124. **Zona roja:** sí.
- **Archivos:** `services/platform_org.py`, `management/commands/tenancy_create_org.py`, `config/settings/env.py`,
  `env.example`, `backend/tests/tenancy/commands/test_create_org.py`.
- **Cambios:** `design.md §4.5`: `--operator` en `PLATFORM_OPERATOR_EMAILS`, idempotente por `--key`, link una vez por
  stdout. **Q-124:** nunca crea membership; si el email ya tiene usuario, igual emite la invitación.
- **Pruebas:** `test_AC_TEN_22_org_without_memberships_plus_invitation`, `test_AC_TEN_22_accept_gives_one_owner`,
  `test_AC_TEN_40_existing_user_gets_invitation_not_membership`, `test_AC_TEN_40_next_login_does_not_accept`,
  `test_AC_TEN_40_accept_from_session_gives_one_owner`, `test_AC_IDA_32_bootstrap_command_audited`,
  `test_Q_123_repeat_creates_nothing`.

### T-TEN-19 — Comandos de suspensión y primer owner
- **AC:** AC-TEN-28, AC-TEN-29. RF-TEN-07, RN-TEN-18, Q-208, Q-213. **Zona roja:** sí.
- **Archivos:** `services/platform_org.py`, `management/commands/{tenancy_set_org_status,tenancy_owner_invite}.py`, tests.
- **Pruebas:** `test_AC_TEN_29_status_changes_only_by_command`, `test_AC_TEN_28_suspended_blocks_writes_allows_reads`,
  `test_Q_213_reissue_only_without_owner`.

### T-TEN-20 — Crear y listar invitaciones
- **AC:** AC-TEN-15, 20, 24, 26, 34. RF-TEN-05, RN-TEN-13, RNF-TEN-03, Q-207. **Zona roja:** sí.
- **Archivos:** `services/invitations.py`, `api/invitations.py`, `api/serializers/invitations.py`,
  `backend/tests/cross_tenant/cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `design.md §4.3`, `accept_url` con fragmento `#token=`, una sola vez; `IntegrityError` → `invitation_pending`.
- **Pruebas:** `test_AC_TEN_15_admin_cannot_invite_owner`, `test_AC_TEN_20_already_member`,
  `test_AC_TEN_24_token_only_in_create_response`, `test_AC_TEN_26_second_pending_rejected`,
  `test_AC_TEN_34_operator_cannot_list`.

### T-TEN-21 — Reenviar y revocar invitaciones
- **AC:** AC-TEN-02, 15, 24, 26, 37. RF-TEN-05. **Zona roja:** sí.
- **Archivos:** `services/invitations.py`, `api/invitations.py`, `cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** transiciones inválidas → `invalid_transition` + `transition.rejected`.
- **Pruebas:** `test_AC_TEN_26_resend_revokes_old_and_renews`, `test_AC_TEN_15_admin_cannot_manage_owner_invitation`,
  `test_AC_TEN_02_other_org_invitation_is_404`, `test_AC_TEN_24_old_token_is_invalid`,
  `test_AC_TEN_37_revoke_accepted_is_invalid_transition`.

### T-TEN-22 — Listar memberships y cambiar rol
- **AC:** AC-TEN-02, 05, 13, 15, 16, 27, 34. RF-TEN-04. **Zona roja:** sí.
- **Archivos:** `services/memberships.py`, `api/memberships.py`, `api/serializers/memberships.py`, `cases/tenancy.py`,
  `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `design.md §4.2`, pasos 1 a 3; el rechazo `last_owner` se audita fuera del `atomic`.
- **Pruebas:** `test_AC_TEN_05_demoted_admin_next_request_403`, `test_AC_TEN_13_last_owner_demotion`,
  `test_AC_TEN_15_admin_cannot_assign_owner`, `test_AC_TEN_16_operator_cannot_change_role`,
  `test_AC_TEN_27_transfer_ownership`, `test_AC_TEN_34_viewer_cannot_list`, `test_AC_TEN_02_other_org_membership_is_404`.

### T-TEN-23 — Revocar, abandonar y autorrevocar invitaciones
- **AC:** AC-TEN-04, 13, 14, 15, 31, 36. RN-TEN-14, RN-TEN-21, Q-221, Q-223. **Zona roja:** sí.
- **Archivos:** `services/memberships.py`, `api/memberships.py`, `cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **División (`C-14`):** si `services/memberships.py` pasa de 250 líneas, revocar y abandonar van a `services/membership_exit.py`.
- **Pruebas:** `test_AC_TEN_04_revoked_admin_is_rejected`, `test_AC_TEN_13_last_owner_cannot_leave`,
  `test_AC_TEN_14_mutual_demotion_keeps_one_owner` (hilos), `test_AC_TEN_31_leave_then_reinvite_is_new_membership`,
  `test_AC_TEN_36_auto_revoked_on_demotion_revoke_and_leave`, `test_Q_221_revoke_allowed_when_suspended`.

### T-TEN-24 — `Branch` + migración 0004 + crear y listar
- **AC:** AC-TEN-07, 16, 30, 38. RF-TEN-06, RN-TEN-15, Q-226, Q-227. **Zona roja:** sí.
- **Archivos:** `models/branch.py`, `migrations/0004_branch.py`, `services/branches.py`, `selectors/branches.py`,
  `api/branches.py`, `api/serializers/branches.py`, `cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** constraints de §5, `branch_org_id_uniq` incluida; `IntegrityError` → `409 conflict`.
- **Pruebas:** `test_AC_TEN_07_org_in_body_creates_nothing_in_b`, `test_AC_TEN_16_viewer_cannot_create_branch`,
  `test_AC_TEN_30_inactive_listed`, `test_AC_TEN_38_name_case_insensitive_and_code`,
  `test_AC_TEN_38_inactive_frees_values`, `test_AC_TEN_38_other_org_accepts`.

### T-TEN-25 — Ver, editar, desactivar y reactivar `Branch`, filtro
- **AC:** AC-TEN-01, 05, 09, 30, 32, 37, 38. RF-TEN-06, RN-TEN-16, RN-TEN-19. **Zona roja:** sí.
- **Archivos:** `services/branches.py`, `api/branches.py`, `api/filters.py`, `cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Pruebas:** `test_AC_TEN_01_other_org_branch_is_404`, `test_AC_TEN_05_demoted_admin_cannot_edit_branch`,
  `test_AC_TEN_09_foreign_branch_filter_is_404`, `test_AC_TEN_30_reactivate_with_taken_name`, `test_AC_TEN_30_no_physical_delete`,
  `test_AC_TEN_32_operator_filters_any_branch`, `test_AC_TEN_37_reactivate_active_is_invalid_transition`,
  `test_AC_TEN_38_patch_to_taken_name`.

### T-TEN-26 — Vencimiento de invitaciones y email por flag
- **AC:** AC-TEN-37. RF-TEN-05, Q-207, Q-225. **Zona roja:** sí.
- **Archivos:** `apps/tenancy/tasks.py`, `apps/tenancy/beat.py`, `config/celery.py`, `apps/common/feature_flags.py`, `env.example`, tests.
- **Cambios:** `expire_invitations` por fan-out; `send_invitation_email` detrás de `TENANCY_INVITATION_EMAIL_ENABLED`,
  apagado. Sin proveedor (Q-207): backend de consola en dev.
- **Pruebas:** `test_AC_TEN_37_expiry_task_emits_system_event`, `test_fanout_only_enumerates_ids`,
  `test_token_never_reaches_broker_with_flag_off`.

### T-TEN-27 — Completitud de auditoría y suspendida genérica
- **AC:** AC-TEN-23, AC-TEN-28. RF-TEN-09, RNF-TEN-04. **Zona roja:** sí.
- **Archivos:** `backend/tests/cross_tenant/harness.py`, `apps/tenancy/tests/test_audit_triggers.py`, los servicios a los que les falte un evento.
- **Pruebas:** `test_AC_TEN_23_every_action_has_trigger_and_fields`, `test_AC_TEN_28_every_write_case_is_409_when_suspended`,
  `test_AC_TEN_28_reads_pass_when_suspended`.

### T-TEN-28 — Comandos de soporte y recuperación de owner
- **AC:** AC-TEN-23 (`purpose`). RF-TEN-07, RN-TEN-20, Q-222, Q-224, Q-225. **Zona roja:** sí.
- **Archivos:** `services/platform_access.py`, `management/commands/{tenancy_support_access,tenancy_owner_recovery}.py`, tests.
- **Cambios:** `design.md §4.5`. El aviso a owners existentes queda atado al flag de email.
- **Pruebas:** `test_Q_222_support_is_invitation_never_owner`, `test_Q_222_reason_is_required`,
  `test_Q_224_recovery_revokes_nobody`, `test_AC_TEN_23_purpose_in_events`.

### T-TEN-29 — Organización activa en el frontend y selector
- **AC:** — (RF-TEN-02, spec §14). Q-119, Q-205. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `src/modules/tenancy/context/ActiveOrgProvider.tsx`, `src/modules/tenancy/components/{OrgBranchSelector,SuspendedBanner}.tsx`,
  `src/modules/tenancy/hooks/{useOrganizations,useCurrentOrganization}.ts`, `src/lib/api-client.ts`, `src/components/shell/TopBar.tsx`,
  `context/07-frontend-ui-guidelines.md`, tests.
- **Cambios:** `design.md §3.9`; reemplaza `OrgBranchSelectorPlaceholder`. Aplica `design.md §3.10` a `context/07`.
- **Pruebas:** prioridad pestaña → default del BFF → primera por nombre; header en cada request; caché limpia al
  cambiar; `404 organization_not_found`; `409 organization_suspended`.

### T-TEN-30 — Sin organización y aviso de invitaciones (Q-124)
- **AC:** AC-TEN-39 (UI). Q-121, Q-124, Q-205. **Zona roja:** sí (acepta una invitación desde la sesión).
- **Archivos:** `src/app/(dashboard)/sin-organizacion/page.tsx`, `src/modules/tenancy/components/PendingInvitationsNotice.tsx`,
  `src/modules/tenancy/hooks/useMyInvitations.ts`, `src/app/(dashboard)/inicio/page.tsx`, `src/modules/identity/components/NoOrganizationState.tsx`,
  `src/lib/server/env.ts`, `env.example`, `infra/docker-compose.yml`, `backend/tests/config/test_AC_PLT_05_env_example_parity.py`, tests.
- **Cambios:** aviso en "Inicio" y en "sin organización": una persona sin memberships también puede tener invitaciones
  (AC-TEN-31). Sin invitaciones, el aviso no se muestra. El contacto es la variable de servidor `OPERATOR_CONTACT`,
  nunca `NEXT_PUBLIC_` (Q-050): se lee en `lib/server/env.ts`, la página la pasa por prop, y se declara en `env.example`,
  en el Compose y en `FRONTEND_SERVER_VARS`. Sin valor, la página no muestra contacto.
- **Pruebas:** `test_AC_TEN_39` en `PendingInvitationsNotice.test.tsx` (lista, acepta, refresca organizaciones, errores).

### T-TEN-31 — Pantalla `/invitacion`
- **AC:** AC-TEN-17 (UI). **Zona roja:** sí (maneja el token).
- **Archivos:** `src/app/invitacion/page.tsx`, `src/modules/tenancy/components/AcceptInvitation.tsx`, `src/proxy.ts`, tests.
- **Cambios:** `design.md §3.9`: lee `#token`, lo borra de la URL, sobrevive al login con `sessionStorage`.
- **Pruebas:** `test_AC_TEN_17` por estado (válida, vencida, revocada, usada, otro email, suspendida), token que no queda
  ni en la URL ni en `sessionStorage` al terminar.

### T-TEN-32 — Datos de la empresa y abandonar
- **AC:** — (RF-TEN-03, RF-TEN-04, spec §14). **Zona roja:** no.
- **Archivos:** `src/app/(dashboard)/configuracion/empresa/page.tsx`, `src/modules/tenancy/components/{CompanyDataForm,LeaveOrganizationDialog}.tsx`,
  `src/modules/tenancy/hooks/*`, `src/modules/settings/settings-sections.ts`, tests.
- **Pruebas:** solo lectura sin `org.update`; validación zod; `409 last_owner` explicado.

### T-TEN-33 — Sucursales
- **AC:** — (RF-TEN-06, spec §14). **Zona roja:** no.
- **Archivos:** `src/app/(dashboard)/configuracion/sucursales/page.tsx`, `src/modules/tenancy/components/{BranchesTable,BranchFormDialog}.tsx`,
  `src/modules/tenancy/hooks/useBranches.ts`, `settings-sections.ts`, tests.
- **Pruebas:** acciones según `allowed_actions`, `409 conflict` en el formulario, vacío y filtro activas/inactivas.

### T-TEN-34 — Colaboradores: miembros
- **AC:** — (RF-TEN-04, spec §14). **Zona roja:** no.
- **Archivos:** `src/app/(dashboard)/configuracion/colaboradores/page.tsx`, `src/modules/tenancy/components/MembersTable.tsx`,
  `src/modules/tenancy/hooks/useMembers.ts`, `settings-sections.ts`, tests.
- **Pruebas:** sin permiso muestra el estado; acciones por fila según `allowed_actions` y `assignable_roles`.

### T-TEN-35 — Colaboradores: invitaciones y link de una sola vez
- **AC:** AC-TEN-24 (UI). Q-207. **Zona roja:** sí (muestra el token).
- **Archivos:** `src/modules/tenancy/components/{InvitationsTable,InviteDialog,InvitationLinkDialog}.tsx`,
  `src/modules/tenancy/hooks/useInvitations.ts`, tests.
- **Pruebas:** `test_AC_TEN_24` (el link queda en estado local, nunca en la caché de Query), `invitable_roles`, reenviar y revocar.

### T-TEN-36 — E2E y cierre conjunto con SPEC-01
- **AC:** AC-TEN-08, 22, 39. Q-108. **Zona roja:** sí (`scripts/**`).
- **Archivos:** `scripts/e2e_tenancy.py`, `scripts/tests/test_e2e_tenancy.py`, `infra/README.md`.
- **Cambios:** con proveedor falso: crear org por comando → aceptar invitación owner → invitar operator → aceptar en otra
  sesión → el operator ve Sucursales en lectura; y una persona ya existente acepta desde la sesión. Corre a mano, como
  `T-IDA-31`.
- **Pruebas:** `test_AC_TEN_22_e2e_flow`, `test_AC_TEN_08_e2e_two_orgs`, `test_AC_TEN_39_e2e_accept_from_session` con respuestas
  simuladas; la corrida real se registra en `verification.md`.
- **DoD extra:** al mergear, avisar para verificar 01 y 02 en la misma pasada (Q-108).

---
**Hecho:** 36 tareas, 40 AC y 9 RF cubiertos, olas y división de archivos.
**Pendiente / dudas:** Q-220 (SPEC-04/05).
**Siguiente rol sugerido:** `backend-dev` en `T-TEN-01`, en paralelo con la ola 0 de SPEC-01, después `reviewer`.
