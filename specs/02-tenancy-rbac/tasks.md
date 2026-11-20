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
| `TenantModel.save()` exige que coincida con el `TenantContext` activo | Sin tenant activo, `save()`, `delete()` y el `UPDATE`/`INSERT` de `save_base()` de un `TenantModel` fallan cerrado (T-TEN-03). Aceptar una invitación desde la sesión (§4.4) y el puerto `accept_invitations` de SPEC-01, que cruzan organizaciones, abren un `tenant_scope` por organización antes de escribir, y `SystemReason` suma un valor para ese caso | Lo resuelven T-TEN-05 y T-TEN-15. El diseño no lo contradice: el `ContextVar` es justamente lo que lee la guarda de `save()` (ADR-0001) |
| `SystemReason` suma un valor para aceptar una invitación (fila de arriba) | `SystemReason.INVITATION_ACCEPT = "invitation_accept"`: el servicio abre `tenant_scope(system_context(org_de_la_invitación, INVITATION_ACCEPT))`. Chequea la suspensión él mismo con el estado leído bajo el mutex, y la auditoría nombra a la persona como actor (`AuditActor` de usuario), no al sistema. `invitation.expired` sí lleva actor sistema (Q-225). `system_context` entra en `TENANT_QUERY_ALLOWLIST` para ese archivo, con `count=1` (T-TEN-15) | La persona todavía no tiene membership: no hay `UserActor` que construir. Con `SystemActor`, `lock_membership_mutex` no rechaza la suspensión, y AC-TEN-28 pide `409 organization_suspended` |
| `400 invitation_invalid` + `reason` (`design.md §6`) | El sobre `problem+json` de SPEC-00 suma un miembro opcional `reason` (extensión de RFC 9457): lo pone el handler cuando la excepción declara `problem_reason`. Solo `invitation_invalid` lo usa. `title` propio para `invitation_invalid` y `already_member` (T-TEN-15) | El sobre de SPEC-00 (`design.md §3.2.4` de 00) no tenía dónde poner `reason`, y el test de contrato fijaba sus propiedades. Es un cambio compatible: campo opcional, versión menor |
| `Invitation.by_token_hash` se lee desde el servicio (`design.md §4.4`) | `selectors/invitations.py::find_by_token`, que devuelve `InvitationRef(id, organization_id)` (T-TEN-15) | La regla C-01 (`ast_rules.py`) solo deja pasar `TENANT_SCOPES` en `services/`, no los scopes por modelo; los selectors son la capa de lectura. T-TEN-16 y T-TEN-17 suman ahí sus lecturas |
| `TENANT_HEADER = "X-Organization-Id"` entre los settings nuevos (`design.md §3.1`) | Constante `TENANT_HEADER` en `apps/tenancy/api/permissions.py` | El nombre del header es contrato (`design.md §6`), no configuración: un setting permitiría cambiarlo sin cambiar el contrato ni el frontend |
| Toda lista de `design.md §6` como `200 [...]` (p. ej. `GET /api/organizations/` → `200 [{id, name, status, role}]`) | La página de SPEC-00: `{count, next, previous, results: [...]}` con `HubPageNumberPagination`, en toda lista de §6: `GET /api/organizations/` (T-TEN-12), `GET /api/branches/` (T-TEN-24) y las que vengan (`memberships`, `invitations`, `invitations/mine`) | La cabecera de §6 fija la paginación por defecto de SPEC-00 para las listas, como `/api/auth/sessions/`; la tabla de §6 muestra solo la forma de cada fila. Generalizada en la revisión de #124 para no repetir el argumento en cada PR |
| `POST /api/branches/{id}/deactivate/` y `.../reactivate/` (`design.md §6`) | Montadas en `api/urls.py` con `BranchViewSet.as_view({"post": ...})`, no con `@action` (T-TEN-25) | drf-spectacular guarda el `@extend_schema` de una `@action` en los `initkwargs` de `as_view()`, y la suite cross-tenant rechaza todo `initkwarg` que pueda reemplazar la guarda (`classifier.py`). `CurrentOrganizationViewSet` ya se monta así |
| `400 validation_error` al reactivar con el **nombre** ocupado (`design.md §6`, RN-TEN-19) | El mismo `400 validation_error` (código `taken` en el campo) si lo ocupado es el `code` (T-TEN-25) | §6 no da otro código de error para reactivar: el `409 conflict` es de crear y editar. Q-227 hace único el `code` entre activas con la misma regla que el nombre |
| Timeout de lock → `OperationalError` de la BD como `500` (`design.md §11`, T-TEN-11, PR #117) | `503 organization_busy` con `Retry-After: 2` y título fijo "Hay otra operación en curso, probá de nuevo", para todo usuario de `lock_org_for_write` / `lock_membership_mutex`; lo mapea `apps/common/api/exceptions.py` por el SQLSTATE `55P03` (T-TEN-22) | Q-230, decidida por el dueño el 2026-11-20. Código nuevo de contrato (versión menor): `design.md §6` no lo lista |
| `GET /api/memberships/` → `user:{id, email, name}` (`design.md §6`) | `name` es `User.display_name` de SPEC-01 (T-TEN-22) | `User` no tiene un campo `name` |

## Resumen

> T-TEN-01, T-TEN-02, T-TEN-03, T-TEN-04, T-TEN-05, T-TEN-06, T-TEN-07, T-TEN-08, T-TEN-09, T-TEN-10, T-TEN-11, T-TEN-12, T-TEN-13, T-TEN-14, T-TEN-15, T-TEN-16, T-TEN-22, T-TEN-24, T-TEN-25, T-TEN-29 y T-TEN-30 en revisión; las demás sin empezar. La columna **Evidencia** es obligatoria para `✅` y la verifica `scripts/check_spec_state.py`.

| ID | Título | AC | Capa | Archivos esperados (ver detalle) | Depende de | Agente | Tamaño | Zona roja | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|---|---|
| T-TEN-01 | `TenantContext`, `tenant_scope` y errores | — (RF-TEN-01, RF-TEN-08) | Base | `apps/common/tenancy/{context,current,middleware,errors}.py`, `.github/zona-roja-paths.txt` | — | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-01-tenant-context`, sin PR |
| T-TEN-02 | Queryset que falla cerrado + `Organization` + migración 0001 | AC-TEN-11 | DB | `apps/common/tenancy/querysets.py`, `apps/tenancy/models/organization.py` | T-TEN-01 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-02-organization`, sin PR |
| T-TEN-03 | `TenantModel` y app de prueba `tenant_probe` | AC-TEN-07 (guarda), AC-TEN-11 | Base | `apps/common/tenancy/models.py`, `tests/testapps/tenant_probe/` | T-TEN-02 | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-03-tenant-model`, sin PR |
| T-TEN-04 | Test de arquitectura de accesos crudos | AC-TEN-10 | Arquitectura | `backend/tests/architecture/tenant_rules.py`, `test_tenant_queries.py` | T-TEN-03 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-04-raw-access-rules`, PR #104 |
| T-TEN-05 | `Membership` + migración 0002 | — (RN-TEN-07, RN-TEN-21) | DB | `apps/tenancy/models/membership.py`, `apps/common/authz/roles.py` | T-TEN-03, T-IDA-01 | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-05-membership`, sin PR |
| T-TEN-06 | Matriz de permisos como código | AC-TEN-15, AC-TEN-16, AC-TEN-34 (matriz) | Dominio | `apps/common/authz/{actions,checks}.py`, `apps/tenancy/domain/permissions.py` | T-TEN-01, T-TEN-05 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-06-permission-matrix`, PR #105 |
| T-TEN-07 | Reglas de roles (`decide_*`) | AC-TEN-13, AC-TEN-15, AC-TEN-16, AC-TEN-27 (decisión) | Dominio | `apps/tenancy/domain/role_rules.py` | T-TEN-05 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-07-role-rules`, sin PR |
| T-TEN-08 | Resolución de organización por request | AC-TEN-03, AC-TEN-04, AC-TEN-06, AC-TEN-33 | API | `apps/tenancy/api/{permissions,base}.py`, `apps/tenancy/selectors/resolution.py` | T-TEN-05, T-TEN-06, T-IDA-06 | backend-dev | L | Sí | 🟡 | PR #110 |
| T-TEN-09 | Suite cross-tenant parametrizada | AC-TEN-12, AC-TEN-33 | Aislamiento | `backend/tests/cross_tenant/*` | T-TEN-08 | backend-dev | L | Sí | 🟡 | PR #114 |
| T-TEN-10 | Puerto de auditoría y catálogo | AC-TEN-23 (base) | Base | `apps/common/audit/{port,sinks}.py`, `apps/tenancy/domain/audit_events.py` | T-TEN-01 | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-10-audit-port`, sin PR |
| T-TEN-11 | Locks y tareas por organización | AC-TEN-28 (s2s) | Base | `apps/common/tenancy/{locks,celery}.py`, `apps/tenancy/selectors/locks.py` | T-TEN-08 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-11-org-locks`, PR #117 |
| T-TEN-12 | `GET /api/organizations/` y selector para `/api/me` | AC-TEN-08, AC-TEN-21, AC-IDA-21 | API | `apps/tenancy/api/organizations.py`, `selectors/memberships.py`, `services/membership_selector.py` | T-TEN-08, T-IDA-07 | backend-dev | M | Sí | 🟡 | rama `task/T-TEN-12-organizations-list`, PR #113 |
| T-TEN-13 | Datos de la organización activa | AC-TEN-29 (API) | API | `apps/tenancy/api/organizations.py`, `services/organizations.py`, `domain/tax_id.py` | T-TEN-10, T-TEN-11, T-TEN-12 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-13-active-org-data`, sin PR |
| T-TEN-14 | `Invitation` + migración 0003 + reglas puras | AC-TEN-25, AC-TEN-35 (unidad) | DB | `apps/tenancy/models/invitation.py`, `domain/invitations.py` | T-TEN-05 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-14-invitation-model`, sin PR |
| T-TEN-15 | Aceptar invitación con token | AC-TEN-17, AC-TEN-18, AC-TEN-19, AC-TEN-25, AC-TEN-35 | Servicio/API | `services/invitation_accept.py`, `api/invitations.py` | T-TEN-10, T-TEN-11, T-TEN-14 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-15-accept-invitation`, sin PR |
| T-TEN-16 | Mis invitaciones y aceptar desde la sesión (Q-124) | AC-TEN-39, AC-TEN-28, AC-TEN-10 | Servicio/API | `selectors/invitations.py`, `api/invitations.py`, `services/invitation_accept.py` | T-TEN-15 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-16-my-invitations`, sin PR |
| T-TEN-17 | `TenancyInvitationPort` (puerto de SPEC-01) | AC-TEN-17 (vía puerto), AC-IDA-02, AC-IDA-04, AC-IDA-05, AC-IDA-31 | Servicio | `services/invitation_port.py`, `config/settings/base.py` | T-TEN-15, T-IDA-13 | backend-dev | M | Sí | ☐ | |
| T-TEN-18 | Comando `tenancy_create_org` | AC-TEN-22, AC-TEN-40, AC-IDA-32 | Comandos | `services/platform_org.py`, `management/commands/tenancy_create_org.py` | T-TEN-16, T-TEN-17 | backend-dev | L | Sí | ☐ | |
| T-TEN-19 | Comandos de suspensión y primer owner | AC-TEN-28, AC-TEN-29 | Comandos | `management/commands/{tenancy_set_org_status,tenancy_owner_invite}.py` | T-TEN-18 | backend-dev | M | Sí | ☐ | |
| T-TEN-20 | Crear y listar invitaciones | AC-TEN-15, AC-TEN-20, AC-TEN-24, AC-TEN-26, AC-TEN-34 | Servicio/API | `services/invitations.py`, `api/invitations.py`, `api/serializers/invitations.py` | T-TEN-07, T-TEN-15 | backend-dev | L | Sí | ☐ | |
| T-TEN-21 | Reenviar y revocar invitaciones | AC-TEN-02, AC-TEN-15, AC-TEN-24, AC-TEN-26, AC-TEN-37 | Servicio/API | `services/invitations.py`, `api/invitations.py` | T-TEN-20 | backend-dev | M | Sí | ☐ | |
| T-TEN-22 | Listar memberships y cambiar rol | AC-TEN-02, AC-TEN-05, AC-TEN-13, AC-TEN-15, AC-TEN-16, AC-TEN-27, AC-TEN-34 | Servicio/API | `services/memberships.py`, `api/memberships.py` | T-TEN-07, T-TEN-11 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-22-memberships`, sin PR |
| T-TEN-23 | Revocar, abandonar y autorrevocar invitaciones | AC-TEN-04, AC-TEN-13, AC-TEN-14, AC-TEN-15, AC-TEN-31, AC-TEN-36 | Servicio/API | `services/memberships.py`, `api/memberships.py` | T-TEN-21, T-TEN-22 | backend-dev | L | Sí | ☐ | |
| T-TEN-24 | `Branch` + migración 0004 + crear y listar | AC-TEN-07, AC-TEN-16, AC-TEN-30, AC-TEN-38 | DB/API | `models/branch.py`, `services/branches.py`, `api/branches.py` | T-TEN-08, T-TEN-11 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-24-branch-model`, sin PR |
| T-TEN-25 | Ver, editar, desactivar y reactivar `Branch`, filtro | AC-TEN-01, AC-TEN-05, AC-TEN-09, AC-TEN-30, AC-TEN-32, AC-TEN-37, AC-TEN-38 | Servicio/API | `services/branches.py`, `api/branches.py`, `api/filters.py` | T-TEN-24 | backend-dev | L | Sí | 🟡 | rama `task/T-TEN-25-branch-edit`, sin PR |
| T-TEN-26 | Vencimiento de invitaciones y email por flag | AC-TEN-37 | Asíncrono | `apps/tenancy/tasks.py` | T-TEN-11, T-TEN-21 | backend-dev | M | Sí | ☐ | |
| T-TEN-27 | Completitud de auditoría y suspendida genérica | AC-TEN-23, AC-TEN-28 | Aislamiento | `backend/tests/cross_tenant/*`, `apps/tenancy/tests/test_audit_triggers.py` | T-TEN-13, T-TEN-23, T-TEN-25, T-TEN-26 | backend-dev | M | Sí | ☐ | |
| T-TEN-28 | Comandos de soporte y recuperación de owner | AC-TEN-23 (`purpose`) | Comandos | `services/platform_access.py`, `management/commands/{tenancy_support_access,tenancy_owner_recovery}.py` | T-TEN-18 | backend-dev | M | Sí | ☐ | |
| T-TEN-29 | Organización activa en el frontend y selector | — (RF-TEN-02, spec §14) | UI | `src/modules/tenancy/context/ActiveOrgProvider.tsx`, `src/lib/api-client.ts`, `context/07-frontend-ui-guidelines.md` | T-TEN-12, T-IDA-27 | frontend-dev | L | No | 🟡 | rama `task/T-TEN-29-active-org-frontend`, PR #122 |
| T-TEN-30 | Sin organización y aviso de invitaciones (Q-124) | AC-TEN-39 (UI) | UI | `app/(dashboard)/sin-organizacion/page.tsx`, `src/modules/tenancy/components/PendingInvitationsNotice.tsx` | T-TEN-16, T-TEN-29, T-IDA-29 | frontend-dev | M | Sí | 🟡 | rama `task/T-TEN-30-no-org-invitations`, PR #129 |
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
- **Archivos:** `apps/common/tenancy/models.py`, `backend/tests/testapps/__init__.py`,
  `backend/tests/testapps/tenant_probe/{__init__,apps,models}.py` y `migrations/0001_widget.py`,
  `config/settings/test.py`, `backend/tests/tenancy/test_AC_TEN_07_{tenant_model,tenant_updates}.py`. Sumados, con su
  porqué:
  - `apps/common/tenancy/querysets.py`: `TenantManager` (el primero que lo usa es `TenantModel`); `create` y `_insert`
    bajo scope de tenant con la misma regla que `bulk_create` (revisión de T-TEN-02).
  - `apps/tenancy/models/organization.py`: guarda de `save()` del pendiente heredado (abajo).
  - `config/settings/base.py`: `TENANT_MODEL = "tenancy.Organization"` (constante, tabla "Ajustes al diseño").
  - `backend/tests/migrations/test_AC_PLT_17_reversibility.py`: revertir `tenancy` a `zero` también desaplica
    `tenant_probe`, que depende de ella; el conjunto esperado de apps revertidas la suma.
  - `views.py` y `tasks.py` de `tenant_probe` **no** entran acá: los traen `T-TEN-08`/`T-TEN-09` (vista con
    `resolve_branch_filter`) y `T-TEN-11` (`TenantTask`), que son quienes los usan.
- **Cambios:** FK `PROTECT`, `related_name="+"`, guarda de `save()`; `Widget` solo en settings de test.
  - `TenantModel.save()` exige un tenant activo (`tenant_scope`), completa `organization` vacía con el activo y
    rechaza otro; `organization` y `pk` no cambian después de leer o guardar; el `UPDATE` también filtra por
    organización. `delete()` exige tenant activo y verifica que la fila de ese `pk` sea de la organización activa.
  - `organization` lleva `editable=False`: queda fuera de formularios y de `ModelSerializer` (RN-TEN-04).
  - Bajo `for_tenant(ctx)`, `create`/`get_or_create`/`update_or_create`/`bulk_create`/`_insert` completan
    `organization_id` vacío con el del scope y rechazan otro; `_insert` con `on_conflict` falla cerrado. Para
    `Organization` el campo es el `pk`, que nunca está vacío: un scope de tenant no crea organizaciones, se crean con
    `unscoped(reason)`.
  - `for_tenant(ctx).create(...)` además pasa por `save()`, que exige `tenant_scope` activo; `bulk_create` no llama a
    `save()` y solo valida contra el scope del queryset.
  - Revisión del PR #100: `update`/`aupdate`/`_update` con `organization` u `organization_id` entre los valores, y
    `bulk_update`/`abulk_update` con esos campos, fallan cerrado bajo cualquier scope: la organización de una fila no
    cambia nunca por esas vías. `_do_update` y `_do_insert` vuelven a leer `current_tenant()` (sin tenant fallan
    cerrado), exigen que la fila sea de esa organización y el `UPDATE` filtra por ella: cubre `save_base()` directo y un
    receptor `pre_save` que cambie organización y `pk`.
- **Pruebas:** `test_AC_TEN_07_save_rejects_other_org`, `test_AC_TEN_11_tenant_model_without_scope_raises`,
  `test_organization_id_is_immutable`, más `test_AC_TEN_07_save_takes_the_active_organization`,
  `test_AC_TEN_07_create_under_a_tenant_takes_its_organization`,
  `test_AC_TEN_07_bulk_create_under_a_tenant_takes_its_organization`,
  `test_AC_TEN_07_save_with_a_changed_pk_leaves_other_org`, `test_AC_TEN_07_delete_never_reaches_another_org`,
  `test_AC_TEN_11_insert_on_conflict_under_a_tenant_raises`,
  `test_AC_TEN_07_organization_save_with_a_changed_pk_leaves_the_other`, `test_AC_TEN_07_update_never_moves_a_row`
  (una vía por caso, con scope de tenant y `unscoped`), `test_AC_TEN_07_async_update_never_moves_a_row`,
  `test_AC_TEN_07_update_of_other_fields_still_works`, `test_AC_TEN_07_save_base_never_writes_another_org`,
  `test_AC_TEN_07_save_base_without_tenant_raises` y `test_AC_TEN_07_pre_save_receiver_never_writes_another_org`.
- **Pendiente heredado de T-TEN-02 (revisión del PR #89), resuelto acá:** `Organization.save()` con el `pk` cambiado
  (`org.pk = b.pk; org.save()`) sobrescribía la otra organización, porque `save()` usa `_base_manager`. Ahora
  `Organization.save()` rechaza un `pk` distinto del leído y, con un tenant activo, cualquier organización que no sea
  la suya; sin tenant (comandos del operador) crea y actualiza cualquiera.
- **Queda para T-TEN-04:** un queryset sin scope usado como subconsulta (`__in=`), el uso de `_base_manager` /
  `_default_manager`, la llamada directa a `save_base()`, `_save_table()` o `_do_update()`, y `refresh_from_db()` después
  de cambiar el `pk` (lee la fila de otra organización) desde código de negocio no tienen guarda completa en tiempo de
  ejecución: los atrapa el test de arquitectura.

### T-TEN-04 — Test de arquitectura de accesos crudos
- **AC:** AC-TEN-10. RN-TEN-02, RNF-TEN-01. **Zona roja:** sí.
- **Archivos:** `backend/tests/architecture/tenant_rules.py` (nuevo), `ast_rules.py`, `allowlists.py`,
  `test_tenant_queries.py`, `test_AC_PLT_15_no_raw_objects_in_services.py`, `synthetic/charges/services/`. Sumados
  en la revisión del PR #104, por `C-14` (`tenant_rules.py` iba a pasar las 400 líneas):
  `tenant_instance_rules.py` (`refresh_from_db` y `TenantContext`), `tenant_model_rules.py` (reglas sobre el registro
  de Django: herencia y managers) y `test_tenant_models.py` (sus pruebas, con modelos sintéticos en `isolate_apps`).
- **Desvío de tamaño:** el diff queda en unas 1100 líneas contra L ≤ 300. Son solo tests de arquitectura, coherentes
  entre sí; el reviewer del PR #104 no pidió dividirlo, pero pidió dejar el desvío registrado acá.
- **División (`C-14`), obligatoria:** `ast_rules.py` tiene 273 líneas; las reglas nuevas van en `tenant_rules.py`, como
  `money_rules.py`.
- **Cambios:** `X.objects.<attr>` solo con scopes permitidos; `unscoped(` y `TenantContext(` fuera de lista blanca fallan;
  todo modelo de negocio hereda `TenantModel` (exentos: `Organization`, `identity`, auditoría). AC-PLT-15 sigue en verde.
  Desde la revisión del PR #100 (T-TEN-03), la regla también prohíbe en código de negocio `_base_manager`,
  `_default_manager`, `save_base(`, `_save_table(`, `_do_update(` y `refresh_from_db()` sobre una instancia a la que se
  le asignó el `pk`.
- **Pruebas:** `test_AC_TEN_10_raw_manager_fails_naming_the_file` (archivo sintético), `test_AC_TEN_10_scoped_call_passes`,
  `test_AC_TEN_10_unscoped_outside_allowlist_fails`.
- **Implementado:** `tenant_rules.py` revisa `apps/**` salvo `tests/`, `migrations/` y los dos módulos del mecanismo
  (`common/tenancy/{models,querysets}.py`). Prohíbe `X.objects` de un modelo tenant que no abra un scope
  (`allowlists.TENANT_SCOPES`; cubre las subconsultas `__in=`/`Subquery`/`Exists`/`Prefetch` sin scope), los internos de
  persistencia de Django, SQL crudo (`raw`, `extra`, `cursor`, `RawSQL`), `refresh_from_db()` tras re-apuntar el `pk`
  en la misma función y `TenantContext(` fuera de `common/tenancy/` y `tenancy/api/permissions.py`. `unscoped(` va
  contra `UNSCOPED_ALLOWLIST` (la entrada fija modelo y motivo) y la herencia de `TenantModel` se lee del registro de
  Django contra `TENANT_EXEMPT_MODELS`. Los límites que no detecta el AST están en el docstring de `tenant_rules.py`
  (quedan para RLS). C-01 (`ast_rules.py`) deja pasar `X.objects.<scope>(`. Pruebas extra:
  `test_AC_TEN_10_{manager_without_scope,persistence_internals,raw_sql,refresh_after_repointing_the_pk,tenant_context_built_outside_resolution}_fails`,
  `test_AC_TEN_10_unscoped_entry_pins_the_reason`, `test_AC_TEN_10_real_code_has_no_violations`,
  `test_RN_TEN_01_every_business_model_is_a_tenant_model` y `test_AC_PLT_15_only_a_scope_call_opens_the_manager`.
- **Revisión del PR #104 (rechazado sobre `ad7b325`):** un manager plano en un modelo tenant (`all_objects =
  models.Manager()`, o `objects` pisado) saltaba todas las reglas. Ahora un modelo es tenant por herencia (`TenantModel`
  o `settings.TENANT_MODEL`), no por su manager; todo manager de uno (`_meta.managers` y `_default_manager`) debe
  construir un `TenantQuerySet` (`test_AC_TEN_10_extra_plain_manager_on_a_tenant_model_fails`,
  `test_AC_TEN_10_overridden_objects_on_a_tenant_model_fails`), y la regla AST mira todos sus managers. Además:
  `chunked_cursor()`, `<connection>.connection`, `RawQuerySet(`, `QuerySet(`, `Func`/`Aggregate(template=...)` y
  subclases con `template`; `unscoped` sin llamar y `methodcaller('unscoped', ...)`; `TenantContext` como valor (alias,
  `partial`) y `type(x)(...)`/`x.__class__(...)`; alias de import y asignados de modelos tenant y `attrgetter('objects')`;
  la exención de métodos propios vale solo dentro de su clase; `count` en las entradas de la lista blanca (un segundo
  `cursor()` en el mismo archivo falla); las etiquetas de `identity` quedan fijadas en un test; se revisa también
  `config/`. `tenancy.Organization` sale de `TENANT_EXEMPT_MODELS`: ya es tenant por `TENANT_MODEL`.

### T-TEN-05 — `Membership` + migración 0002
- **AC:** — (RN-TEN-07, RN-TEN-21, RNF-TEN-05). **Zona roja:** sí.
- **Archivos:** `models/membership.py`, `migrations/0002_membership.py`, `apps/common/authz/roles.py`, tests
  (`backend/tests/tenancy/test_membership.py`, `test_roles.py`). Sumados, con su porqué:
  - `apps/common/authz/__init__.py`: el paquete nuevo de `roles.py`.
  - `apps/tenancy/models/__init__.py`: exporta `Membership`, como `Organization`.
  - `apps/common/tenancy/context.py`: `UserActor.role` pasa de `str` a `Role` y se valida al construir, como el resto
    del contexto (su docstring lo dejaba para esta tarea).
  - `backend/tests/tenancy/test_{context,audit}.py`: construyen `UserActor` con `Role` en vez de `str`.
- **Cambios:** constraints e índice parcial de §5; `source_invitation` entra en `T-TEN-14`.
  - `membership_end_coherent` suma `ended_reason IS NOT NULL` en la rama `revoked`: tal como la escribe §5,
    `ended_reason IN (...)` da NULL con un motivo NULL y el CHECK lo deja pasar (lo encontró
    `test_RN_TEN_21_end_fields_are_coherent`).
  - Las FK a usuario (`user`, `ended_by`, `invited_by`) son `PROTECT` con `related_name="+"`.
  - `MembershipStatus` y `EndedReason` viven en `models/membership.py`; `Role` y `ROLE_RANK`, en `authz/roles.py`.
- **Fuera:** el scope `Membership.for_user(user_id)` (§3.4) entra con su primer uso, `T-TEN-12`. El valor nuevo de
  `SystemReason` y el `tenant_scope` por organización de la fila "Ajustes al diseño" entran en `T-TEN-15`, el primero
  que escribe memberships de varias organizaciones: acá no hay quien los use (ADR-0011).
- **Pruebas:** `test_RN_TEN_07_one_active_per_org_and_user`, `test_RN_TEN_21_end_fields_are_coherent`,
  `test_RN_TEN_07_two_orgs_are_allowed`, más los rechazos de rol y estado, la membership revocada que se conserva y
  no bloquea una nueva, sin borrado físico (de la membership ni del usuario), la guarda de `TenantModel`, el índice
  parcial con `INCLUDE (role)` y `Role`/`ROLE_RANK`.

### T-TEN-06 — Matriz de permisos como código
- **AC:** AC-TEN-15, 16, 34 (matriz). RN-TEN-09, Q-218, Q-221. **Zona roja:** sí.
- **Archivos:** `apps/common/authz/{actions,checks}.py`, `apps/tenancy/domain/permissions.py`,
  `backend/tests/tenancy/domain/test_permission_matrix_active.py`, `test_permission_matrix_suspended.py`.
  `backend/tests/tenancy/domain/__init__.py` (vacío): el paquete de tests nuevo, como `tests/identity/domain/`.
- **División (`C-14`):** la tabla literal se parte en dos archivos, `active` y `suspended`.
- **Cambios:** `design.md §3.8`; `SUSPENDED_ALLOWED_KINDS` en un solo lugar.
- **Pruebas:** `test_AC_TEN_15_matrix_admin_owner_actions`, `test_AC_TEN_16_matrix_operator_viewer`,
  `test_AC_TEN_34_member_list_denied`, `test_all_actions_declared`.

### T-TEN-07 — Reglas de roles (`decide_*`)
- **AC:** AC-TEN-13, 15, 16, 27 (decisión). RN-TEN-13, RN-TEN-14. **Zona roja:** sí.
- **Archivos:** `apps/tenancy/domain/role_rules.py`, `backend/tests/tenancy/domain/test_role_rules.py`,
  `backend/tests/tenancy/domain/__init__.py` (vacío: el paquete de tests nuevo, como `tests/identity/domain/`).
- **Cambios:** funciones de `design.md §3.8`, incluida `invitations_to_auto_revoke`.
- **Pruebas:** tabla completa `Role × Role × Role × is_self × owners∈{1,2}`: `test_AC_TEN_13_last_owner_decision`,
  `test_AC_TEN_15_admin_never_touches_owner`, `test_AC_TEN_16_no_self_elevation`, `test_AC_TEN_27_transfer_decision`.

### T-TEN-08 — Resolución de organización por request
- **AC:** AC-TEN-03, 04, 06, 33. RF-TEN-01, RN-TEN-03, 06, 08, 20, RNF-TEN-02, RNF-TEN-07. **Zona roja:** sí.
- **Archivos:** `apps/tenancy/api/{permissions,base}.py`, `selectors/resolution.py`, `apps/common/api/problems.py`,
  `backend/tests/tenancy/api/test_resolution.py`.
  - `apps/tenancy/{api,selectors}/__init__.py`: los paquetes no existían.
  - `backend/tests/tenancy/api/{__init__,probe,test_action_permission}.py`: la ruta de prueba (`ProbeViewSet`) y los
    tests de `ActionPermission`/`TenantViewSet`, aparte para que `test_resolution.py` no pase de 400 líneas (`C-14`).
- **Cambios:** `design.md §3.5`; cuerpo constante en el `404`.
  - `X-Organization-Id` es la constante `TENANT_HEADER` de `api/permissions.py`, no un setting: es parte del contrato
    (`design.md §6`) y `config/settings/base.py` no está en esta tarea.
  - El selector lee con `values_list` (una consulta, `JOIN` con `tenancy_organization`) en vez de
    `select_related().only()`; convierte con `Role(...)`/`OrgStatus(...)` y una fila fuera del enum da `None` (`404`)
    y el evento `tenancy.resolution_invalid_row`: falla cerrado.
  - Un header vacío es `400 organization_required`; uno que no es UUID, `404` con el cuerpo de inexistente. El log de
    denegación (`tenancy.access_denied`) lleva `reason`, `user_id` y `requested_organization_id` (solo un UUID ya
    parseado, nunca el header crudo); también lo emiten los `403`/`409` de `ActionPermission`, con `action`.
  - `ActionPermission`: acción sin `ActionSpec` (p. ej. `OPTIONS`, la acción `metadata` de DRF) → `403`; método que
    el viewset no mapea → `405`.
  - Revisión del PR #110: `TenantViewSet.__init_subclass__` también exige `ActionSpec` para cada
    `@<acción>.mapping.<método>` y rechaza un `permission_classes` sin `ResolveTenant` seguido de `ActionPermission` y
    un `get_permissions` propio. Segunda revisión: también rechaza `get_permissions`/`check_permissions` heredados de un mixin puesto
    antes de `TenantViewSet`; `permission_classes` es una tupla, y `check_permissions` vuelve a validarla en cada
    request, así que reasignarla después de importar (`V.permission_classes = ...`, `as_view(permission_classes=...)`)
    da `500` genérico antes de que corra cualquier permiso. Límite: un `dispatch`/`initial` propio que no llame a
    `check_permissions` sigue sin detectarse; lo cubre la suite cross-tenant (`T-TEN-09`).
  - `TenantViewSet` declara `X-Organization-Id` como header requerido en el esquema (`TenantAutoSchema`, `design.md
    §6`). Todavía no hay rutas reales: `openapi.yaml` no cambia.
  - `User` no tiene `is_superuser`/`is_staff` (Q-228): AC-TEN-33 los pone con `monkeypatch` y verifica que la
    resolución no los mira.
  - `backend/tests/architecture/allowlists.py`: `UNSCOPED_ALLOWLIST` suma la entrada de
    `apps/tenancy/selectors/resolution.py` (`Membership.objects.unscoped(UnscopedReason.TENANT_RESOLUTION)`,
    `count=1`), la que `design.md §3.3` prevé desde `T-TEN-04` (PR #104).
- **Pruebas:** `test_AC_TEN_03_foreign_equals_nonexistent`, `test_AC_TEN_04_revoked_membership_with_valid_jwt`,
  `test_AC_TEN_06_missing_header`, `test_AC_TEN_33_superuser_without_membership`,
  `test_RNF_TEN_07_one_query_per_request`, `test_RNF_TEN_02_denial_is_logged`, más
  `test_RN_TEN_03_unknown_role_or_status_is_not_found`, `test_RN_TEN_09_role_outside_the_spec_is_forbidden`,
  `test_RN_TEN_18_write_on_a_suspended_org_is_409`, `test_RN_TEN_09_action_without_spec_fails_at_import`.

### T-TEN-09 — Suite cross-tenant parametrizada
- **AC:** AC-TEN-12, AC-TEN-33. RNF-TEN-01. **Zona roja:** sí.
- **Archivos:** `backend/tests/cross_tenant/{conftest,classifier,harness,test_routes}.py`, `cases/{tenant_probe,tenancy,identity}.py`.
  - `registry.py`: `CrossTenantCase`, `Exemption`, `Seed` y `load()`, que importa cada módulo de `cases/` sin lista a mano.
  - `cases/platform.py`: las rutas de SPEC-00 (`healthz`, `readyz`, `/api/dev/*`) exentas, aparte de las de SPEC-01.
  - `urls.py`: el `ROOT_URLCONF` de test más las rutas de `Widget`; sin tocar `config/urls_dev.py`.
  - `synthetic.py` y `test_walker.py`: endpoints rotos que prueban la red (no hay rutas reales todavía).
- **Cambios:** `design.md §9`. Clasifica también las rutas de 00 y 01 como exentas, con justificación.
  - Recorre `get_resolver()`: toda ruta (no solo `/api/`) es un `TenantViewSet` con un caso por método mapeado, o
    está exenta con motivo; otra cosa falla "sin clasificar". También fallan una exención sin motivo o sin ruta, un
    caso sin ruta y un `TenantViewSet` exento. Las rutas del proveedor OIDC falso son `optional` (solo con `fake`).
  - Red estática para lo que T-TEN-08 no ve: initkwargs de `as_view()` fuera de los del router, y `dispatch`,
    `initial`, `check_permissions` o `get_permissions` distintos de los de `TenantViewSet` (propios o reasignados).
  - Red de comportamiento por (ruta, método): sin header `400`; UUID inexistente y org B `404` con cuerpo idéntico;
    objeto de B con A activa `404`; `WRITE` con A suspendida `409` sin escribir; objeto propio `2xx` (control). En
    cada request, las filas de B no cambian y la respuesta no lleva ids de B. HEAD se prueba por estado.
  - Una ruta exenta con `GET` detrás del login (`IsAuthenticated`) declara `read`: la suite la lee como miembro de A,
    sin header y con el de B, y falla si aparece algo de B, de su owner o de su sesión (exenta no es sin aislamiento).
    Hoy: `/api/me/`, `/api/auth/sessions/` y `GET /api/organizations/` (T-TEN-12, en `cases/tenancy.py`).
  - Sin rutas de negocio aún, `cases/tenant_probe.py` monta un CRUD de `Widget` como ruta real de la suite.
  - AC-TEN-33: el operador es owner de otra organización y `is_superuser`/`is_staff` se ponen con `monkeypatch` (Q-228).
  - `conftest.py` apaga `cache_logger_on_first_use` durante la suite: un logger cacheado acá antes de que
    `tests/logging` reconfigure structlog no llega a un `capture_logs` posterior (rompía 8 tests de 00 y de T-TEN-08).
  - Límites aceptados (revisión del PR #114): la regla de initkwargs es estricta, así que un `@action(serializer_class=...)`
    falla; el walker solo ve las rutas montadas con los settings de test; y la dependencia de orden de structlog en
    `main` (`tests/logging` reconfigura y rompe un `capture_logs` posterior) queda para un seguimiento por Carril O.
  - Revisión del PR #114: `reads_as_a_user` cuenta también un `GET` de las acciones de un `ViewSet`, y la detección de
    fugas de las rutas tenant incluye al owner de B, su email y su sesión (`World.marks_of_b`), como en las exentas.
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
- **Sumados:** `backend/tests/architecture/allowlists.py`: la entrada del único `connection.cursor` de `locks.py`
  (`count=1`), como pide T-TEN-04; `celery.py` no necesita ninguna. `backend/tests/tenancy/locking.py`: el armado
  común de los cuatro archivos de test.
- **Implementado:**
  - `system_context(organization_id, reason)` vive en `common/tenancy/locks.py`, no en `context.py`: lee el estado con
    el mismo SQL crudo que el lock (`common` no importa `Organization`, y su manager exige un `TenantContext`) y
    `context.py` sigue puro. Organización inexistente → `OrganizationNotFound`.
  - `lock_org_for_write`/`ensure_writable` exigen `transaction.atomic()` y que el tenant activo, si hay, sea el mismo.
    `bounded_lock_wait()` pone `lock_timeout = 5s` solo mientras se toma el lock y devuelve el valor anterior. El
    timeout sale como `OperationalError` de la BD (500), sin código de error nuevo.
  - `selectors/locks.py` (revisión del PR #106): `lock_membership_mutex(ctx, kind)` devuelve un `MembershipMutex`
    que exigen `active_owner_count`, `actor_membership` (relee rol y estado del actor) y `lock_membership` (destino
    `FOR NO KEY UPDATE`, `None` si es de otra organización). Fuera de la transacción que tomó el lock fallan con
    `TransactionManagementError`. Con la organización `suspended`, un `WRITE` de usuario o API key da
    `organization_suspended`; `READ`, `REDUCE_ACCESS` y `SystemActor` pasan.
  - `TenantTask` exige `organization_id` como kwarg (UUID o su texto) y abre
    `tenant_scope(system_context(..., CELERY))`. `SystemFanoutTask` corre sin tenant, rechaza `organization_id` y
    `fan_out(task, organization_id, **kwargs)` encola solo `TenantTask`.
  - Pruebas extra: con hilos, escribir después de suspender ve `suspended`, las escrituras no se esperan entre sí ni
    a un cambio de membership, dos cambios de membership sí se esperan y la espera del lock está acotada.
- **Revisión del PR #117 (aprobado sobre `f47d2e4`, 9 no bloqueantes):**
  - Sumados: `backend/tests/architecture/tenant_instance_rules.py` (la regla) y
    `test_restricted_values.py` (sus pruebas). `RESTRICTED_VALUES` extiende la regla de `TenantContext`:
    `system_context` solo en `common/tenancy/{celery,locks}.py` y `MembershipMutex(` solo en
    `tenancy/selectors/locks.py`; una anotación de tipo pasa. Sin token por transacción: la regla AST cierra el
    constructor y los dos huecos documentados siguen igual.
  - `bounded_lock_wait` también restaura `lock_timeout` cuando sale un `DatabaseError` y la transacción sigue
    usable (el error salió de un savepoint interno al bloque); antes quedaba en `5s` (`0 -> 5s`).
  - `TenantTask` no corre dentro de un tenant activo, de otra organización **ni de la misma**: en una request
    cambiaría un usuario, que la suspensión frena, por un actor de sistema, que no. `fan_out` tampoco encola dentro
    de un tenant.
  - Celery confirma el mensaje antes de correr la tarea (`acks_late` apagado): un timeout de lock en una tarea
    termina en `FAILURE` sin reintento. Los consumidores servidor-a-servidor de SPEC-06/07 declaran
    `autoretry_for=(OperationalError,)` con backoff (anotado en el docstring de `celery.py`).
  - Antes de T-TEN-20..23 hay que abrir un `Q-xxx`: un código reintentable para el timeout de lock (`409`/`503` +
    `Retry-After`) sería contrato público. Hoy da `500`.
  - `wait_for_a_blocked_backend` (`tests/identity/test_refresh_concurrency.py`) cuenta cualquier backend de la base
    que espera un lock: vale en la corrida serial de CI, no con pytest en paralelo sobre la misma base.

### T-TEN-12 — `GET /api/organizations/` y selector para `/api/me`
- **AC:** AC-TEN-08, AC-TEN-21, AC-IDA-21. RF-TEN-02, RF-IDA-06. **Zona roja:** sí.
- **Archivos:** `api/organizations.py`, `api/urls.py`, `selectors/memberships.py`, `services/membership_selector.py`,
  `config/settings/base.py`, `openapi.yaml`, `api.d.ts`, tests. Sumados, con su porqué:
  - `apps/common/tenancy/scopes.py` (nuevo) y `querysets.py`: el `ModelScope` que declara un modelo, de solo lectura.
    `UnscopedReason` y la comparación de scopes pasan a `scopes.py` para que `querysets.py` no pase de 400 líneas
    (`C-14`); `querysets.py` reexporta `UnscopedReason`.
  - `apps/tenancy/models/membership.py`: `MembershipQuerySet.for_user(user_id)` (`design.md §3.4`, primer uso).
  - `backend/tests/architecture/{allowlists,tenant_rules}.py`: `MODEL_SCOPES` (modelo → scopes), la regla por modelo
    que pide la nota de T-TEN-04 (PR #104) antes de sumar `for_user`. Revisión del PR #113: la regla también marca
    `_model_scope` fuera de un módulo `models` (encadenado a un scope le cambiaría la etiqueta), y un test exige que
    ningún otro modelo defina un nombre de `MODEL_SCOPES` (la regla confía en el nombre de la clase).
  - `config/urls.py`: monta `apps.tenancy.api.urls` bajo `/api/`.
  - `apps/common/api/schema.py`: `API_VERSION` 0.9.0 (endpoint nuevo) y nombres fijos para los enums `RoleEnum` y
    `OrganizationStatusEnum`, que vuelven en memberships e invitaciones.
  - `backend/tests/identity/test_ports.py`: el selector por defecto deja de ser el stub.
  - `backend/tests/identity/api/test_{login_complete_errors,login_start,logout_view,refresh_view,sessions}.py`: fijan
    `info.version` del contrato, que pasa a 0.9.0 (#111 tomó la 0.8.0).
- **Cambios:** implementa `MembershipSelectorPort`; fija `MembershipSummary`; `POST/PUT/DELETE` → `405`.
  - `MembershipSummary` queda como estaba (`organization_id`, `organization_name`, `role`): el estado de la
    organización lo da `GET /api/organizations/`, la fuente del selector (`design.md §3.9`). `/api/me` no cambia.
  - `for_user` es un `ModelScope`: lee las memberships de un usuario en todas sus organizaciones y rechaza toda
    escritura, `raw` y la combinación con otro scope (`TenantScopeError`). La regla de arquitectura lo deja pasar solo
    en `Membership.objects` (`MODEL_SCOPES`); `TENANT_SCOPES` sigue global (`for_tenant`, `unscoped`).
  - `GET /api/organizations/` es una vista de usuario (`ListAPIView`), no un `TenantViewSet`: es ruta exenta
    (`design.md §3.5`) e ignora `X-Organization-Id`. Usa la sesión del Hub (`RequestAuthContext`, como `/api/me`),
    pagina con `HubPageNumberPagination`, responde `Cache-Control: no-store`, ordena por nombre y después por id, e
    incluye las organizaciones `suspended` con su `status`.
  - La exención de `/api/organizations/` en la suite cross-tenant la registra `T-TEN-09` (`cases/tenancy.py`,
    `EXEMPT`), o esta tarea si `T-TEN-09` se mergea antes.
- **Pruebas:** `test_AC_TEN_08_exactly_my_orgs_and_roles`, `test_AC_TEN_21_no_org_creation_via_api`,
  `test_AC_IDA_21_me_uses_real_selector`, más `test_AC_TEN_08_{header_is_ignored,without_memberships_is_an_empty_list,
  is_paginated,anonymous_is_401}`, `test_AC_TEN_11_for_user_is_read_only`,
  `test_AC_TEN_11_for_user_does_not_mix_with_other_scopes`, `test_AC_TEN_10_model_scope_on_another_model_fails` y
  `test_RF_TEN_02_selector_lists_active_ones_by_name_in_one_query`.

### T-TEN-13 — Datos de la organización activa
- **AC:** AC-TEN-29 (API). RF-TEN-03, Q-209. **Zona roja:** sí.
- **Archivos:** `api/organizations.py`, `api/serializers/organizations.py`, `services/organizations.py`, `domain/tax_id.py`,
  `openapi.yaml`, `api.d.ts`, tests.
  Sumados, con su porqué:
  - `selectors/organizations.py` (nuevo, lo nombra `design.md §3.2`): `get_organization(ctx)` y `lock_organization(ctx)`
    (`FOR NO KEY UPDATE`); la API no toca managers (`design.md §3.3`).
  - `api/urls.py`: monta `organizations/current/`.
  - `apps/common/api/schema.py`: `API_VERSION` 0.10.0 (endpoint nuevo) y el nombre fijo `TenancyActionEnum` para
    `allowed_actions`, que vuelve en memberships e invitaciones.
  - `backend/tests/identity/api/test_{login_complete_errors,login_start,logout_view,refresh_view,sessions}.py` y
    `backend/tests/tenancy/api/test_organizations.py`: fijan `info.version` del contrato, que pasa a 0.10.0.
- **Cambios:** `GET`/`PATCH /api/organizations/current/` en un `TenantViewSet` (`org.read` / `org.update`).
  - El `PATCH` es estricto: una clave que no sea `name`, `legal_name`, `tax_id` o `timezone` (`status`, `id`,
    `organization_id`…) es `400 validation_error` con código `unknown_field` en esa clave; `POST`/`PUT`/`DELETE` son
    `405`. Nadie de la organización cambia su estado por la API (AC-TEN-29).
  - `update_organization` normaliza y valida por su cuenta (recorta espacios; `name` 1–120, `legal_name` ≤200, CUIT
    con dígito verificador, zona horaria de `zoneinfo.available_timezones()`), toma `ensure_writable` y después
    `lock_organization`, guarda solo los campos que cambian y emite `organization.updated` con sus nombres, nunca sus
    valores. Sin cambios: ni escritura ni evento.
  - CUIT (`domain/tax_id.py`): 11 dígitos, sin guiones o como `XX-XXXXXXXX-X`; módulo 11 de AFIP con pesos
    `5 4 3 2 7 6 5 4 3 2`, 11 → 0 y 10 sin CUIT válido. Se guarda sin guiones; vacío lo borra.
  - La respuesta suma `my_role`, `my_membership_id`, `allowed_actions` (las acciones de SPEC-02 que `require` deja
    pasar ahora, con rol y suspensión) e `invitable_roles` (vacía si no puede invitar). `Cache-Control: no-store`.
- **Pruebas:** `test_AC_TEN_29_status_is_not_writable`, `test_RF_TEN_03_owner_and_admin_edit`, `test_tax_id_check_digit`,
  caso `tenancy.py` para `current`, más `test_AC_TEN_29_{no_other_method_changes_the_status,
  owner_of_a_suspended_one_cannot_reactivate_it}`, `test_AC_TEN_28_{suspended_is_read_without_writes,
  suspended_after_the_resolution_is_not_edited,an_edit_in_flight_commits_before_the_suspension,
  an_edit_after_the_suspension_is_rejected}` y `test_RF_TEN_03_two_edits_run_one_after_the_other`.

### T-TEN-14 — `Invitation` + migración 0003 + reglas puras
- **AC:** AC-TEN-25, AC-TEN-35 (unidad). RNF-TEN-03, 05, 06. **Zona roja:** sí.
- **Archivos:** `models/invitation.py`, `models/membership.py` (`source_invitation`), `migrations/0003_invitation.py`,
  `domain/invitations.py`, tests.
- **Cambios:** tabla de §5; `normalize_email` comparte contrato con el de identity, sin importarlo (`domain` puro).
- **Pruebas:** `test_AC_TEN_25_expiry_edge_with_injected_clock`, `test_AC_TEN_35_normalization`,
  `test_RNF_TEN_03_only_hash_is_stored`, `test_one_pending_per_org_and_email`.
- **Nota de T-TEN-04 (revisión del PR #104):** `allowlists.TENANT_SCOPES` es global y
  `test_AC_TEN_10_scopes_are_tenant_queryset_methods` exige que cada scope sea método de `TenantQuerySet`. Los scopes
  declarados por modelo (`Invitation.by_token_hash`, `pending_for_email`, y `Membership.for_user`) necesitan pasar a
  scopes por modelo (modelo → scopes) en la regla y en ese test antes de sumarse; si no, cualquier modelo podría usarlos.
- **Hecho (2026-11-19):** los scopes por modelo ya existen (T-TEN-12, `allowlists.MODEL_SCOPES`), pero esta tarea no
  declara ninguno de `Invitation`: `by_token_hash` llega con su primer lector (`T-TEN-15`) y `pending_for_email` con el
  suyo (`T-TEN-16`/`T-TEN-17`). `normalize_email` es `strip` + `lower`, igual que el de identity (un test compara los dos
  sobre la misma tabla); validar que sea un email (`EmailValidator`, 254) queda en la entrada (`T-TEN-20`, comandos),
  porque `domain/` no importa Django. Suma `invitation_token_hash_sha256` (64 hex en minúscula: un token en claro no
  entra en la columna, RNF-TEN-03) e `invitation_revoked_reason_valid` (enum de §5 como `CHECK`). `token_hash` es
  `varchar(64)` con ese `CHECK` en vez de `char(64)`.

### T-TEN-15 — Aceptar invitación con token
- **AC:** AC-TEN-17, 18, 19, 25, 35. RN-TEN-11, RN-TEN-12. **Zona roja:** sí.
- **Archivos:** `services/invitation_accept.py`, `api/invitations.py`, `api/serializers/invitations.py`, `api/urls.py`,
  `models/invitation.py` (scope `by_token_hash`), `backend/tests/architecture/allowlists.py`, `openapi.yaml`, `api.d.ts`,
  tests.
- **Cambios:** `design.md §4.4`. Servicio único: lo reusan `T-TEN-16` y `T-TEN-17`.
  Abre un `tenant_scope` por organización antes de escribir la membership y suma a `SystemReason` el valor de ese
  caso ("Ajustes al diseño"; T-TEN-05 lo dejó acá).
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
  motivo (nota de T-TEN-04, PR #104: hoy `TENANT_SCOPES` es global; este scope necesita una regla por modelo y por
  archivo, como `UNSCOPED_ALLOWLIST`). Si al releer bajo lock el email ya no coincide, responde `not_found`, sin membership y con `invitation.rejected`
  fuera del `atomic`.
- **Fuera:** UI (`T-TEN-30`).
- **Pruebas:** `test_AC_TEN_39_lists_only_my_email`, `test_AC_TEN_39_response_has_no_token`,
  `test_AC_TEN_39_accept_from_session`, `test_AC_TEN_39_other_email_is_invalid_and_stays_pending`,
  `test_AC_TEN_39_expired_and_suspended_are_not_listed`, `test_AC_TEN_39_foreign_and_missing_same_body`,
  `test_AC_TEN_39_foreign_attempt_is_audited` (`transaction=True`: el evento debe quedar confirmado),
  `test_AC_TEN_28_accept_from_session_is_409`, `test_AC_TEN_39_double_accept_one_membership`,
  `test_AC_TEN_39_accept_vs_revoke_in_parallel` (hilos), `test_AC_TEN_39_email_changed_under_lock_is_not_found`,
  `test_AC_TEN_10_for_session_accept_outside_its_service_fails`.
- **Implementado:** `services/invitation_accept.py::accept_from_session` hace los tres pasos de §4.4: lee con
  `Invitation.objects.for_session_accept(id)` sin transacción ni lock; sin fila o con otro email responde
  `not_found` con el mismo cuerpo, y para una fila ajena emite `invitation.rejected` (`email_mismatch`, actor la
  persona) fuera de toda transacción; el titular sigue por `accept_invitation(..., mismatch=NOT_FOUND)`.
  `selectors/invitations.py::list_my_pending` lee con `Invitation.objects.pending_for_email(email)` (normaliza el
  email) y filtra `expires_at > now` y organización `active`; la lista va paginada como las demás
  (`HubPageNumberPagination`), ordenada por vencimiento e id, y la organización reusa el esquema
  `JoinedOrganization`. La regla por archivo es `tenant_rules.restricted_scope_violations` con
  `allowlists.RESTRICTED_SCOPES` y `RESTRICTED_SCOPE_ALLOWLIST` (símbolo `Invitation.objects.for_session_accept`,
  `count=1`); C-01 suma una entrada `Invitation.objects` con `count=1` para ese servicio. El `POST` no lleva cuerpo:
  cualquier clave es `unknown_field`. `system_context` sigue con una sola aparición (`_accept_context`). La suite
  cross-tenant suma las dos exenciones (la de `mine/` con `read`) y un `Seed` de invitaciones para otro email en
  cada organización. `API_VERSION` 0.13.0. Pruebas extra: `test_AC_TEN_25_expiry_from_the_session_stays_committed`
  (`transaction=True`, revisión del PR #125), `test_AC_TEN_39_foreign_attempt_takes_no_lock`,
  `test_AC_TEN_10_session_scopes_are_read_only` y `test_RN_TEN_12_accept_from_session_takes_no_body`.

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
- **También `deactivate_user` y `reactivate_user`** (`apps/identity`, `T-IDA-18`; decisión de planificación,
  2026-11-14): aplicar la misma validación de `--operator` contra `PLATFORM_OPERATOR_EMAILS`, para que todos los
  comandos de operador sean iguales. Hoy solo exigen un `--operator` no vacío de hasta 150 caracteres.
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
- **Sumados, con su porqué:**
  - `selectors/memberships.py`: `list_members` (perezoso, para el paginador), `get_member` y `count_active_owners`;
    la API no toca managers (`design.md §3.3`).
  - `api/urls.py` (monta `memberships`), `api/base.py` (`ORGANIZATION_BUSY_RESPONSE`, el `503` documentado de Q-230)
    y `apps/common/api/schema.py` (`API_VERSION` 0.15.0; enum `MembershipStatusEnum`).
  - Q-230 (decidida por el dueño el 2026-11-20, primera de T-TEN-20..23): `apps/common/api/{problems,exceptions}.py`
    (`503 organization_busy` + `Retry-After: 2`), el docstring de `apps/common/tenancy/locks.py`, y el `503` en el
    contrato de las demás escrituras que toman esos locks: `api/{branches,organizations,invitations}.py`.
  - Tests que fijan `info.version` (pasa a 0.15.0) y `tests/tenancy/api/membership_setup.py` (armado común).
- **Implementado:**
  - `GET /api/memberships/?status=active|revoked` (por defecto `active`), paginado, por `created_at` e id,
    `Cache-Control: no-store`. Cada fila: `{id, user:{id, email, name}, role, status, ended_reason, created_at,
    allowed_actions, assignable_roles}`; `name` es `User.display_name`. `allowed_actions` = la matriz (rol y
    suspensión) **y** `role_rules` sobre esa fila con los owners activos: `member.change_role` si hay algún rol
    asignable, `member.revoke` en la ajena, `member.leave` en la propia. Una `revoked` no trae ninguna.
  - `PATCH /api/memberships/{id}/` con `{role}` estricto (`unknown_field`). Bajo el mutex: actor releído (revocado →
    `404 organization_not_found`; rol que ya no cambia roles → `403`), destino bloqueado (otra organización, inexistente
    o id no UUID → `404 not_found`; `revoked` → `409 invalid_transition` + `transition.rejected` fuera del `atomic`),
    `decide_role_change`. `LAST_OWNER` → `owner_protection.rejected` fuera del `atomic` + `409 last_owner`.
  - **Paso 3 de §4.2 completo:** degradar auto-revoca las `pending` que emitió esa persona y su rol nuevo ya no
    permite (`inviter_lost_permission`, `revoked_by` = quien degradó, `invitation.auto_revoked`), en la misma
    transacción (AC-TEN-36, solo la degradación; revocar y abandonar siguen en T-TEN-23, que reusa
    `auto_revoke_invitations`). Pruebas: `test_AC_TEN_36_auto_revoked_on_demotion`,
    `test_AC_TEN_36_a_demoted_owner_keeps_what_an_admin_may_issue`.
  - Q-230: `test_Q_230_lock_timeout_is_organization_busy` (espera real sobre la fila de la organización tomada
    `FOR UPDATE`, para cambiar rol, crear sucursal, editar la organización y aceptar invitación) y
    `test_Q_230_only_lock_not_available_is_busy`.
  - `AUDIT_TRIGGERS`: `change_role` registra `membership.role_changed`, `owner_protection.rejected` e
    `invitation.auto_revoked`; `transition.rejected` ya lo registra `reactivate_branch` (T-TEN-25).

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
- **Hecho (2026-11-19):** `GET`/`POST /api/branches/` sobre `TenantViewSet` (`branch.read`, `branch.create`);
  el detalle por id, editar, desactivar y reactivar quedan para `T-TEN-25`. Contrato 0.11.0.
  - El cuerpo del `POST` lo valida el servicio (`services/branches.py::clean_new_branch`), estricto: otra clave
    (`organization_id`, `is_active`, `id`) → `400 validation_error` con `unknown_field` y nada escrito (AC-TEN-07,
    design.md §6), con la misma regla que `T-TEN-13`. `BranchCreateSerializer` solo documenta el contrato; un test
    lo ata a `CREATE_FIELDS`.
  - La unicidad entre activas es de la BD: el `INSERT` corre en un savepoint y el `IntegrityError` de
    `branch_unique_active_name`/`branch_unique_active_code` → `409 conflict` (con `detail` que nombra nombre o código);
    otro `IntegrityError` sube como bug. Sin evento de auditoría en el rechazo.
  - En una transacción: `ensure_writable` (AC-TEN-28), el `INSERT` y `branch.created` con `branch_id`
    (`AUDIT_TRIGGERS`).
  - `GET` lista activas e inactivas (AC-TEN-30), `?is_active=true|false` filtra; paginado con
    `HubPageNumberPagination` (como `GET /api/organizations/`), por nombre y después id. `DELETE`/`PUT` → `405`.
  - Sumados, con su porqué: `models/__init__.py` (exporta `Branch`); `api/urls.py` (monta el router);
    `api/serializers/__init__.py` (paquete nuevo, mismo contenido que el de `T-TEN-13`);
    `apps/common/api/problems.py` (título fijo de `conflict`); `apps/common/api/schema.py` (`API_VERSION` 0.11.0) y
    los tests que fijan `info.version`.
  - `services/fields.py` (nuevo) con `unknown_field_errors`, la regla de cuerpo estricto que ya tenía `T-TEN-13`:
    la usan `services/branches.py`, `services/organizations.py` y `api/serializers/organizations.py` en vez de
    repetirla. El mensaje pasa a uno solo, "Este campo no se acepta."; el código `unknown_field` no cambia.

### T-TEN-25 — Ver, editar, desactivar y reactivar `Branch`, filtro
- **AC:** AC-TEN-01, 05, 09, 30, 32, 37, 38. RF-TEN-06, RN-TEN-16, RN-TEN-19. **Zona roja:** sí.
- **Archivos:** `services/branches.py`, `api/branches.py`, `api/filters.py`, `cases/tenancy.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Pruebas:** `test_AC_TEN_01_other_org_branch_is_404`, `test_AC_TEN_05_demoted_admin_cannot_edit_branch`,
  `test_AC_TEN_09_foreign_branch_filter_is_404`, `test_AC_TEN_30_reactivate_with_taken_name`, `test_AC_TEN_30_no_physical_delete`,
  `test_AC_TEN_32_operator_filters_any_branch`, `test_AC_TEN_37_reactivate_active_is_invalid_transition`,
  `test_AC_TEN_38_patch_to_taken_name`.
- **Hecho (2026-11-20):** `GET`/`PATCH /api/branches/{id}/`, `POST .../deactivate/` y `.../reactivate/` sobre
  `BranchViewSet` (`branch.read`, `branch.update`, `branch.deactivate`, `branch.reactivate`). Contrato 0.14.0.
  - Por id, una sucursal de otra organización, una inexistente y un id que no es UUID dan el mismo `404 not_found`
    (AC-TEN-01). Lee `selectors/branches.py::get_branch(ctx, id)`, que también usan 04/05 (RN-TEN-15); las
    escrituras toman la fila con `lock_branch` (`FOR NO KEY UPDATE`) después de `ensure_writable` (AC-TEN-28).
  - `PATCH` valida el cuerpo en el servicio con la misma regla estricta que el alta (`unknown_field`, también para
    `is_active` y `organization_id`); guarda solo lo que cambia, con `branch.updated` y los nombres de los campos
    (nunca los valores). El `IntegrityError` de las únicas parciales → `409 conflict` (AC-TEN-38).
  - Desactivar pone `is_active` falso y `deactivated_at`; reactivar los devuelve. Nombre o código ocupado al
    reactivar → `400 validation_error` (código `taken`) y sigue inactiva (AC-TEN-30). El estado equivocado →
    `409 invalid_transition` (`apps/tenancy/errors.py`, título propio) y `transition.rejected` con entidad, estado
    y evento, emitido fuera de la transacción (AC-TEN-37, Q-225). `reactivate_branch` es el trigger de
    `transition.rejected` en `AUDIT_TRIGGERS`. `DELETE`/`PUT` por id → `405` (AC-TEN-30).
  - `api/filters.py::resolve_branch_filter(request, ctx)`: `branch_id` de otra organización → `404 not_found`
    (AC-TEN-09); cualquier rol filtra por cualquier sucursal de la organización, activa o no (AC-TEN-32); un valor
    que no es UUID → `400 validation_error`. Lo prueba una vista de test (`test_branch_filter.py`): todavía no hay
    rutas de negocio que filtren por sucursal.
  - `cases/tenancy.py`: los cuatro casos nuevos y, como pidió la revisión de #124, el `POST` armado para B lleva el
    `organization_id` de B.
  - Sumados, con su porqué: `selectors/branches.py` (`get_branch` y `lock_branch`); `apps/tenancy/errors.py`
    (`InvalidTransition`, que reusan memberships e invitaciones); `api/urls.py` (las dos rutas de estado, ver
    "Ajustes"); `api/serializers/branches.py` (`BranchUpdateSerializer`, solo contrato); `apps/common/api/problems.py`
    (título de `invalid_transition`); `apps/common/api/schema.py` (`API_VERSION` 0.14.0) y los tests que fijan
    `info.version`; `tests/identity/test_AC_IDA_32_no_endpoints.py`, que rechazaba todo segmento `deactivate`/
    `reactivate`: ahora los permite solo bajo `branches` (el estado de una sucursal, no de un usuario).

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
  `context/07-frontend-ui-guidelines.md`, tests. Agregados en la implementación (revisión de #122):
  `src/modules/tenancy/lib/active-organization.ts` (lógica pura: prioridad, valor de la pestaña, default del BFF),
  `src/app/(dashboard)/layout.tsx` (lee `__Host-cpu_org` y monta el provider), `src/components/shell/AppShell.tsx`
  (monta `SuspendedBanner`), `src/components/shell/OrgBranchSelectorPlaceholder.tsx` (borrado),
  `src/modules/identity/hooks/useLogout.ts` (el logout borra el valor de la pestaña) y los helpers de tests.
- **Cambios:** `design.md §3.9`; reemplaza `OrgBranchSelectorPlaceholder`. Aplica `design.md §3.10` a `context/07`.
- **Pruebas:** prioridad pestaña → default del BFF → primera por nombre; header en cada request, tomado de la clave
  `['org', orgId, …]` de su query; caché limpia al cambiar; `404 organization_not_found`; `409 organization_suspended`.

### T-TEN-30 — Sin organización y aviso de invitaciones (Q-124)
- **AC:** AC-TEN-39 (UI). Q-121, Q-124, Q-205. **Zona roja:** sí (acepta una invitación desde la sesión).
- **Archivos:** `src/app/(dashboard)/sin-organizacion/page.tsx`, `src/modules/tenancy/components/PendingInvitationsNotice.tsx`,
  `src/modules/tenancy/hooks/useMyInvitations.ts`, `src/app/(dashboard)/inicio/page.tsx`, `src/modules/identity/components/NoOrganizationState.tsx`,
  `src/lib/server/env.ts`, `env.example`, `infra/docker-compose.yml`, `backend/tests/config/test_AC_PLT_05_env_example_parity.py`,
  `scripts/smoke_pages.py`, `scripts/tests/{test_smoke_pages,smoke_stack_fakes}.py` (el smoke espera la redirección de
  `/sin-organizacion` a `/login`; revisión de #129), tests.
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
