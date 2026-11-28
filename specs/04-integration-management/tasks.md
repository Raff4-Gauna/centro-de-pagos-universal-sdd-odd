---
spec: SPEC-04
actualizado: 2026-11-27
---
# Tareas — Módulo de Gestión de Integraciones (integraciones, credenciales, vínculos y Cajas)

Reglas: rebanada vertical · ≤ ~300 líneas de diff · mergeable sola · cita AC · lista archivos esperados · incluye su plan de pruebas.

> Entradas: `spec.sdd.md` **Approved 1.0.0**, `design.md` **Aprobado** (2026-11-27), `clarifications.md` (Q-401…Q-434),
> ADR-0003 **Aceptado**, ADR-0001/ADR-0002 (base de SPEC-02), `context/08-control-de-versiones-ci-cd.md`.
> **Dependencia con SPEC-03 (Q-433):** el motor (`apps/integrations/engine/`: registry, `FieldSpec`/`FieldSchema`,
> `Capability`, `IntegrationContext`/`Credentials`, `ConnectionStatus`, errores con `reason`, `test_connection`,
> `list_stores`/`list_pos`/`ensure_store`/`ensure_pos`, `FakeAdapter`) no tiene diseño ni tareas: SPEC-03 sigue en
> *Draft* 0.3.0. Las tareas que lo consumen están **⛔ Q-433** y dicen qué pieza del motor necesitan; las que no lo
> necesitan (`T-INT-01` a `T-INT-19`) arrancan ya. **Q-433 decidida por el dueño (2026-11-27), opción a):** SPEC-03
> se lleva a *Approved* con su `tasks.md`; cuando existan las tareas de 03, se reemplaza "SPEC-03 (sin *Approved*)"
> por los `T-ENG-NN` reales y esas filas pasan a ☐ en el mismo PR. Hasta entonces siguen ⛔ con Q-433 en Evidencia.
> **Q-434 decidida (2026-11-27), opción a):** `T-INT-43` depende además de un cambio de SPEC-02 que todavía no tiene
> tarea (ver su ficha).
> **Migraciones en serie:** `T-INT-01 → T-INT-02 → T-INT-03 → T-INT-04` (0001 → 0002 → 0003 → 0004). Ninguna otra
> tarea crea migraciones; si alguna lo necesitara, cuelga de la última mergeada y nunca corre en paralelo con otra
> que cree una (dos hojas en `integrations` hacen fallar `makemigrations --check`).

## Convenciones de esta lista
- **Rutas:** relativas a `backend/` salvo que empiecen con `frontend/`, `scripts/`, `infra/` o `specs/`.
  `apps/integrations/` es la app de este módulo (design §3.1); `T-INT-01` la crea y SPEC-03 le suma `engine/` y
  `providers/`.
- **Tamaño** (líneas de diff, **sin** lockfiles ni los generados `specs/_contracts/openapi.yaml` y
  `frontend/src/types/api.d.ts`; las migraciones generadas **sí** cuentan): **S** ≤ 100 · **M** ≤ 200 · **L** ≤ 300.
- **Zona roja = reviewer obligatorio.** Todo `backend/apps/integrations/**`, `backend/**/migrations/**`,
  `backend/config/settings/**`, `backend/tests/architecture/**`, `specs/_contracts/**`, `apps/common/api/{problems,
  schema}.py` y `scripts/**` lo son por `.github/zona-roja-paths.txt`. En el frontend, las pantallas que manejan
  credenciales o el identificador de webhooks se marcan zona roja aunque su ruta no esté en esa lista.
- **Ninguna tarea toca `.github/workflows/`** (Q-063). Si una lo necesitara, para y lo reporta.
- **DoD de todo endpoint tenant-scoped:** registra su `CrossTenantCase` en el archivo de casos que le toca (ver
  `C-14` abajo) en el mismo PR; si no, `backend/tests/cross_tenant/test_routes.py` falla. Corre `export_openapi` y
  `openapi:types`, commitea el resultado y sube `API_VERSION` menor (ADR-0005, design §6.5).
- **DoD de toda tarea de servicio:** emite sus eventos (`IntegrationsAuditAction`) dentro de la transacción, los
  rechazos auditables (`transition.rejected`) fuera, y registra cada evento en `AUDIT_TRIGGERS`.
- **DoD de todo código que toque credenciales:** valores sintéticos (`fake-secret-…`), nunca los de `context/09` ni
  `context/10`; ningún valor secreto en logs, errores, auditoría ni `repr` (RNF-INT-01).
- **Tests:** en `backend/tests/integrations/{domain,services,api,commands,security}/`, nombrados
  `test_AC_INT_NN_<caso>`; lo que no tiene AC propio se nombra por su RN, RF o Q. Un archivo de tests por AC o por
  grupo chico, para no pasar las ~400 líneas.
- **C-14 (≤ ~400 líneas por archivo), divisiones fijadas de antemano:**
  - `config/settings/env.py` tiene **357** líneas: `T-INT-06` le suma solo los dos campos `SecretStr` (≤ 10 líneas);
    el parseo y la validación del llavero van en `apps/integrations/keyring.py`.
  - Suite cross-tenant en **tres** archivos: `backend/tests/cross_tenant/cases/integrations.py` (`/api/integrations/**`
    e `/api/integration-providers/`), `cases/branch_links.py` y `cases/cash_registers.py` (`cases/tenancy.py` llega a
    268 líneas con ~20 rutas; las ~24 de este módulo en un solo archivo pasarían de 400).
  - `frontend/src/modules/tenancy/components/BranchesTable.tsx` tiene **342** líneas: el enlace a la sucursal va en un
    componente nuevo `BranchDetailLink.tsx` y la tabla solo lo importa y lo usa (≤ 5 líneas).
  - Estimaciones de design §3.2 que crecen en varias tareas: `services/integration_lifecycle.py` (~240: T-INT-10,
    T-INT-11, T-INT-34), `services/branch_links.py` (~220: T-INT-17, T-INT-37), `services/cash_registers.py` (~230:
    T-INT-19, T-INT-39), `api/integration_actions.py` (~210: T-INT-13, T-INT-29, T-INT-32, T-INT-33),
    `selectors/usability.py` (~150: T-INT-18, T-INT-35), `apps/integrations/checks.py` (~120: T-INT-06, T-INT-11,
    T-INT-21). Si alguno pasa de ~300 al implementarlo, se parte por caso de uso antes de seguir (design §3.2).

### Estados de una tarea
Los de `specs/00-platform/tasks.md`: ☐ pendiente · 🔄 en curso · 🟡 en revisión · ✅ mergeada (PR **y** SHA) · 🧪 verificada
· ⛔ bloqueada (`Q-xxx`). Camino: `☐ → 🔄 → 🟡 → ✅ → 🧪`. La fila se actualiza en el mismo PR que cambia el estado.

## Ramas, PR y merge
- **Prerrequisito:** esta lista se mergea a `main` antes de abrir `task/T-INT-…`. El commit que la mergea **no** nombra
  ningún `T-INT-NN` en el asunto (`check_spec_state.py` lo tomaría como una tarea mergeada).
- Cada tarea en `task/T-INT-NN-slug` desde `main` actualizado; un PR por tarea; merge squash con
  `--match-head-commit <sha>`. Quién mergea: Q-057 (`AGENTS.md`).
- **Antes de `T-INT-49` y `T-INT-50`** (pantalla de sucursales): alinear Q-220 en los textos de 02 y en `context/07`
  (design §11.3, tablero §3), en un PR de documentos aparte. No es una tarea de este módulo.

## Ajustes al diseño
Donde el diseño y el código de `main`, o el orden real, difieren, manda esta tabla.

| `design.md` dice | Se implementa | Por qué |
|---|---|---|
| Tests en `apps/integrations/tests/` (§3.2) | Tests en `backend/tests/integrations/{domain,services,api,commands,security}/` | Es la convención del repo (`backend/tests/tenancy/`) y `scripts/check_spec_state.py` solo busca tests en `backend/tests/**`: en otro lugar, los AC figurarían sin test |
| Llavero como `SecretStr` en `config/settings/env.py` (§3.4) | Solo los dos campos en `env.py`; el parseo `id:clave`, la validación y el `Keyring` en `apps/integrations/keyring.py` | `env.py` tiene 357 líneas (`C-14`) |
| Orden de §11.4 en 18 tareas | 52 tareas: todo lo que no usa el motor primero (las cuatro migraciones al principio, cifrado, dominio, ciclo de vida sin API, identificador de webhooks, re-cifrado, lectura y ciclo de vida de vínculos y Cajas), después lo que usa el motor | Tope de ~300 líneas por tarea y Q-433: SPEC-03 sin diseño |
| Ciclo de vida en una tarea (§11.4 punto 9) | Servicios sin motor (`T-INT-10`, `T-INT-11`), API (`T-INT-33`) y reactivar una desconectada con juego nuevo (`T-INT-34`) | La respuesta `200 Integration` lleva `capabilities[]` y `provider_available` del registry (§6.5); reactivar una desconectada llama a `test_connection` |
| `BranchLink` y `CashRegister` con sus servicios (§11.4 puntos 13 y 14) | Modelos y migraciones primero (`T-INT-03`, `T-INT-04`); lectura y ciclo de vida sin proveedor (`T-INT-16` a `T-INT-19`); altas con proveedor después (`T-INT-37` a `T-INT-40`) | Las altas necesitan `field_schema.branch_link`, `POS_MANAGEMENT` y `ensure_*`/`list_*` del motor; leer, desactivar y reactivar no |
| `get_usable_cash_register`: Caja activa, de esa integración, `Branch` activa y vínculo activo (§3.7) | Además exige la integración `status='active'` | AC-INT-46 pide que el selector no devuelva las Cajas "hasta que la integración y la `Branch` vuelvan a estar activas" |
| Listas como `200 [...]` (§6.1) | Página de SPEC-00 `{count, next, previous, results}` (`HubPageNumberPagination`) en toda lista del módulo | La cabecera de §6 fija la paginación por defecto de SPEC-00; mismo ajuste que SPEC-02 (revisión de #124) |
| `POST …/{acción}/` del ciclo de vida, de vínculos y de Cajas | Montadas en `api/urls.py` con `ViewSet.as_view({"post": ...})`, no con `@action` | La suite cross-tenant rechaza `initkwargs` que reemplacen la guarda (`classifier.py`); mismo ajuste que T-TEN-25 |
| Test de rutas sin OAuth en la suite final (§9) | En `T-INT-13`, la primera tarea que agrega rutas; `T-INT-42` lo vuelve a correr sobre todas | Corre sobre todas las rutas registradas: conviene tenerlo desde la primera |
| Un solo `apps/common/api/schema.py` sin cambios | `ENUM_NAME_OVERRIDES` suma los enums del módulo (`IntegrationStatusEnum`, `ConnectionStatusEnum`, `IntegrationsActionEnum`, …) en la tarea que los expone primero | Los `status` y `allowed_actions` de 04 chocarían con los nombres de enum de SPEC-02 (`schema.py`, comentario de `ENUM_NAME_OVERRIDES`) |

## Resumen

> 52 tareas: 19 ☐ que no usan el motor (`T-INT-01` a `T-INT-19`) y 33 ⛔ que esperan a SPEC-03 (Q-433, decidida a):
> esperan a las `T-ENG-NN`; `T-INT-43` también al cambio de SPEC-02 de Q-434 a)). Ninguna está mergeada. La columna **Evidencia** es obligatoria para `✅` y para `⛔` y la verifica
> `scripts/check_spec_state.py`.

| ID | Título | AC | Capa | Archivos esperados (ver detalle) | Depende de | Agente | Tamaño | Zona roja | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|---|---|
| T-INT-01 | App `integrations` + `Integration` + migración 0001 | AC-INT-28 (constraint), AC-INT-29 (índice), AC-INT-38 (índice), AC-INT-41 (unicidad) | DB | `apps/integrations/{apps,models/integration}.py`, `migrations/0001_integration.py`, `config/settings/base.py` | — | backend-dev | L | Sí | 🔄 | rama `task/T-INT-01-integration-model` |
| T-INT-02 | `CredentialSet` + migración 0002 con FK compuesta | — (RN-INT-06, RN-INT-13) | DB | `models/credential_set.py`, `migrations/0002_credential_set.py` | T-INT-01 | backend-dev | M | Sí | ☐ | — |
| T-INT-03 | `BranchLink` + migración 0003 con FK compuestas | AC-INT-34 (constraint), AC-INT-43 (constraint) | DB | `models/branch_link.py`, `migrations/0003_branch_link.py` | T-INT-02 | backend-dev | M | Sí | ☐ | — |
| T-INT-04 | `CashRegister` + migración 0004 con FK compuesta al vínculo | AC-INT-19 (constraint) | DB | `models/cash_register.py`, `migrations/0004_cash_register.py` | T-INT-03 | backend-dev | M | Sí | ☐ | — |
| T-INT-05 | Cifrado AES-256-GCM y llavero (dominio, ADR-0003) | AC-INT-44 (cifrado) | Dominio | `apps/integrations/keyring.py`, `domain/credential_cipher.py` | T-INT-01 | backend-dev | L | Sí | ☐ | — |
| T-INT-06 | Llavero en settings, system checks y `integrations_generate_key` | AC-INT-08 | Base | `config/settings/{env,base,test,prod}.py`, `apps/integrations/checks.py`, `management/commands/integrations_generate_key.py`, `env.example`, `infra/docker-compose.ci.yml` | T-INT-02, T-INT-05 | backend-dev | M | Sí | ☐ | — |
| T-INT-07 | Matriz de permisos y catálogo de auditoría | AC-INT-11 (matriz), AC-INT-21 (matriz), AC-INT-23 (catálogo) | Dominio | `domain/{permissions,audit_events}.py`, `services/audit.py` | T-INT-01 | backend-dev | M | Sí | ☐ | — |
| T-INT-08 | Máquinas de estado, nombres y claves externas | AC-INT-25 (decisión), AC-INT-28 (normalización), AC-INT-43 (transiciones) | Dominio | `domain/{lifecycle,names,external_keys}.py` | T-INT-01 | backend-dev | M | Sí | ☐ | — |
| T-INT-09 | Decisión de la prueba de conexión (`decide_save` / `decide_manual_test`) | AC-INT-13, AC-INT-31, AC-INT-36, AC-INT-37, AC-INT-42, AC-INT-45 (decisión) | Dominio | `domain/{connection,errors}.py` | T-INT-01 | backend-dev | L | Sí | ☐ | — |
| T-INT-10 | Desactivar y reactivar una integración inactiva (servicio) | AC-INT-25 (servicio), AC-INT-28 (reactivar), AC-INT-33 (reactivar sin juego), AC-INT-38 (desactivar) | Servicio | `services/integration_lifecycle.py`, `selectors/integrations.py`, `apps/integrations/errors.py` | T-INT-02, T-INT-07, T-INT-08 | backend-dev | M | Sí | ☐ | — |
| T-INT-11 | `PendingChargesPort` y desconectar (servicio) | AC-INT-25 (desconectar), AC-INT-33 (desconectar), AC-INT-38 (desconectar) | Servicio | `services/{ports,integration_lifecycle}.py`, `apps/integrations/checks.py`, `config/settings/base.py` | T-INT-04, T-INT-10 | backend-dev | L | Sí | ☐ | — |
| T-INT-12 | Búsqueda por identificador de webhooks para SPEC-07 | AC-INT-41 (búsqueda) | Selector | `selectors/webhook_routing.py`, `models/integration.py`, `tests/architecture/allowlists.py` | T-INT-01 | backend-dev | S | Sí | ☐ | — |
| T-INT-13 | Regenerar el identificador de webhooks (primera ruta del módulo) | AC-INT-10 (regenerar), AC-INT-11 (regenerar), AC-INT-12, AC-INT-17 (regenerar), AC-INT-22, AC-INT-41 (regenerar) | Servicio/API | `services/webhook_key.py`, `api/{urls,base,integration_actions}.py`, `config/urls.py`, `tests/cross_tenant/cases/integrations.py` | T-INT-07, T-INT-10, T-INT-12 | backend-dev | L | Sí | ☐ | — |
| T-INT-14 | Re-cifrado por organización (servicio) | AC-INT-44 (re-cifrado) | Servicio | `services/reencrypt.py`, `tests/architecture/allowlists.py` | T-INT-06, T-INT-07 | backend-dev | L | Sí | ☐ | — |
| T-INT-15 | Comando `integrations_reencrypt_credentials` y `--check` | AC-INT-44 (comando y `--check`) | Comandos | `management/commands/integrations_reencrypt_credentials.py` | T-INT-14 | backend-dev | M | Sí | ☐ | — |
| T-INT-16 | Vínculos: listar y ver | AC-INT-20 (vínculos), AC-INT-21 (leer vínculos), AC-INT-34 (listado) | Selector/API | `selectors/branch_links.py`, `api/{branch_links,serializers/branch_links}.py`, `tests/cross_tenant/cases/branch_links.py` | T-INT-03, T-INT-07, T-INT-13 | backend-dev | M | Sí | ☐ | — |
| T-INT-17 | Vínculos: desactivar y reactivar | AC-INT-17 (vínculo), AC-INT-20 (escrituras), AC-INT-21 (desactivar), AC-INT-34 (desactivar), AC-INT-43 (reactivar), AC-INT-46 (reactivar vínculo) | Servicio/API | `services/branch_links.py`, `api/branch_links.py`, `api/urls.py` | T-INT-08, T-INT-16 | backend-dev | M | Sí | ☐ | — |
| T-INT-18 | Cajas: listar, ver y "Caja utilizable" | AC-INT-17 (leer Cajas), AC-INT-18 (Caja), AC-INT-20 (Cajas), AC-INT-21 (leer Cajas), AC-INT-40 (selector) | Selector/API | `selectors/{cash_registers,usability}.py`, `api/{cash_registers,serializers/cash_registers}.py`, `tests/cross_tenant/cases/cash_registers.py` | T-INT-04, T-INT-16 | backend-dev | L | Sí | ☐ | — |
| T-INT-19 | Cajas: editar, desactivar y reactivar | AC-INT-17 (Cajas), AC-INT-20 (escrituras), AC-INT-21 (escrituras), AC-INT-46 (reactivar Caja) | Servicio/API | `services/cash_registers.py`, `api/cash_registers.py`, `api/urls.py` | T-INT-08, T-INT-18 | backend-dev | L | Sí | ☐ | — |
| T-INT-20 | Validación contra el esquema del adaptador | AC-INT-05 (dominio) | Dominio | `domain/field_validation.py` | T-INT-01, SPEC-03 (sin *Approved*) | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-21 | Catálogo de providers y *feature flags* por provider | AC-INT-11 (catálogo), AC-INT-26, AC-INT-27 | Selector/API | `selectors/catalog.py`, `api/{providers,serializers/catalog}.py`, `apps/common/feature_flags.py`, `apps/integrations/checks.py` | T-INT-13, T-INT-20, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-22 | Listado y detalle por rol | AC-INT-06, AC-INT-10 (GET), AC-INT-12 (lecturas), AC-INT-17 (leer), AC-INT-30, AC-INT-41 (detalle) | Selector/API | `api/{integrations,representation,serializers/integrations}.py`, `selectors/integrations.py`, `apps/common/api/schema.py` | T-INT-21, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-23 | `GET /api/integrations/{id}/capabilities/` | AC-INT-10 (capacidades), AC-INT-15, AC-INT-30 (capacidades) | API | `api/integrations.py`, `selectors/catalog.py` | T-INT-22 | backend-dev | S | Sí | ⛔ | Q-433 |
| T-INT-24 | Servicio de alta y escritura del juego (`writes.py`) | AC-INT-01, AC-INT-03, AC-INT-04 (validación), AC-INT-05, AC-INT-28, AC-INT-29, AC-INT-31 (alta), AC-INT-38 (alta) | Servicio | `services/{create_integration,writes}.py`, `apps/integrations/errors.py` | T-INT-06, T-INT-09, T-INT-20, T-INT-21, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-25 | `POST /api/integrations/` | AC-INT-01 (API), AC-INT-02, AC-INT-11 (crear), AC-INT-17 (crear) | API | `api/integrations.py`, `apps/common/api/problems.py` | T-INT-22, T-INT-24 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-26 | Resolución de credenciales (`resolve_integration_context`) | AC-INT-04 (contexto), AC-INT-16, AC-INT-17 (sistema), AC-INT-18 (sistema), AC-INT-44 (resolución) | Servicio | `services/resolve_context.py`, `selectors/credentials.py` | T-INT-24, SPEC-03 (sin *Approved*) | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-27 | `provider_session` y `ProviderAuthError` en una operación real | AC-INT-32 | Servicio | `services/{provider_gateway,auth_failure}.py` | T-INT-26, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-28 | Servicio de prueba de conexión a pedido | AC-INT-13, AC-INT-14, AC-INT-36, AC-INT-45 (prueba) | Servicio | `services/test_connection.py` | T-INT-09, T-INT-26, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-29 | `POST …/test-connection/` y throttle | AC-INT-10 (probar), AC-INT-11 (probar), AC-INT-13 (API), AC-INT-14 (timeout), AC-INT-17 (probar) | API | `api/{integration_actions,throttling}.py`, `config/settings/base.py`, `apps/common/api/problems.py` | T-INT-22, T-INT-28 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-30 | `PATCH /api/integrations/{id}/` (datos no secretos) | AC-INT-10 (PATCH), AC-INT-11 (editar), AC-INT-17 (editar), AC-INT-31 (editar sin prueba) | Servicio/API | `services/update_integration.py`, `api/integrations.py` | T-INT-20, T-INT-22 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-31 | Servicio de reemplazo de credenciales | AC-INT-09, AC-INT-31 (reemplazo), AC-INT-37, AC-INT-44 (reemplazo), AC-INT-45 (reemplazo) | Servicio | `services/replace_credentials.py`, `services/writes.py` | T-INT-24, T-INT-26 | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-32 | `PUT /api/integrations/{id}/credentials/` | AC-INT-10 (reemplazar), AC-INT-11 (reemplazar), AC-INT-17 (reemplazar) | API | `api/integration_actions.py`, `apps/common/api/problems.py` | T-INT-22, T-INT-31 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-33 | API del ciclo de vida (desactivar, reactivar, desconectar; sin `DELETE`) | AC-INT-10 (ciclo de vida), AC-INT-11 (ciclo de vida), AC-INT-17 (ciclo de vida), AC-INT-25 (API), AC-INT-33 (API) | API | `api/{integration_actions,urls}.py`, `apps/common/api/problems.py` | T-INT-11, T-INT-22 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-34 | Reactivar una desconectada con un juego nuevo | AC-INT-28 (reactivar), AC-INT-33 (reactivar), AC-INT-42, AC-INT-45 (reactivación) | Servicio/API | `services/integration_lifecycle.py`, `api/integration_actions.py` | T-INT-31, T-INT-33 | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-35 | "Integración utilizable" y lock del cobro nuevo | AC-INT-18 (integración), AC-INT-36 (selector), AC-INT-45 (selector y lock) | Selector | `selectors/{usability,locks}.py`, `tests/architecture/allowlists.py` | T-INT-21, T-INT-31, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-36 | `provider_session` con `NewChargeLock` | AC-INT-45 (concurrencia) | Servicio | `services/provider_gateway.py` | T-INT-27, T-INT-35 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-37 | Servicio de alta de vínculo (crear, importar, manual, sin referencia) | AC-INT-34 (alta), AC-INT-39, AC-INT-43 (alta duplicada), AC-INT-46 (vínculo) | Servicio | `services/branch_links.py` | T-INT-17, T-INT-20, T-INT-27, SPEC-03 (sin *Approved*) | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-38 | `POST /api/branch-links/` y `GET …/provider-stores/` | AC-INT-10 (Stores), AC-INT-11 (Stores), AC-INT-17 (crear vínculo), AC-INT-21 (crear vínculo), AC-INT-34 (de otra organización) | API | `api/branch_links.py`, `services/provider_lookup.py`, `api/integration_actions.py`, `apps/common/api/problems.py` | T-INT-22, T-INT-37 | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-39 | Servicio de alta de Caja (crear, importar, manual) | AC-INT-19, AC-INT-35, AC-INT-40 (sin Caja nueva), AC-INT-46 (Caja) | Servicio | `services/cash_registers.py` | T-INT-19, T-INT-37 | backend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-40 | `POST /api/cash-registers/` y `GET /api/branch-links/{id}/provider-pos/` | AC-INT-11 (POS), AC-INT-17 (crear Caja), AC-INT-19 (de otra organización), AC-INT-21 (crear Caja) | API | `api/{cash_registers,branch_links}.py`, `services/provider_lookup.py`, `apps/common/api/problems.py` | T-INT-38, T-INT-39 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-41 | Suite de secretos (RNF-INT-01) | AC-INT-07, AC-INT-08 (otros caminos) | Seguridad | `backend/tests/integrations/security/test_no_secret_leaks.py` | T-INT-25, T-INT-29, T-INT-32, T-INT-33 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-42 | Completitud: cross-tenant, suspendida, auditoría y rutas | AC-INT-10, AC-INT-12, AC-INT-17, AC-INT-20, AC-INT-22, AC-INT-23, AC-INT-24 | Aislamiento | `backend/tests/cross_tenant/cases/*`, `backend/tests/integrations/test_audit_triggers.py` | T-INT-23, T-INT-30, T-INT-34, T-INT-36, T-INT-40, T-INT-41 | backend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-43 | Frontend: lista de integraciones y entrada de Configuración | — (RF-INT-03, spec §14) | UI | `frontend/src/app/(dashboard)/configuracion/integraciones/page.tsx`, `frontend/src/modules/integrations/{components/IntegrationsScreen,components/IntegrationCard,hooks/useIntegrations}.tsx`, `frontend/src/modules/settings/settings-sections.ts` | T-INT-22, cambio de SPEC-02 por Q-434 (sin tarea todavía) | frontend-dev | M | No | ⛔ | Q-433 · Q-434 |
| T-INT-44 | Frontend: `SchemaFields` y `schema-to-zod` | — (RF-INT-01, RN-INT-07) | UI | `frontend/src/modules/integrations/{lib/schema-to-zod.ts,components/SchemaFields.tsx}` | T-INT-21 | frontend-dev | M | Sí | ⛔ | Q-433 |
| T-INT-45 | Frontend: alta de integración | — (RF-INT-02, spec §14 "Alta") | UI | `frontend/src/modules/integrations/{components/CreateIntegrationDialog.tsx,hooks/useProviderCatalog.ts,hooks/useIntegrationMutations.ts}` | T-INT-25, T-INT-43, T-INT-44 | frontend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-46 | Frontend: detalle y "Probar conexión" | — (RF-INT-03, RF-INT-05) | UI | `frontend/src/app/(dashboard)/configuracion/integraciones/[id]/page.tsx`, `frontend/src/modules/integrations/{components/IntegrationDetailScreen.tsx,components/ConnectionTestButton.tsx,lib/connection-messages.ts}` | T-INT-29, T-INT-43 | frontend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-47 | Frontend: identificador de webhooks (Copiar, Regenerar) | — (RF-INT-14) | UI | `frontend/src/modules/integrations/components/WebhookKeyPanel.tsx` | T-INT-13, T-INT-46 | frontend-dev | S | Sí | ⛔ | Q-433 |
| T-INT-48 | Frontend: reemplazar credenciales y ciclo de vida | — (RF-INT-04, RF-INT-06) | UI | `frontend/src/modules/integrations/components/{CredentialsDialog,IntegrationLifecycleDialogs}.tsx` | T-INT-32, T-INT-34, T-INT-44, T-INT-46 | frontend-dev | L | Sí | ⛔ | Q-433 |
| T-INT-49 | Frontend: detalle de sucursal con sus vínculos | — (RF-INT-10, spec §14 "Sucursales y cajas") | UI | `frontend/src/app/(dashboard)/configuracion/sucursales/[id]/page.tsx`, `frontend/src/modules/integrations/components/{BranchDetailScreen,BranchLinksPanel,BranchLinkDialog}.tsx`, `frontend/src/modules/tenancy/components/{BranchesTable,BranchDetailLink}.tsx` | T-INT-17, T-INT-38, T-INT-44 | frontend-dev | L | No | ⛔ | Q-433 |
| T-INT-50 | Frontend: Cajas de la sucursal | — (RF-INT-09, spec §14 "Sucursales y cajas") | UI | `frontend/src/modules/integrations/{components/CashRegistersTable.tsx,components/CashRegisterDialog.tsx,hooks/useCashRegisters.ts}` | T-INT-19, T-INT-40, T-INT-49 | frontend-dev | L | No | ⛔ | Q-433 |
| T-INT-51 | Frontend: tarjetas de integraciones en Inicio | — (RF-INT-03, spec §14 "Inicio") | UI | `frontend/src/modules/integrations/components/IntegrationStatusCards.tsx`, `frontend/src/app/(dashboard)/inicio/page.tsx` | T-INT-22 | frontend-dev | S | No | ⛔ | Q-433 |
| T-INT-52 | Humo E2E por HTTP con `FakeAdapter` | AC-INT-01 (humo), AC-INT-33 (humo), AC-INT-35 (humo) | E2E | `scripts/e2e_integrations.py`, `scripts/tests/test_e2e_integrations.py` | T-INT-34, T-INT-40, T-INT-42 | backend-dev | M | Sí | ⛔ | Q-433 |

## Cobertura AC → tareas
| AC | Tareas |
|---|---|
| AC-INT-01 | T-INT-24, T-INT-25, T-INT-52 |
| AC-INT-02 | T-INT-25 |
| AC-INT-03 | T-INT-24 |
| AC-INT-04 | T-INT-24 (validación), T-INT-26 (contexto) |
| AC-INT-05 | T-INT-20 (dominio), T-INT-24 (servicio) |
| AC-INT-06 | T-INT-22 |
| AC-INT-07 | T-INT-41 |
| AC-INT-08 | T-INT-06, T-INT-41 |
| AC-INT-09 | T-INT-31 |
| AC-INT-10 | T-INT-13, T-INT-22, T-INT-23, T-INT-29, T-INT-30, T-INT-32, T-INT-33, T-INT-38, T-INT-42 |
| AC-INT-11 | T-INT-07, T-INT-13, T-INT-21, T-INT-25, T-INT-29, T-INT-30, T-INT-32, T-INT-33, T-INT-38, T-INT-40 |
| AC-INT-12 | T-INT-13, T-INT-22, T-INT-42 |
| AC-INT-13 | T-INT-09 (decisión), T-INT-28, T-INT-29 |
| AC-INT-14 | T-INT-28, T-INT-29 |
| AC-INT-15 | T-INT-23 |
| AC-INT-16 | T-INT-26 |
| AC-INT-17 | T-INT-13, T-INT-17, T-INT-18, T-INT-19, T-INT-22, T-INT-25, T-INT-26, T-INT-29, T-INT-30, T-INT-32, T-INT-33, T-INT-38, T-INT-40, T-INT-42 |
| AC-INT-18 | T-INT-18 (Caja), T-INT-26 (sistema), T-INT-35 (integración) |
| AC-INT-19 | T-INT-04 (constraint), T-INT-39, T-INT-40 |
| AC-INT-20 | T-INT-16, T-INT-17, T-INT-18, T-INT-19, T-INT-42 |
| AC-INT-21 | T-INT-07, T-INT-16, T-INT-17, T-INT-18, T-INT-19, T-INT-38, T-INT-40 |
| AC-INT-22 | T-INT-13, T-INT-42 |
| AC-INT-23 | T-INT-07, T-INT-42 |
| AC-INT-24 | T-INT-42 (y el DoD de cada tarea con rutas) |
| AC-INT-25 | T-INT-08, T-INT-10, T-INT-11, T-INT-33 |
| AC-INT-26 | T-INT-21 |
| AC-INT-27 | T-INT-21 |
| AC-INT-28 | T-INT-01, T-INT-08, T-INT-10, T-INT-24, T-INT-34 |
| AC-INT-29 | T-INT-01, T-INT-24 |
| AC-INT-30 | T-INT-22, T-INT-23 |
| AC-INT-31 | T-INT-09, T-INT-24, T-INT-30, T-INT-31 |
| AC-INT-32 | T-INT-27 |
| AC-INT-33 | T-INT-10 (reactivar sin juego), T-INT-11, T-INT-33, T-INT-34, T-INT-52 |
| AC-INT-34 | T-INT-03, T-INT-16, T-INT-17, T-INT-37, T-INT-38 |
| AC-INT-35 | T-INT-39, T-INT-52 |
| AC-INT-36 | T-INT-09, T-INT-28, T-INT-35 |
| AC-INT-37 | T-INT-09, T-INT-31 |
| AC-INT-38 | T-INT-01, T-INT-10, T-INT-11, T-INT-24 |
| AC-INT-39 | T-INT-37 |
| AC-INT-40 | T-INT-18, T-INT-39 |
| AC-INT-41 | T-INT-01, T-INT-12, T-INT-13, T-INT-22 |
| AC-INT-42 | T-INT-09, T-INT-34 |
| AC-INT-43 | T-INT-03, T-INT-08, T-INT-17, T-INT-37 |
| AC-INT-44 | T-INT-05, T-INT-14, T-INT-15, T-INT-26, T-INT-31 |
| AC-INT-45 | T-INT-09, T-INT-28, T-INT-31, T-INT-34, T-INT-35, T-INT-36 |
| AC-INT-46 | T-INT-17, T-INT-19, T-INT-37, T-INT-39 |

**RF → tareas:** RF-INT-01 → T-INT-21, T-INT-44 · RF-INT-02 → T-INT-24, T-INT-25, T-INT-45 · RF-INT-03 → T-INT-22,
T-INT-43, T-INT-46, T-INT-51 · RF-INT-04 → T-INT-30, T-INT-31, T-INT-32, T-INT-48 · RF-INT-05 → T-INT-28, T-INT-29,
T-INT-46 · RF-INT-06 → T-INT-10, T-INT-11, T-INT-33, T-INT-34, T-INT-48 · RF-INT-07 → T-INT-23 · RF-INT-08 → T-INT-26 ·
RF-INT-09 → T-INT-04, T-INT-18, T-INT-19, T-INT-39, T-INT-40, T-INT-50 · RF-INT-10 → T-INT-03, T-INT-16, T-INT-17,
T-INT-37, T-INT-38, T-INT-49 · RF-INT-11 → T-INT-18, T-INT-35, T-INT-36 · RF-INT-12 → T-INT-07, T-INT-42 · RF-INT-13 →
T-INT-27 · RF-INT-14 → T-INT-12, T-INT-13, T-INT-22, T-INT-47 · RF-INT-15 → T-INT-14, T-INT-15.

**RNF → tareas:** RNF-INT-01 → T-INT-41 (y el DoD de credenciales) · RNF-INT-02 → T-INT-05, T-INT-06, T-INT-14,
T-INT-15 · RNF-INT-03 → T-INT-07, T-INT-42 · RNF-INT-04 → T-INT-14, T-INT-26, T-INT-27, T-INT-28 · RNF-INT-05 →
T-INT-42 (y el DoD de rutas) · RNF-INT-06 → T-INT-01, T-INT-02, T-INT-03, T-INT-04 · RNF-INT-07 → T-INT-21 ·
RNF-INT-08 → T-INT-28, T-INT-29 · RNF-INT-09 → toda tarea con rutas · RNF-INT-10 → T-INT-01, T-INT-41.

**Spec §14 → tareas:** Configuración → Integraciones → T-INT-43, T-INT-46, T-INT-47, T-INT-48 · Alta → T-INT-44,
T-INT-45 · Sucursales y cajas → T-INT-49, T-INT-50 · Inicio → T-INT-51 · estados (cargando, vacío, error, sin permiso,
suspendida, resultado de la prueba, cuenta ya conectada) → en cada tarea de UI.

**Huecos:** ningún AC ni RF sin tarea. Salvedades:
- **Q-433:** solo **AC-INT-20** y **AC-INT-22** quedan cubiertos enteros por tareas sin motor (`T-INT-16` a `T-INT-19`
  y `T-INT-13`); AC-INT-25 queda cubierto a nivel servicio (`T-INT-08`, `T-INT-10`, `T-INT-11`) y su API espera a
  `T-INT-33`. Todos los demás AC tienen al menos una parte en una tarea ⛔.
- **AC-INT-24** no tiene tarea propia aparte de `T-INT-42`: lo construye cada tarea con rutas (DoD) y `T-INT-42`
  verifica que no falte ninguna.
- **AC-INT-14** se apoya en el test de contrato del adaptador (SPEC-03 AC-ENG-11) para "sin efectos en un proveedor
  real"; acá solo se usa el `FakeAdapter` (design §9).
- **Supuestos abiertos** (design §11.2) que tocan tareas: Q-413 a) → T-INT-04, T-INT-19; Q-414 a) → T-INT-30; Q-417 a)
  → T-INT-29; Q-419 a) → T-INT-28, T-INT-29; Q-422 a) → T-INT-35. Si el dueño decide otra opción, cambia la tarea
  indicada (design §11.2 dice cómo).

## Orden y paralelismo
| Ola | Tareas | Notas |
|---|---|---|
| 0 | T-INT-01 → T-INT-02 → T-INT-03 → T-INT-04 (en serie: son las cuatro migraciones) · después de T-INT-01, en paralelo: {T-INT-05, T-INT-07, T-INT-08, T-INT-09, T-INT-12} | Arrancan ya: no usan el motor. Ninguna de las paralelas crea migraciones |
| 1 | T-INT-06 · T-INT-10 → T-INT-11 · T-INT-13 → T-INT-16 → {T-INT-17, T-INT-18 → T-INT-19} · T-INT-14 → T-INT-15 | Arrancan ya. Con T-INT-13 existe la primera ruta del módulo |
| 2 (⛔ Q-433) | T-INT-20 → T-INT-21 → T-INT-22 → T-INT-23 · T-INT-24 → {T-INT-25, T-INT-26 → {T-INT-27, T-INT-28 → T-INT-29}} · T-INT-30 | Desde acá hace falta el motor de SPEC-03 |
| 3 (⛔ Q-433) | T-INT-31 → {T-INT-32, T-INT-35 → T-INT-36} · T-INT-33 → T-INT-34 · T-INT-37 → {T-INT-38, T-INT-39 → T-INT-40} | Con T-INT-35/36, SPEC-06 tiene los contratos de §3.7 |
| 4 (⛔ Q-433) | T-INT-41 → T-INT-42 · T-INT-43 → {T-INT-45, T-INT-46 → {T-INT-47, T-INT-48}} · T-INT-44 · T-INT-49 → T-INT-50 · T-INT-51 → T-INT-52 | T-INT-43 espera además el cambio de SPEC-02 de Q-434. Después de T-INT-52: verificación (paso 6) y validación manual de §14 |

---

## Detalle por tarea

> Cada ficha cumple la DoR de `.agents/workflows/sdd-odd.md §6` (AC, archivos, plan de pruebas, dependencias, spec
> *Approved*), salvo las ⛔: su DoR se completa cuando existan las tareas de SPEC-03 que nombran (Q-433). La DoD
> general es la de `sdd-odd.md §6` más la de "Convenciones" de esta lista; cada ficha agrega solo lo propio.

### T-INT-01 — App `integrations` + `Integration` + migración 0001
- **AC:** AC-INT-28 (constraint de nombre), AC-INT-29 (índice de cuenta), AC-INT-38 (índice parcial), AC-INT-41
  (unicidad del identificador). RN-INT-01, 03, 19, 21, 27; RNF-INT-06, RNF-INT-10. **Zona roja:** sí (migraciones,
  aislamiento). **DoR:** lista.
- **Archivos:** `apps/integrations/{__init__,apps}.py` (label `integrations`), `models/{__init__,integration}.py`,
  `migrations/0001_integration.py` (depende de `tenancy.0004_branch` y de `identity`), `config/settings/base.py`
  (`INSTALLED_APPS`), `backend/tests/integrations/test_integration_constraints.py`; si
  `backend/tests/migrations/test_AC_PLT_17_reversibility.py` enumera las apps que se revierten, suma `integrations`.
- **Cambios:** tabla `integrations_integration` de design §5 con **todas** sus constraints e índices
  (`integration_unique_active_name`, `integration_account_reserved`, `integration_unconfirmed_coherent`, …,
  `integration_org_id_uniq`); `TenantModel` + `NoHardDeleteMixin`; `webhook_route_key` por defecto
  `secrets.token_urlsafe(32)`, único; `__repr__`/`__str__` = PK.
- **Fuera:** `CredentialSet`, servicios, scope `by_webhook_route_key` (T-INT-12).
- **Pruebas:** `test_AC_INT_28_active_name_unique_case_insensitive_constraint`,
  `test_AC_INT_28_inactive_name_does_not_block`, `test_AC_INT_29_account_reserved_across_organizations`,
  `test_AC_INT_29_other_environment_is_free`, `test_AC_INT_38_disconnected_does_not_reserve_account`,
  `test_AC_INT_41_webhook_route_key_unique`, `test_RN_INT_21_reason_and_status_coherent` (parametrizado por check),
  `test_RN_INT_19_unconfirmed_coherent`. Ida y vuelta de la migración (job `migrations`).
- **DoD extra:** `makemigrations --check` y `lint_migrations` en verde.

### T-INT-02 — `CredentialSet` + migración 0002 con FK compuesta
- **AC:** — (RN-INT-06 un juego por integración, RN-INT-13). **Zona roja:** sí. **Depende:** T-INT-01. **DoR:** lista.
- **Archivos:** `models/credential_set.py`, `models/__init__.py`, `migrations/0002_credential_set.py`,
  `backend/tests/integrations/test_credential_set_constraints.py`.
- **Cambios:** tabla `integrations_credentialset` de design §5 (sin `NoHardDeleteMixin`: se borra al desconectar);
  FK compuesta `(organization_id, integration_id) → integrations_integration (organization_id, id)` con
  `RunSQL(sql, reverse_sql)` (§5.1); sin serializer; `__repr__` = PK.
- **Fuera:** cifrado (T-INT-05), escritura del juego (T-INT-24).
- **Pruebas:** `test_RN_INT_13_credentialset_mixing_organizations_is_rejected` (INSERT por SQL),
  `test_RN_INT_06_one_set_per_integration`, `test_RN_INT_04_credentialset_repr_has_no_data`, checks de
  `key_id`/`format_version`/`ciphertext` mínimo.

### T-INT-03 — `BranchLink` + migración 0003 con FK compuestas
- **AC:** AC-INT-34 (constraint), AC-INT-43 (constraint). RN-INT-13, RN-INT-23; Q-429, Q-432 a). **Zona roja:** sí.
  **Depende:** T-INT-02 (0003 cuelga de `0002_credential_set` y de `tenancy.0004_branch`; serie de migraciones).
  **DoR:** lista.
- **Archivos:** `models/branch_link.py`, `models/__init__.py`, `migrations/0003_branch_link.py`,
  `backend/tests/integrations/test_branch_link_constraints.py`.
- **Cambios:** tabla `integrations_branchlink` (design §5): `branch_link_one_per_pair`, `branch_link_unique_store_ref`,
  `branch_link_store_ref_coherent`, `branch_link_active_coherent`; FK compuestas a `tenancy_branch (organization_id,
  id)` (usa `branch_org_id_uniq`) y a la integración, `ON DELETE RESTRICT`.
- **Fuera:** servicios y API (T-INT-16, T-INT-17, T-INT-37).
- **Pruebas:** `test_AC_INT_34_link_mixing_organizations_is_rejected` (SQL directo, `Branch` de B),
  `test_AC_INT_43_second_link_same_pair_is_rejected` (también con el primero inactivo),
  `test_Q_432_store_ref_unique_per_integration`, `test_RN_INT_23_store_origin_none_has_no_ref`.

### T-INT-04 — `CashRegister` + migración 0004 con FK compuesta al vínculo
- **AC:** AC-INT-19 (constraint). RN-INT-12, RN-INT-13; Q-413 a) (supuesto). **Zona roja:** sí. **Depende:** T-INT-03.
  **DoR:** lista.
- **Archivos:** `models/cash_register.py`, `models/__init__.py`, `migrations/0004_cash_register.py`,
  `backend/tests/integrations/test_cash_register_constraints.py`.
- **Cambios:** tabla `integrations_cashregister` (design §5): FK compuesta `(organization_id, branch_id,
  integration_id) → integrations_branchlink`, `cash_register_unique_active_name`, `cash_register_unique_provider_ref`,
  `cash_register_org_id_uniq` (destino de la FK de SPEC-06), checks de origen, nombre y referencia.
- **Fuera:** servicios y API (T-INT-18, T-INT-19, T-INT-39).
- **Pruebas:** `test_AC_INT_19_cash_register_mixing_organizations_is_rejected`,
  `test_AC_INT_19_cash_register_without_link_is_rejected`, `test_Q_413_active_name_unique_per_link`,
  `test_Q_413_provider_ref_unique_per_integration`. Ida y vuelta de 0001–0004.

### T-INT-05 — Cifrado AES-256-GCM y llavero (dominio, ADR-0003)
- **AC:** AC-INT-44 (cifrado: lectura con la clave de la fila, cifrado con la activa). RNF-INT-02; ADR-0003 §1–§4.
  **Zona roja:** sí (cifrado). **Depende:** T-INT-01 (paquete). **DoR:** lista.
- **Archivos:** `apps/integrations/keyring.py` (`Keyring`, `parse_keyring(raw_keys, active_id)`),
  `domain/credential_cipher.py` (`seal`, `open_sealed`, `Sealed`, `aad`, `CredentialDecryptError`,
  `CredentialKeyUnavailable`), `backend/tests/integrations/domain/{test_credential_cipher,test_keyring}.py`.
- **Cambios:** design §3.4 literal: nonce de 12 bytes por cifrado, JSON canónico, límite de 16 KiB, AAD con
  organización, integración y `key_id`; `Keyring` inmutable, `repr` sin bytes; ids `^[a-z0-9-]{1,32}$`, claves de 32
  bytes en base64url, id activo presente, sin repetidos. Sin Django ni red.
- **Fuera:** lectura desde settings, checks y comando (T-INT-06).
- **Pruebas:** `test_AC_INT_44_reads_with_row_key_and_seals_with_active`, `test_RNF_INT_02_roundtrip`,
  `test_RNF_INT_02_other_org_integration_or_key_id_fails` (parametrizado), `test_RNF_INT_02_nonce_differs_per_seal`,
  `test_RNF_INT_02_unknown_key_id_raises_unavailable`, `test_RNF_INT_02_plaintext_limit`,
  `test_RNF_INT_02_keyring_parse_errors` (parametrizado), `test_RN_INT_04_keyring_and_sealed_repr_have_no_bytes`.

### T-INT-06 — Llavero en settings, system checks y `integrations_generate_key`
- **AC:** AC-INT-08. RNF-INT-02; ADR-0003 §4. **Zona roja:** sí (settings, cifrado). **Depende:** T-INT-02, T-INT-05.
  **DoR:** lista.
- **Archivos:** `config/settings/env.py` (solo `INTEGRATIONS_CREDENTIAL_KEYS` e `INTEGRATIONS_CREDENTIAL_ACTIVE_KEY`,
  `SecretStr`; ver C-14), `config/settings/{base,test,prod}.py` (llavero sintético fijo en `test`),
  `apps/integrations/keyring.py` (`get_keyring()` desde settings), `apps/integrations/checks.py` (llavero inválido →
  `ImproperlyConfigured` salvo `test`; `prod` rechaza el id `test` y los bytes del llavero de test),
  `management/commands/integrations_generate_key.py` (imprime una vez en `stdout`, no pasa por el logger),
  `env.example` (nombres vacíos + instrucción), `infra/docker-compose.ci.yml` (llavero sintético para el smoke del job
  `build`), `infra/README.md`, `backend/tests/integrations/{test_keyring_settings,test_AC_INT_08_ciphertext_at_rest}.py`,
  `backend/tests/integrations/commands/test_generate_key.py`.
- **Cambios:** ADR-0003 §4. Antes de abrir el PR, revisar qué jobs de CI y qué servicios de Compose arrancan Django
  con settings distintos de `test` (`check_migrations_roundtrip`, smoke, `docker-compose.yml` de desarrollo): todos
  necesitan un llavero. Si alguno exige tocar `.github/workflows/`, la tarea **para** y lo reporta (Q-063).
- **Fuera:** re-cifrado (T-INT-14, T-INT-15).
- **Pruebas:** `test_AC_INT_08_stored_set_has_no_plaintext_secret` (escribe un juego con `seal` y lee la fila por SQL),
  `test_RNF_INT_02_missing_keyring_does_not_start`, `test_RNF_INT_02_prod_rejects_test_key_id_and_bytes`,
  `test_RNF_INT_02_generate_key_prints_once_and_never_logs`.
- **DoD extra:** `python scripts/smoke_stack.py` en verde sobre las imágenes `runtime` del commit.

### T-INT-07 — Matriz de permisos y catálogo de auditoría
- **AC:** AC-INT-11 (matriz), AC-INT-21 (matriz), AC-INT-23 (catálogo). RN-INT-08, RN-INT-17, RN-INT-25; RNF-INT-03.
  **Zona roja:** sí (permisos). **Depende:** T-INT-01. **DoR:** lista.
- **Archivos:** `domain/permissions.py` (`IntegrationsAction`, `INTEGRATIONS_ACTIONS` con `ActionSpec`, design §3.5),
  `domain/audit_events.py` (`IntegrationsAuditAction`, design §6.4), `services/audit.py::record_event` (patrón de
  SPEC-02), `backend/tests/integrations/domain/{test_permission_matrix,test_audit_catalog}.py`.
- **Cambios:** matriz deny-by-default; `api_key_scope=None` (Q-420); `test_connection` y `disconnect` son `WRITE`
  (Q-417 a), AC-INT-17).
- **Fuera:** `AUDIT_TRIGGERS` completo (cada servicio suma los suyos; T-INT-42 verifica la completitud).
- **Pruebas:** `test_AC_INT_11_operator_viewer_denied_integration_writes` y `test_AC_INT_21_links_and_cash_registers_matrix`
  (transcriben la tabla de `spec.sdd.md §4` 1.0.0 celda por celda, en `active` y `suspended`),
  `test_AC_INT_23_catalog_matches_rnf_int_03`, `test_RN_INT_08_actions_enum_equals_specs`.

### T-INT-08 — Máquinas de estado, nombres y claves externas
- **AC:** AC-INT-25 (decisión), AC-INT-28 (normalización), AC-INT-43 (transiciones del vínculo). RN-INT-18; Q-408,
  Q-413 a), Q-426, Q-429. **Zona roja:** sí (ciclo de vida). **Depende:** T-INT-01. **DoR:** lista.
- **Archivos:** `domain/lifecycle.py` (`decide_integration_event`, `decide_link_event`, `decide_cash_register_event`),
  `domain/names.py::normalize_name`, `domain/external_keys.py` (`store_key`, `pos_key`), tests en
  `backend/tests/integrations/domain/{test_lifecycle,test_names,test_external_keys}.py`.
- **Cambios:** tablas de `spec.sdd.md §10`; cada inválida → `InvalidTransition(entity, status, event)`; claves
  `"hub" + sha256(...)[:32]` estables (design §4.6). Sin Django.
- **Pruebas:** `test_AC_INT_25_invalid_integration_transitions` (parametrizado por cada inválida de §10),
  `test_AC_INT_43_link_reactivate_active_is_invalid`, `test_AC_INT_28_normalize_trims_and_casefolds`,
  `test_RN_INT_12_pos_key_stable_and_opaque`, `test_RN_INT_23_store_key_stable_and_opaque`.

### T-INT-09 — Decisión de la prueba de conexión (`decide_save` / `decide_manual_test`)
- **AC:** AC-INT-13, AC-INT-31, AC-INT-36, AC-INT-37, AC-INT-42, AC-INT-45 (decisión). RN-INT-10, 19, 21, 22; Q-406,
  Q-407, Q-423, Q-425, Q-427, Q-430 a). **Zona roja:** sí. **Depende:** T-INT-01. **DoR:** lista.
- **Archivos:** `domain/connection.py` (`Outcome` = `Connected | AuthInvalid | Unreachable | Raised`, `Save`, `Reject`,
  `Apply`, `decide_save`, `decide_manual_test`), `domain/errors.py` (reasons cerrados de design §6.2), tests en
  `backend/tests/integrations/domain/{test_decide_save,test_decide_manual_test}.py` (dos archivos, `C-14`).
- **Cambios:** tabla de design §4.2 completa, incluida `account_unconfirmed`. Los `Outcome` son tipos propios del
  dominio: la traducción desde `ConnectionStatus` y los errores del motor es de T-INT-24/T-INT-28.
- **Pruebas:** un test por fila de §4.2 en cada función, nombrados por su AC: `test_AC_INT_31_*` (rechazos y guardado
  al crear), `test_AC_INT_37_other_account_on_replace_rejects`, `test_AC_INT_42_other_account_on_reactivate_rejects`,
  `test_AC_INT_36_connected_without_known_account_sets_it`, `test_AC_INT_45_unreachable_with_known_account_marks_unconfirmed`,
  `test_AC_INT_45_manual_other_account_keeps_unconfirmed`, `test_AC_INT_13_manual_outcomes` (parametrizado, Q-425).

### T-INT-10 — Desactivar y reactivar una integración inactiva (servicio)
- **AC:** AC-INT-25 (servicio), AC-INT-28 (reactivar con el nombre ocupado), AC-INT-38 (desactivar no libera la
  cuenta). RN-INT-14, RN-INT-15, RN-INT-18; Q-408, Q-426. **Zona roja:** sí. **Depende:** T-INT-02, T-INT-07,
  T-INT-08. **DoR:** lista.
- **Archivos:** `services/integration_lifecycle.py` (`deactivate`, `reactivate` de una **inactiva con credenciales**),
  `selectors/integrations.py::get_integration(ctx, id)`, `apps/integrations/errors.py`,
  `backend/tests/integrations/services/test_lifecycle_deactivate_reactivate.py`.
- **Cambios:** `atomic` → `ensure_writable` → `select_for_update(no_key=True)` → `decide_integration_event` →
  escritura; nombre ocupado → `taken` traduciendo el `IntegrityError` (sin `full_clean`, Q-229); desactivar no toca
  credenciales, vínculos ni Cajas; `transition.rejected` fuera del `atomic`. Reactivar una **desconectada sin juego
  nuevo** se rechaza sin cambios como `validation_error` con `credentials`: `required` (design §6.1, la API lo
  devuelve como `400` en T-INT-33). Reactivar una desconectada **con** juego nuevo llama al motor y es de T-INT-34.
- **Fuera:** API (T-INT-33), desconectar (T-INT-11), reactivar con juego nuevo (T-INT-34).
- **Pruebas:** `test_AC_INT_25_reactivate_active_is_rejected_and_audited`, `test_AC_INT_25_deactivate_inactive_is_rejected`,
  `test_AC_INT_28_reactivate_with_taken_name_is_rejected`, `test_AC_INT_38_deactivated_keeps_account_reserved`,
  `test_AC_INT_33_reactivate_disconnected_without_set_requires_credentials`, `test_RN_INT_15_suspended_organization_rejects`.

### T-INT-11 — `PendingChargesPort` y desconectar (servicio)
- **AC:** AC-INT-25 (desconectar una desconectada), AC-INT-33 (desconectar), AC-INT-38 (desconectar libera la cuenta).
  RN-INT-24; Q-408, Q-425, Q-427. **Zona roja:** sí (credenciales, cobros `pending`). **Depende:** T-INT-04, T-INT-10.
  **DoR:** lista.
- **Archivos:** `services/ports.py` (`PendingChargesPort`, `NoChargesModule`), `services/integration_lifecycle.py`
  (`disconnect`), `apps/integrations/checks.py` (falla si `apps.charges` está instalada sin puerto propio),
  `config/settings/base.py` (`INTEGRATIONS_PENDING_CHARGES_PORT`), `backend/tests/integrations/services/test_disconnect.py`.
- **Cambios:** design §4.5 "Desconectar": `FOR UPDATE`, `bounded_lock_wait()`, puerto, `DELETE` del juego, campos de
  conexión a `unverified`, `account_id` conservado, `integration.disconnected`.
- **Fuera:** lock del cobro nuevo (T-INT-35), API (T-INT-33).
- **Pruebas:** `test_AC_INT_33_disconnect_deletes_set_keeps_account_and_links` (Cajas y vínculos sin cambios),
  `test_AC_INT_33_disconnect_with_pending_charges_is_rejected` (puerto de test que devuelve `True`),
  `test_AC_INT_25_disconnect_disconnected_is_rejected`, `test_AC_INT_38_disconnected_frees_account`,
  `test_RN_INT_24_port_check_fails_without_charges_port`.

### T-INT-12 — Búsqueda por identificador de webhooks para SPEC-07
- **AC:** AC-INT-41 (búsqueda). RN-INT-27; RF-INT-14. **Zona roja:** sí (lectura antes del tenant).
  **Depende:** T-INT-01. **DoR:** lista.
- **Archivos:** `selectors/webhook_routing.py::find_by_webhook_route_key(key) -> RoutedIntegration | None`,
  `models/integration.py` (scope `by_webhook_route_key`), `tests/architecture/allowlists.py` (`MODEL_SCOPES`,
  `RESTRICTED_SCOPES` y su entrada, con motivo y `count`), `backend/tests/integrations/test_webhook_routing.py`.
- **Cambios:** design §5.2: una fila por igualdad, solo `organization_id` e `integration_id`; el valor nunca se loguea.
- **Pruebas:** `test_AC_INT_41_lookup_finds_integration_by_key`, `test_AC_INT_41_unknown_key_returns_none`,
  `test_RN_INT_27_scope_only_allowed_in_webhook_routing` (test de arquitectura existente en verde).

### T-INT-13 — Regenerar el identificador de webhooks (primera ruta del módulo)
- **AC:** AC-INT-10 (regenerar), AC-INT-11 (regenerar), AC-INT-12, AC-INT-17 (regenerar), AC-INT-22, AC-INT-41
  (regenerar). RN-INT-16, RN-INT-27. **Zona roja:** sí (contrato, permisos). **Depende:** T-INT-07, T-INT-10,
  T-INT-12. **DoR:** lista.
- **Archivos:** `services/webhook_key.py::regenerate_webhook_key`, `api/urls.py`, `api/base.py` (viewset de
  integración sobre `TenantViewSet` de SPEC-02), `api/integration_actions.py`, `config/urls.py`,
  `backend/tests/cross_tenant/cases/integrations.py`, `backend/tests/integrations/api/{test_webhook_key_regenerate,
  test_AC_INT_22_no_oauth_routes}.py`, `specs/_contracts/openapi.yaml`, `frontend/src/types/api.d.ts`, `API_VERSION`.
- **Cambios:** `POST /api/integrations/{id}/webhook-key/regenerate/` → `200 {webhook_route_key}`; el anterior deja de
  servir en la misma transacción; `integration.webhook_key_regenerated` sin valores; ruta montada con `as_view`
  (Ajustes). Test de rutas: ninguna ruta de autorización ni de callback OAuth.
- **Fuera:** mostrar el identificador en el detalle (T-INT-22), UI (T-INT-47).
- **Pruebas:** `test_AC_INT_41_regenerate_invalidates_previous_key`, `test_AC_INT_41_keys_never_in_logs`,
  `test_AC_INT_41_operator_gets_403`, `test_AC_INT_10_regenerate_other_org_404`, `test_AC_INT_12_superuser_without_membership_404`,
  `test_AC_INT_17_suspended_rejects_regenerate`, `test_AC_INT_22_no_oauth_routes`.

### T-INT-14 — Re-cifrado por organización (servicio)
- **AC:** AC-INT-44 (re-cifrado). RNF-INT-02; RF-INT-15; ADR-0003 §5. **Zona roja:** sí (cifrado, `unscoped`).
  **Depende:** T-INT-06, T-INT-07. **DoR:** lista.
- **Archivos:** `services/reencrypt.py` (enumera organizaciones con `unscoped(PLATFORM_COMMAND)`, procesa cada una con
  `tenant_scope(system_context(...))`), `tests/architecture/allowlists.py` (`UNSCOPED_ALLOWLIST` y `system_context`),
  `backend/tests/integrations/services/test_reencrypt.py`.
- **Cambios:** ADR-0003 §5.3: transacción corta por juego, lock, re-chequeo de `key_id` bajo lock, una sola `UPDATE` de
  `ciphertext` + `key_id` + `reencrypted_at`; `credentials_updated_at` sin cambio; un juego que no descifra no se
  escribe, se cuenta y se loguea `integrations.reencrypt_failed`; `integration.credentials_reencrypted` por
  organización (actor operador); log `integrations.reencrypt_batch`.
- **Fuera:** CLI y `--check` (T-INT-15).
- **Pruebas:** `test_AC_INT_44_reencrypt_moves_all_sets_to_active_key` (A y B), `test_AC_INT_44_content_and_updated_at_unchanged`,
  `test_AC_INT_44_one_event_per_organization_without_values`, `test_AC_INT_44_undecryptable_set_is_skipped_and_counted`,
  `test_AC_INT_44_already_active_set_is_skipped_under_lock`, `test_AC_INT_44_sets_readable_after_removing_old_key`.

### T-INT-15 — Comando `integrations_reencrypt_credentials` y `--check`
- **AC:** AC-INT-44 (comando y `--check`). RF-INT-15; ADR-0003 §5.3–§5.4. **Zona roja:** sí. **Depende:** T-INT-14.
  **DoR:** lista.
- **Archivos:** `management/commands/integrations_reencrypt_credentials.py` (`--operator`, `--batch-size`,
  `--dry-run`, `--check`; operador validado como los comandos de SPEC-02),
  `backend/tests/integrations/commands/test_reencrypt_command.py`.
- **Pruebas:** `test_AC_INT_44_check_reports_remaining_and_fails_while_old_key_used`,
  `test_AC_INT_44_check_passes_when_done`, `test_AC_INT_44_exit_code_nonzero_on_failed_set`,
  `test_RF_INT_15_dry_run_writes_nothing`, `test_RF_INT_15_operator_outside_allowlist_is_rejected`.

### T-INT-16 — Vínculos: listar y ver
- **AC:** AC-INT-20 (vínculos de B), AC-INT-21 (leer), AC-INT-34 (listado). RN-INT-09, RN-INT-25. **Zona roja:** sí.
  **Depende:** T-INT-03, T-INT-07, T-INT-13. **DoR:** lista.
- **Archivos:** `selectors/branch_links.py`, `api/branch_links.py`, `api/serializers/branch_links.py`, `api/urls.py`,
  `backend/tests/cross_tenant/cases/branch_links.py`, `backend/tests/integrations/api/test_branch_links_read.py`, contrato.
- **Cambios:** `GET /api/branch-links/` (filtros `branch_id`, `integration_id`, `is_active`; filtro de otra
  organización → `404`) y `GET /api/branch-links/{id}/`; representación de design §6.5 con `allowed_actions`.
- **Pruebas:** `test_AC_INT_20_link_of_other_org_404`, `test_AC_INT_20_list_excludes_other_org`,
  `test_AC_INT_21_operator_and_viewer_can_read_links`, `test_AC_INT_34_list_returns_org_links`.

### T-INT-17 — Vínculos: desactivar y reactivar
- **AC:** AC-INT-17 (vínculo), AC-INT-20 (escrituras de B), AC-INT-21 (desactivar), AC-INT-34 (desactivar), AC-INT-43
  (reactivar), AC-INT-46 (reactivar con integración o `Branch` inactiva). RN-INT-14, RN-INT-18, RN-INT-23; Q-429,
  Q-431 b). **Zona roja:** sí. **Depende:** T-INT-08, T-INT-16. **DoR:** lista.
- **Archivos:** `services/branch_links.py` (`deactivate_link`, `reactivate_link`), `api/branch_links.py`, `api/urls.py`,
  `backend/tests/cross_tenant/cases/branch_links.py`, `backend/tests/integrations/api/test_branch_links_lifecycle.py`, contrato.
- **Cambios:** `POST /api/branch-links/{id}/deactivate/` y `/reactivate/` (design §4.6 "Reactivar un vínculo"): sin
  llamar al proveedor, sin tocar el estado de las Cajas; `branch_link.deactivated` / `.reactivated`.
- **Pruebas:** `test_AC_INT_34_deactivate_link_emits_event`, `test_AC_INT_43_reactivate_returns_same_link_and_store_ref`,
  `test_AC_INT_43_reactivate_active_is_invalid_and_audited`, `test_AC_INT_46_reactivate_link_with_inactive_integration_or_branch`,
  `test_AC_INT_21_operator_cannot_deactivate_link`, `test_AC_INT_20_deactivate_other_org_link_404`,
  `test_AC_INT_17_suspended_rejects_link_writes`.

### T-INT-18 — Cajas: listar, ver y "Caja utilizable"
- **AC:** AC-INT-17 (leer Cajas con la organización suspendida), AC-INT-18 (Caja), AC-INT-20 (Cajas de B), AC-INT-21
  (leer), AC-INT-40 (selector). RN-INT-14, RN-INT-26; RF-INT-11. **Zona roja:** sí. **Depende:** T-INT-04, T-INT-16.
  **DoR:** lista.
- **Archivos:** `selectors/cash_registers.py`, `selectors/usability.py::get_usable_cash_register` (+
  `CashRegisterNotUsable`), `api/cash_registers.py`, `api/serializers/cash_registers.py` (`is_usable` del backend),
  `api/urls.py`, `backend/tests/cross_tenant/cases/cash_registers.py`,
  `backend/tests/integrations/{api/test_cash_registers_read,services/test_cash_register_usability}.py`, contrato.
- **Cambios:** `GET /api/cash-registers/` (filtros) y `GET /api/cash-registers/{id}/`; selector con las condiciones de
  RN-INT-26 para la Caja más integración `active` (Ajustes, AC-INT-46).
- **Pruebas:** `test_AC_INT_18_inactive_cash_register_not_usable`, `test_AC_INT_18_cash_register_of_inactive_branch_not_usable`,
  `test_AC_INT_18_cash_register_of_inactive_link_not_usable`, `test_AC_INT_40_link_deactivated_cash_register_stays_active_not_usable`,
  `test_AC_INT_20_cash_register_of_other_org_404`, `test_AC_INT_21_viewer_can_read_cash_registers`,
  `test_AC_INT_17_suspended_owner_reads_cash_registers`.

### T-INT-19 — Cajas: editar, desactivar y reactivar
- **AC:** AC-INT-17 (Cajas), AC-INT-20 (escrituras de B), AC-INT-21 (escrituras), AC-INT-46 (reactivar Caja).
  RN-INT-18, RN-INT-25; Q-413 a). **Zona roja:** sí. **Depende:** T-INT-08, T-INT-18. **DoR:** lista.
- **Archivos:** `services/cash_registers.py` (`update_cash_register`, `deactivate`, `reactivate`),
  `api/cash_registers.py`, `api/urls.py`, `backend/tests/cross_tenant/cases/cash_registers.py`,
  `backend/tests/integrations/api/test_cash_registers_lifecycle.py`, contrato.
- **Cambios:** `PATCH /api/cash-registers/{id}/` (`{name}`; renombrar no cambia el POS, design §4.6),
  `POST …/deactivate/` y `/reactivate/` (nombre ocupado → `400 taken`); eventos `cash_register.updated`,
  `.deactivated`, `.reactivated`.
- **Pruebas:** `test_AC_INT_46_reactivate_cash_register_with_inactive_branch_stays_not_usable`,
  `test_AC_INT_21_operator_cannot_edit_or_deactivate_cash_register`, `test_AC_INT_20_patch_other_org_cash_register_404`,
  `test_AC_INT_17_suspended_rejects_cash_register_writes`, `test_Q_413_reactivate_with_taken_name`,
  `test_RN_INT_18_cash_register_invalid_transitions_audited`.

### T-INT-20 — Validación contra el esquema del adaptador ⛔ Q-433
- **AC:** AC-INT-05 (dominio). RN-INT-07; design §7 (límites). **Zona roja:** sí. **Depende:** T-INT-01; **SPEC-03:**
  `FieldSpec`/`FieldSchema` (RF-ENG-06).
- **Archivos:** `domain/field_validation.py::validate_section(specs, values)`,
  `backend/tests/integrations/domain/test_field_validation.py`.
- **Cambios:** requerido, tipo, `pattern` con `fullmatch` después del corte de largo, `max_length` (≤ 2048), `choices`,
  campo desconocido (`unknown_field`), ≤ 32 campos por sección, 16 KiB totales (`too_large`); mensajes fijos que nombran
  el campo, nunca el valor.
- **Pruebas:** `test_AC_INT_05_missing_required_secret_names_field`, `test_AC_INT_05_bad_format_names_field`,
  `test_RN_INT_07_messages_never_contain_value`, `test_RN_INT_07_limits` (parametrizado).

### T-INT-21 — Catálogo de providers y *feature flags* por provider ⛔ Q-433
- **AC:** AC-INT-11 (catálogo), AC-INT-26, AC-INT-27. RN-INT-02; RF-INT-01; RNF-INT-07. **Zona roja:** sí.
  **Depende:** T-INT-13, T-INT-20; **SPEC-03:** `ProviderRegistry`, `BaseAdapter.capabilities`/`.field_schema`,
  `FakeAdapter`.
- **Archivos:** `selectors/catalog.py` (`list_enabled_providers`, `enabled_provider`), `api/providers.py`,
  `api/serializers/catalog.py`, `api/urls.py`, `apps/common/feature_flags.py` (`INTEGRATIONS_PROVIDER_FAKE`, solo
  dev/test), `apps/integrations/checks.py` (provider sin flag; `fake` en `prod`), `backend/tests/integrations/conftest.py`
  (fixture que registra el `FakeAdapter` y su flag), `backend/tests/cross_tenant/cases/integrations.py`,
  `backend/tests/integrations/api/test_catalog.py`, contrato.
- **Pruebas:** `test_AC_INT_27_catalog_lists_fake_with_declared_fields`, `test_AC_INT_26_flag_off_hides_provider`,
  `test_AC_INT_11_operator_viewer_get_403_on_catalog`, `test_RNF_INT_07_check_fails_for_provider_without_flag`,
  `test_RNF_INT_07_prod_check_rejects_fake`.

### T-INT-22 — Listado y detalle por rol ⛔ Q-433
- **AC:** AC-INT-06, AC-INT-10 (GET), AC-INT-12 (lecturas), AC-INT-17 (leer suspendida), AC-INT-30, AC-INT-41
  (detalle). RN-INT-04, RN-INT-20; RF-INT-03. **Zona roja:** sí (representación con credenciales).
  **Depende:** T-INT-21; **SPEC-03:** capacidades del adaptador (para `capabilities[]` y `provider_available`).
- **Archivos:** `selectors/integrations.py` (listado con `?status`), `api/integrations.py`, `api/representation.py`
  (resumen o `management` según `integration.read_detail`, design §6.5), `api/serializers/integrations.py`,
  `apps/common/api/schema.py` (`ENUM_NAME_OVERRIDES`), `backend/tests/cross_tenant/cases/integrations.py`,
  `backend/tests/integrations/api/{test_integrations_read,test_representation_by_role}.py`, contrato.
- **Pruebas:** `test_AC_INT_06_owner_sees_configured_and_date_never_secret`, `test_AC_INT_06_public_fields_and_account_full`,
  `test_AC_INT_30_operator_viewer_get_summary_without_management`, `test_AC_INT_41_detail_has_key_summary_does_not`,
  `test_AC_INT_10_get_other_org_404_and_list_excludes`, `test_AC_INT_12_superuser_without_membership_404`,
  `test_AC_INT_17_suspended_owner_reads_integrations`.

### T-INT-23 — `GET /api/integrations/{id}/capabilities/` ⛔ Q-433
- **AC:** AC-INT-10 (capacidades), AC-INT-15, AC-INT-30 (capacidades). RN-INT-11; RF-INT-07. **Zona roja:** sí
  (contrato). **Depende:** T-INT-22.
- **Archivos:** `api/integrations.py`, `selectors/catalog.py::capabilities_of`,
  `backend/tests/cross_tenant/cases/integrations.py`, `backend/tests/integrations/api/test_capabilities.py`, contrato.
- **Pruebas:** `test_AC_INT_15_capabilities_equal_adapter_declaration`, `test_AC_INT_30_viewer_gets_capabilities_200`,
  `test_AC_INT_10_capabilities_other_org_404`.

### T-INT-24 — Servicio de alta y escritura del juego (`writes.py`) ⛔ Q-433
- **AC:** AC-INT-01, AC-INT-03, AC-INT-04 (validación), AC-INT-05, AC-INT-28, AC-INT-29, AC-INT-31 (alta), AC-INT-38
  (alta). RN-INT-01…04, 07, 16, 19, 22; RF-INT-02. **Zona roja:** sí (credenciales, cuenta entre organizaciones).
  **Depende:** T-INT-06, T-INT-09, T-INT-20, T-INT-21; **SPEC-03:** `test_connection()`/`ConnectionStatus`, errores con
  `reason`, adaptador construido con un `IntegrationContext` candidato.
- **Archivos:** `services/create_integration.py`, `services/writes.py` (~90: cifrar y escribir el juego, aplicar el
  resultado, traducir `IntegrityError` por `constraint_name`), `apps/integrations/errors.py`,
  `backend/tests/integrations/services/{test_create_integration,test_create_account_reservation}.py`.
- **Cambios:** design §4.1 (prueba fuera de transacción; `atomic` + savepoint); logs `integrations.connection_test`.
- **Pruebas:** `test_AC_INT_01_create_connected_sets_created_by_and_event`, `test_AC_INT_03_unregistered_provider_rejected`,
  `test_AC_INT_04_missing_or_bad_environment_rejected`, `test_AC_INT_05_invalid_fields_never_call_test_connection`,
  `test_AC_INT_28_same_name_conflict_and_other_org_ok`, `test_AC_INT_29_account_taken_elsewhere_rejected_without_details`,
  `test_AC_INT_31_create_outcomes` (parametrizado), `test_AC_INT_38_disconnect_frees_account_for_create`.

### T-INT-25 — `POST /api/integrations/` ⛔ Q-433
- **AC:** AC-INT-01 (API), AC-INT-02, AC-INT-11 (crear), AC-INT-17 (crear). RNF-INT-09. **Zona roja:** sí.
  **Depende:** T-INT-22, T-INT-24.
- **Archivos:** `api/integrations.py`, `api/serializers/integrations.py` (`credentials` `write_only`),
  `apps/common/api/problems.py` (`connection_test_failed`, `account_already_connected`),
  `backend/tests/cross_tenant/cases/integrations.py`, `backend/tests/integrations/api/test_create_integration_api.py`, contrato.
- **Pruebas:** `test_AC_INT_01_post_returns_201_with_connection_test`, `test_AC_INT_02_organization_id_in_body_is_unknown_field`,
  `test_AC_INT_11_operator_viewer_cannot_create`, `test_AC_INT_17_suspended_rejects_create`,
  `test_AC_INT_29_conflict_body_is_constant`.

### T-INT-26 — Resolución de credenciales (`resolve_integration_context`) ⛔ Q-433
- **AC:** AC-INT-04 (contexto), AC-INT-16, AC-INT-17 (tarea de sistema), AC-INT-18 (sistema), AC-INT-44 (resolución).
  RN-INT-05, RN-INT-15; RF-INT-08. **Zona roja:** sí. **Depende:** T-INT-24; **SPEC-03:** `IntegrationContext`,
  `Credentials` con `repr` redactado (AC-ENG-05).
- **Archivos:** `services/resolve_context.py`, `selectors/credentials.py`, `backend/tests/integrations/services/test_resolve_context.py`.
- **Cambios:** design §4.8; desconectada → `IntegrationWithoutCredentials`; `key_id` ausente → log
  `integrations.cipher_key_missing` (no pasa a `credenciales inválidas`); log `integrations.context_resolved`.
- **Pruebas:** `test_AC_INT_04_context_carries_environment`, `test_AC_INT_16_other_org_context_raises_and_decrypts_nothing`,
  `test_AC_INT_17_system_task_resolves_for_suspended_org`, `test_AC_INT_18_system_task_resolves_inactive_integration`,
  `test_AC_INT_44_resolves_with_old_and_new_key`, `test_RN_INT_05_copied_ciphertext_fails_aad`.

### T-INT-27 — `provider_session` y `ProviderAuthError` en una operación real ⛔ Q-433
- **AC:** AC-INT-32. RN-INT-21; RF-INT-13; Q-409. **Zona roja:** sí. **Depende:** T-INT-26; **SPEC-03:**
  `ProviderAuthError`, `BaseAdapter(context)`, operaciones reales del `FakeAdapter` (p. ej. `get_charge`).
- **Archivos:** `services/provider_gateway.py::provider_session` (sin `new_charge` todavía), `services/auth_failure.py::
  report_provider_auth_error`, `backend/tests/integrations/services/test_provider_session.py`.
- **Cambios:** design §4.7 pasos 1, 2, 4, 5, 6 (el 3 es T-INT-36); `TransactionManagementError` dentro de una
  transacción; solo aplica si el juego sigue en la versión leída; actor `SYSTEM`; log `integrations.provider_auth_failure`.
- **Pruebas:** `test_AC_INT_32_auth_error_marks_invalid_once_without_retry`, `test_AC_INT_32_success_does_not_change_status`,
  `test_RN_INT_21_stale_version_does_not_overwrite`, `test_RN_INT_05_session_inside_atomic_raises`.

### T-INT-28 — Servicio de prueba de conexión a pedido ⛔ Q-433
- **AC:** AC-INT-13, AC-INT-14, AC-INT-36, AC-INT-45 (prueba). RN-INT-10, RN-INT-21; RF-INT-05; Q-419 a). **Zona roja:**
  sí. **Depende:** T-INT-09, T-INT-26; **SPEC-03:** `test_connection`, `FakeAdapter` que registra operaciones y simula
  timeout.
- **Archivos:** `services/test_connection.py`, `backend/tests/integrations/services/{test_manual_connection_test,
  test_manual_test_accounts}.py`.
- **Cambios:** design §4.4: versión del juego probada, resultado viejo descartado (`409 conflict`), estado escrito antes
  del `409` de cuenta (§4.2); evento solo si cambia el estado; logs `connection_test` y `connection_status_changed`.
- **Pruebas:** `test_AC_INT_13_outcomes_update_status_and_event` (parametrizado, incluye Q-425),
  `test_AC_INT_14_only_test_connection_invoked_and_no_mutation`, `test_AC_INT_36_unknown_account_then_connected_free`,
  `test_AC_INT_36_account_already_connected_persists_error`, `test_AC_INT_45_other_account_keeps_unconfirmed`,
  `test_AC_INT_45_same_account_confirms`, `test_RN_INT_10_stale_result_discarded`.

### T-INT-29 — `POST …/test-connection/` y throttle ⛔ Q-433
- **AC:** AC-INT-10 (probar), AC-INT-11 (probar), AC-INT-13 (API), AC-INT-14 (timeout), AC-INT-17 (probar; Q-417 a)).
  RNF-INT-08. **Zona roja:** sí. **Depende:** T-INT-22, T-INT-28.
- **Archivos:** `api/integration_actions.py`, `api/throttling.py::ConnectionTestThrottle`, `config/settings/base.py`
  (`INTEGRATIONS_CONNECTION_TEST_RATE`), `apps/common/api/problems.py` (`account_mismatch`),
  `backend/tests/cross_tenant/cases/integrations.py`, `backend/tests/integrations/api/test_connection_test_api.py`, contrato.
- **Cambios:** design §6.3; verificar que el timeout del worker de gunicorn supera el presupuesto (si no, se reporta;
  su configuración vive fuera de `apps/` y es zona roja).
- **Pruebas:** `test_AC_INT_13_response_has_normalized_reason_only`, `test_AC_INT_14_hanging_fake_answers_within_timeout`,
  `test_AC_INT_10_test_other_org_404`, `test_AC_INT_11_operator_cannot_test`, `test_AC_INT_17_suspended_rejects_test`,
  `test_RNF_INT_08_throttle_returns_429_with_retry_after`.

### T-INT-30 — `PATCH /api/integrations/{id}/` (datos no secretos) ⛔ Q-433
- **AC:** AC-INT-10 (PATCH), AC-INT-11 (editar), AC-INT-17 (editar), AC-INT-31 (editar sin prueba). RN-INT-03 (Q-414 a)),
  RN-INT-07. **Zona roja:** sí. **Depende:** T-INT-20, T-INT-22; **SPEC-03:** `field_schema.configuration`.
- **Archivos:** `services/update_integration.py`, `api/integrations.py`, `backend/tests/integrations/api/test_update_integration.py`, contrato.
- **Cambios:** `{name?, configuration?}`; `environment` → `read_only`; `integration.updated` con `changed_fields` (nombres,
  nunca valores); nombre ocupado → `409 conflict`.
- **Pruebas:** `test_AC_INT_31_edit_configuration_never_calls_test_connection`, `test_AC_INT_10_patch_other_org_404`,
  `test_AC_INT_11_operator_cannot_patch`, `test_AC_INT_17_suspended_rejects_patch`, `test_Q_414_environment_is_read_only`.

### T-INT-31 — Servicio de reemplazo de credenciales ⛔ Q-433
- **AC:** AC-INT-09, AC-INT-31 (reemplazo), AC-INT-37, AC-INT-44 (reemplazo con la clave nueva), AC-INT-45 (reemplazo).
  RN-INT-06, RN-INT-19, RN-INT-22. **Zona roja:** sí. **Depende:** T-INT-24, T-INT-26.
- **Archivos:** `services/replace_credentials.py` (~200), `services/writes.py`,
  `backend/tests/integrations/services/{test_replace_credentials,test_replace_concurrency}.py`.
- **Cambios:** design §4.3 (pasos 1–5, reemplazo): una sola `UPDATE`, `version+1`, control de versión bajo lock.
- **Pruebas:** `test_AC_INT_09_concurrent_resolution_sees_j1_or_j2_whole` (hilos, `transaction=True`),
  `test_AC_INT_31_replace_outcomes` (parametrizado), `test_AC_INT_37_other_account_keeps_j1`, `test_AC_INT_37_same_account_accepted`,
  `test_AC_INT_44_new_replace_sealed_with_active_key`, `test_AC_INT_45_unreachable_replace_marks_unconfirmed`,
  `test_RN_INT_06_two_admins_second_gets_conflict`.

### T-INT-32 — `PUT /api/integrations/{id}/credentials/` ⛔ Q-433
- **AC:** AC-INT-10 (reemplazar), AC-INT-11 (reemplazar), AC-INT-17 (reemplazar). **Zona roja:** sí.
  **Depende:** T-INT-22, T-INT-31.
- **Archivos:** `api/integration_actions.py`, `api/urls.py`, `apps/common/api/problems.py` (si falta algún código),
  `backend/tests/cross_tenant/cases/integrations.py`, `backend/tests/integrations/api/test_replace_credentials_api.py`, contrato.
- **Pruebas:** `test_AC_INT_10_replace_other_org_404`, `test_AC_INT_11_operator_cannot_replace`,
  `test_AC_INT_17_suspended_rejects_replace`, `test_RN_INT_22_replace_disconnected_is_invalid_transition`.

### T-INT-33 — API del ciclo de vida (desactivar, reactivar, desconectar; sin `DELETE`) ⛔ Q-433
- **AC:** AC-INT-10, AC-INT-11, AC-INT-17 (ciclo de vida), AC-INT-25 (API), AC-INT-33 (API, sin borrado físico).
  RF-INT-06. **Zona roja:** sí. **Depende:** T-INT-11, T-INT-22.
- **Archivos:** `api/integration_actions.py`, `api/urls.py`, `apps/common/api/problems.py` (`pending_charges`),
  representación con `management.disconnect_blocked_reason`, `backend/tests/cross_tenant/cases/integrations.py`,
  `backend/tests/integrations/api/test_lifecycle_api.py`, contrato.
- **Pruebas:** `test_AC_INT_25_reactivate_active_returns_invalid_transition`, `test_AC_INT_33_delete_is_405`,
  `test_AC_INT_33_disconnect_with_pending_returns_409`, `test_AC_INT_10_lifecycle_other_org_404`,
  `test_AC_INT_11_operator_cannot_change_lifecycle`, `test_AC_INT_17_suspended_rejects_lifecycle`.

### T-INT-34 — Reactivar una desconectada con un juego nuevo ⛔ Q-433
- **AC:** AC-INT-28 (reactivar con el nombre ocupado), AC-INT-33 (reactivar), AC-INT-42, AC-INT-45 (reactivación).
  RN-INT-19, RN-INT-22, RN-INT-24; Q-427, Q-430 a). **Zona roja:** sí. **Depende:** T-INT-31, T-INT-33.
- **Archivos:** `services/integration_lifecycle.py::reactivate` (rama desconectada; reutiliza `writes.py`),
  `api/integration_actions.py` (`{credentials?}`), `backend/tests/integrations/services/test_reactivate_disconnected.py`.
- **Pruebas:** `test_AC_INT_33_reactivate_without_set_rejected`, `test_AC_INT_33_reactivate_same_account_active`,
  `test_AC_INT_42_other_account_stays_disconnected`, `test_AC_INT_42_account_taken_elsewhere_rejected_without_details`,
  `test_AC_INT_42_free_account_reserved_again`, `test_AC_INT_45_unreachable_reactivation_marks_unconfirmed`,
  `test_AC_INT_28_reactivate_disconnected_with_taken_name`.

### T-INT-35 — "Integración utilizable" y lock del cobro nuevo ⛔ Q-433
- **AC:** AC-INT-18 (integración), AC-INT-36 (selector), AC-INT-45 (selector y lock). RN-INT-26; RF-INT-11; Q-422 a).
  **Zona roja:** sí (SQL crudo, aislamiento). **Depende:** T-INT-21, T-INT-31; **SPEC-03:** `Capability`, registry
  (provider disponible).
- **Archivos:** `selectors/usability.py::get_usable_integration` (+ `IntegrationNotUsable`), `selectors/locks.py::
  lock_integration_for_new_charge -> NewChargeLock`, `tests/architecture/allowlists.py` (`TENANT_QUERY_ALLOWLIST`,
  `count=1`), `backend/tests/integrations/services/{test_integration_usability,test_new_charge_lock}.py`.
- **Pruebas:** `test_AC_INT_18_inactive_integration_not_usable`, `test_AC_INT_36_unknown_account_not_usable`,
  `test_AC_INT_45_unconfirmed_not_usable_and_lock_rejects`, `test_RN_INT_24_disconnect_vs_new_charge_lock` (hilos),
  `test_Q_422_provider_flag_off_not_usable`, `test_RN_INT_26_other_org_not_found`.

### T-INT-36 — `provider_session` con `NewChargeLock` ⛔ Q-433
- **AC:** AC-INT-45 (concurrencia). RN-INT-15, RN-INT-26. **Zona roja:** sí. **Depende:** T-INT-27, T-INT-35.
- **Archivos:** `services/provider_gateway.py` (paso 3 de design §4.7; `NEW_CHARGE_OPERATIONS`),
  `backend/tests/integrations/services/test_session_new_charge.py`.
- **Pruebas:** `test_AC_INT_45_replace_between_lock_and_call_fails_without_calls` (hilos, design §9),
  `test_AC_INT_45_existing_charge_operation_still_uses_current_set`, `test_RN_INT_26_create_charge_without_lock_is_type_error`,
  `test_RN_INT_26_version_changed_reason_credentials_changed`.

### T-INT-37 — Servicio de alta de vínculo (crear, importar, manual, sin referencia) ⛔ Q-433
- **AC:** AC-INT-34 (alta), AC-INT-39, AC-INT-43 (alta duplicada), AC-INT-46 (vínculo). RN-INT-23; Q-424, Q-428,
  Q-431 b), Q-432 a). **Zona roja:** sí. **Depende:** T-INT-17, T-INT-20, T-INT-27; **SPEC-03:** `POS_MANAGEMENT`,
  `field_schema.branch_link`, `ensure_store(EnsureStore)`, `list_stores()`, `CapabilityNotSupported`.
- **Archivos:** `services/branch_links.py::create_branch_link` (total del archivo ~220), `apps/integrations/errors.py`,
  `backend/tests/integrations/services/{test_create_branch_link,test_create_branch_link_activity}.py`.
- **Cambios:** design §4.6: chequeo de actividad, llamada al proveedor fuera de transacción, re-chequeo bajo lock en el
  orden fijo, savepoint.
- **Pruebas:** `test_AC_INT_34_create_link_with_valid_data_and_event`, `test_AC_INT_34_missing_required_data_names_field`,
  `test_AC_INT_39_create_mode_calls_ensure_store`, `test_AC_INT_39_import_mode_uses_list_stores`,
  `test_AC_INT_39_import_ref_not_listed_rejected`, `test_AC_INT_39_without_pos_management_manual_or_none_no_calls`,
  `test_AC_INT_43_second_link_conflict`, `test_AC_INT_46_inactive_integration_or_branch_rejected_without_calls`,
  `test_AC_INT_46_deactivation_between_call_and_insert_rejected`.

### T-INT-38 — `POST /api/branch-links/` y `GET …/provider-stores/` ⛔ Q-433
- **AC:** AC-INT-10 (Stores), AC-INT-11 (Stores), AC-INT-17 (crear vínculo), AC-INT-21 (crear vínculo), AC-INT-34 (de
  otra organización). **Zona roja:** sí. **Depende:** T-INT-22, T-INT-37.
- **Archivos:** `api/branch_links.py`, `api/integration_actions.py` (`provider-stores`), `services/provider_lookup.py`,
  `apps/common/api/problems.py` (`resource_inactive`, `capability_not_supported`, `provider_rejected`,
  `provider_unavailable`, `integration_without_credentials`), `backend/tests/cross_tenant/cases/{branch_links,
  integrations}.py`, `backend/tests/integrations/api/test_branch_links_create_api.py`, contrato.
- **Pruebas:** `test_AC_INT_34_branch_or_integration_of_other_org_404`, `test_AC_INT_21_operator_cannot_create_link`,
  `test_AC_INT_17_suspended_rejects_create_link`, `test_AC_INT_11_operator_cannot_list_stores`,
  `test_AC_INT_10_stores_of_other_org_404`, `test_RN_INT_23_stores_without_pos_management_409`.

### T-INT-39 — Servicio de alta de Caja (crear, importar, manual) ⛔ Q-433
- **AC:** AC-INT-19, AC-INT-35, AC-INT-40 (sin Caja nueva sobre un vínculo inactivo), AC-INT-46 (Caja). RN-INT-12;
  Q-411, Q-424, Q-431 b). **Zona roja:** sí. **Depende:** T-INT-19, T-INT-37; **SPEC-03:** `ensure_pos(EnsurePos)`,
  `list_pos()`.
- **Archivos:** `services/cash_registers.py::create_cash_register` (total del archivo ~230),
  `backend/tests/integrations/services/test_create_cash_register.py`.
- **Pruebas:** `test_AC_INT_19_create_with_active_link`, `test_AC_INT_19_without_or_inactive_link_rejected`,
  `test_AC_INT_35_create_mode_calls_ensure_pos`, `test_AC_INT_35_import_mode_uses_list_pos`,
  `test_AC_INT_35_manual_without_pos_management_no_calls`, `test_AC_INT_35_create_or_import_without_capability_409`,
  `test_AC_INT_40_no_new_cash_register_on_inactive_link`, `test_AC_INT_46_cash_register_on_inactive_integration_or_branch_rejected`.

### T-INT-40 — `POST /api/cash-registers/` y `GET /api/branch-links/{id}/provider-pos/` ⛔ Q-433
- **AC:** AC-INT-11 (POS), AC-INT-17 (crear Caja), AC-INT-19 (de otra organización), AC-INT-21 (crear Caja). **Zona
  roja:** sí. **Depende:** T-INT-38, T-INT-39.
- **Archivos:** `api/cash_registers.py`, `api/branch_links.py` (`provider-pos`), `services/provider_lookup.py`,
  `apps/common/api/problems.py` (`branch_link_required`), `backend/tests/cross_tenant/cases/{cash_registers,
  branch_links}.py`, `backend/tests/integrations/api/test_cash_registers_create_api.py`, contrato.
- **Pruebas:** `test_AC_INT_19_branch_or_integration_of_other_org_404`, `test_AC_INT_21_operator_cannot_create_cash_register`,
  `test_AC_INT_17_suspended_rejects_create_cash_register`, `test_AC_INT_11_operator_cannot_list_pos`.

### T-INT-41 — Suite de secretos (RNF-INT-01) ⛔ Q-433
- **AC:** AC-INT-07, AC-INT-08 (otros caminos). RN-INT-04; RNF-INT-01. **Zona roja:** sí. **Depende:** T-INT-25,
  T-INT-29, T-INT-32, T-INT-33.
- **Archivos:** `backend/tests/integrations/security/{test_no_secret_leaks,test_no_secret_in_repr}.py`.
- **Cambios:** valor sintético conocido en crear, reemplazar, probar con `AUTH_INVALID`, resolver y desconectar; se
  busca en logs capturados (structlog), cuerpos de respuesta y de error, eventos del `RecordingSink`, `repr`/`str` de
  modelos, DTOs y excepciones; la fila de la BD no tiene el valor en claro.
- **Pruebas:** `test_AC_INT_07_secret_never_leaks` (parametrizado por camino), `test_AC_INT_08_no_plaintext_after_replace`.

### T-INT-42 — Completitud: cross-tenant, suspendida, auditoría y rutas ⛔ Q-433
- **AC:** AC-INT-10, AC-INT-12, AC-INT-17, AC-INT-20, AC-INT-22, AC-INT-23, AC-INT-24. RNF-INT-03, RNF-INT-05.
  **Zona roja:** sí. **Depende:** T-INT-23, T-INT-30, T-INT-34, T-INT-36, T-INT-40, T-INT-41.
- **Archivos:** `backend/tests/cross_tenant/cases/{integrations,branch_links,cash_registers}.py` (huecos),
  `backend/tests/integrations/test_audit_triggers.py` (`AUDIT_TRIGGERS` parametrizado sobre `IntegrationsAuditAction`).
- **Pruebas:** `test_AC_INT_24_every_route_has_case`, `test_AC_INT_23_every_action_has_trigger_without_secrets`,
  `test_AC_INT_17_every_write_rejected_when_suspended`, `test_AC_INT_12_every_route_404_without_membership`,
  `test_AC_INT_22_no_oauth_routes` (vuelve a correr sobre todas las rutas).

### T-INT-43 — Frontend: lista de integraciones y entrada de Configuración ⛔ Q-433 · Q-434
- **AC:** — (RF-INT-03, spec §14). **Zona roja:** no. **Depende:** T-INT-22 y el cambio de SPEC-02 que pide **Q-434
  a)** (decidida por el dueño el 2026-11-27): el detalle de la organización activa suma `integration_provider.list` a
  `allowed_actions`. Ese cambio no tiene tarea todavía: es de SPEC-02 (contrato compatible, con entrada en el Historial
  de 02 y su propio PR) y no se crea desde esta lista. Mientras no exista y esté mergeado, esta fila sigue con Q-434 en
  Evidencia; cuando tenga ID (`T-TEN-NN`), se reemplaza acá "cambio de SPEC-02 por Q-434" por ese ID.
- **Archivos:** `frontend/src/app/(dashboard)/configuracion/integraciones/page.tsx`,
  `frontend/src/modules/integrations/components/{IntegrationsScreen,IntegrationCard,ConnectionStatusChip}.tsx`,
  `frontend/src/modules/integrations/hooks/useIntegrations.ts`, `frontend/src/modules/settings/settings-sections.ts`
  (`href` y `requires: "integration_provider.list"` de "Integraciones"; el tipo de `requires` se amplía si hace falta),
  tests `*.test.tsx`.
- **Cambios:** design §3.9: tarjetas, filtro activas/inactivas/desconectadas, vacío "Todavía no conectaste ningún
  proveedor", `PageSkeleton`, error con "Reintentar", "sin permiso", suspendida; query keys `['org', orgId, 'integrations', …]`.
- **Pruebas:** `IntegrationsScreen.test.tsx` (vacío, error, lista, sin permiso), `settings-sections.test.ts` (sección
  oculta sin `integration_provider.list`, Q-434 a)).

### T-INT-44 — Frontend: `SchemaFields` y `schema-to-zod` ⛔ Q-433
- **AC:** — (RF-INT-01, RN-INT-07). **Zona roja:** sí (campos secretos). **Depende:** T-INT-21.
- **Archivos:** `frontend/src/modules/integrations/lib/schema-to-zod.ts`, `frontend/src/modules/integrations/components/SchemaFields.tsx`, tests.
- **Cambios:** `FieldSpec[]` → zod (requerido, `pattern`, `max_length`, `choices`); campos `secret` con
  `type="password"`, `autoComplete="new-password"`, sin valor inicial.
- **Pruebas:** `schema-to-zod.test.ts`, `SchemaFields.test.tsx` (secreto sin valor inicial; error que nombra el campo).

### T-INT-45 — Frontend: alta de integración ⛔ Q-433
- **AC:** — (RF-INT-02, spec §14 "Alta"). **Zona roja:** sí (credenciales en el navegador). **Depende:** T-INT-25,
  T-INT-43, T-INT-44.
- **Archivos:** `frontend/src/modules/integrations/components/CreateIntegrationDialog.tsx`,
  `frontend/src/modules/integrations/hooks/{useProviderCatalog,useIntegrationMutations}.ts`, tests.
- **Cambios:** pasos proveedor → nombre + ambiente → `SchemaFields`; resultado de la prueba con texto accionable;
  `account_already_connected` sin decir dónde; mutación con `gcTime: 0` y `reset()` en `onSettled`; `reset()` del
  formulario al cerrar.
- **Pruebas:** `CreateIntegrationDialog.test.tsx` (cada resultado; el secreto no queda en el `MutationCache`).

### T-INT-46 — Frontend: detalle y "Probar conexión" ⛔ Q-433
- **AC:** — (RF-INT-03, RF-INT-05). **Zona roja:** sí (muestra `account_id`, configuración y los secretos como
  "Configurado"). **Depende:** T-INT-29, T-INT-43.
- **Archivos:** `frontend/src/app/(dashboard)/configuracion/integraciones/[id]/page.tsx`,
  `frontend/src/modules/integrations/components/{IntegrationDetailScreen,ConnectionTestButton}.tsx`,
  `frontend/src/modules/integrations/lib/connection-messages.ts`, `frontend/src/modules/integrations/hooks/useIntegration.ts`, tests.
- **Cambios:** datos no secretos y `account_id` completos; secretos como "Configurado · actualizado el …"; resultado en
  `Alert`; `429` con el aviso de esperar.
- **Pruebas:** `IntegrationDetailScreen.test.tsx` (nunca un valor secreto), `connection-messages.test.ts` (todo `reason`
  de design §6.2 tiene texto).

### T-INT-47 — Frontend: identificador de webhooks (Copiar, Regenerar) ⛔ Q-433
- **AC:** — (RF-INT-14). **Zona roja:** sí (identificador de ruteo, Q-415). **Depende:** T-INT-13, T-INT-46.
- **Archivos:** `frontend/src/modules/integrations/components/WebhookKeyPanel.tsx`, test.
- **Pruebas:** `WebhookKeyPanel.test.tsx` (confirmación que avisa pegar la URL nueva; el valor no va a logs ni a la URL).

### T-INT-48 — Frontend: reemplazar credenciales y ciclo de vida ⛔ Q-433
- **AC:** — (RF-INT-04, RF-INT-06). **Zona roja:** sí (credenciales). **Depende:** T-INT-32, T-INT-34, T-INT-44, T-INT-46.
- **Archivos:** `frontend/src/modules/integrations/components/{CredentialsDialog,IntegrationLifecycleDialogs}.tsx`, tests.
- **Cambios:** reemplazar o reactivar una desconectada con el mismo formulario; "Desconectar" deshabilitado con el
  motivo si `management.disconnect_blocked_reason`; acciones según `allowed_actions`.
- **Pruebas:** `CredentialsDialog.test.tsx` (sin precarga, `reset()`), `IntegrationLifecycleDialogs.test.tsx`.

### T-INT-49 — Frontend: detalle de sucursal con sus vínculos ⛔ Q-433
- **AC:** — (RF-INT-10, spec §14 "Sucursales y cajas"). **Zona roja:** no. **Depende:** T-INT-17, T-INT-38, T-INT-44;
  prerrequisito de documentos (Q-220 alineada en 02 y `context/07`).
- **Archivos:** `frontend/src/app/(dashboard)/configuracion/sucursales/[id]/page.tsx`,
  `frontend/src/modules/integrations/components/{BranchDetailScreen,BranchLinksPanel,BranchLinkDialog}.tsx`,
  `frontend/src/modules/integrations/hooks/{useBranchLinks,useProviderLookups}.ts`,
  `frontend/src/modules/tenancy/components/BranchDetailLink.tsx` (nuevo) y `BranchesTable.tsx` (solo lo importa; ver
  C-14), `frontend/src/modules/settings/settings-sections.ts` ("Sucursales y cajas" → módulos `02` y `04`), tests.
- **Pruebas:** `BranchLinkDialog.test.tsx` (modos según capacidades; `SchemaFields` de `branch_link`),
  `BranchLinksPanel.test.tsx` (lectura para operator/viewer).

### T-INT-50 — Frontend: Cajas de la sucursal ⛔ Q-433
- **AC:** — (RF-INT-09, spec §14 "Sucursales y cajas"). **Zona roja:** no. **Depende:** T-INT-19, T-INT-40, T-INT-49.
- **Archivos:** `frontend/src/modules/integrations/components/{CashRegistersTable,CashRegisterDialog}.tsx`,
  `frontend/src/modules/integrations/hooks/useCashRegisters.ts`, tests.
- **Cambios:** por vínculo activo; "crear en el proveedor" / "importar existente" (lista de `provider-pos`) / "ligar a
  mano"; `is_usable` del backend; el texto de `409 conflict` en `provider_ref` explica el caso del renombre.
- **Pruebas:** `CashRegisterDialog.test.tsx`, `CashRegistersTable.test.tsx`.

### T-INT-51 — Frontend: tarjetas de integraciones en Inicio ⛔ Q-433
- **AC:** — (RF-INT-03, spec §14 "Inicio"). **Zona roja:** no. **Depende:** T-INT-22.
- **Archivos:** `frontend/src/modules/integrations/components/IntegrationStatusCards.tsx`,
  `frontend/src/app/(dashboard)/inicio/page.tsx`, test.
- **Cambios:** resumen de RN-INT-20 (estado de conexión + capacidades) para todos los roles; "último evento" lo suma SPEC-07.
- **Pruebas:** `IntegrationStatusCards.test.tsx`.

### T-INT-52 — Humo E2E por HTTP con `FakeAdapter` ⛔ Q-433
- **AC:** AC-INT-01 (humo), AC-INT-33 (humo), AC-INT-35 (humo). **Zona roja:** sí (`scripts/**`). **Depende:** T-INT-34,
  T-INT-40, T-INT-42.
- **Archivos:** `scripts/e2e_integrations.py`, `scripts/tests/test_e2e_integrations.py`.
- **Cambios:** como `scripts/e2e_tenancy.py` (por HTTP, sin navegador): alta → prueba → vínculo → Caja → desconectar,
  con `INTEGRATIONS_PROVIDER_FAKE` en dev.
- **Pruebas:** `test_AC_INT_01_smoke_create`, `test_AC_INT_35_smoke_cash_register`, `test_AC_INT_33_smoke_disconnect`.

## Conciliación con git (generada, no editar a mano)

> La genera `python scripts/check_spec_state.py --write` a partir de `git log` y del estado de la tabla de
> resumen. No se edita a mano: el bloque se reemplaza completo.

<!-- check_spec_state:begin -->
| Tarea | PR | SHA | Estado |
|---|---|---|---|
| T-INT-01 | — | — | ☐ |
| T-INT-02 | — | — | ☐ |
| T-INT-03 | — | — | ☐ |
| T-INT-04 | — | — | ☐ |
| T-INT-05 | — | — | ☐ |
| T-INT-06 | — | — | ☐ |
| T-INT-07 | — | — | ☐ |
| T-INT-08 | — | — | ☐ |
| T-INT-09 | — | — | ☐ |
| T-INT-10 | — | — | ☐ |
| T-INT-11 | — | — | ☐ |
| T-INT-12 | — | — | ☐ |
| T-INT-13 | — | — | ☐ |
| T-INT-14 | — | — | ☐ |
| T-INT-15 | — | — | ☐ |
| T-INT-16 | — | — | ☐ |
| T-INT-17 | — | — | ☐ |
| T-INT-18 | — | — | ☐ |
| T-INT-19 | — | — | ☐ |
| T-INT-20 | — | — | ⛔ |
| T-INT-21 | — | — | ⛔ |
| T-INT-22 | — | — | ⛔ |
| T-INT-23 | — | — | ⛔ |
| T-INT-24 | — | — | ⛔ |
| T-INT-25 | — | — | ⛔ |
| T-INT-26 | — | — | ⛔ |
| T-INT-27 | — | — | ⛔ |
| T-INT-28 | — | — | ⛔ |
| T-INT-29 | — | — | ⛔ |
| T-INT-30 | — | — | ⛔ |
| T-INT-31 | — | — | ⛔ |
| T-INT-32 | — | — | ⛔ |
| T-INT-33 | — | — | ⛔ |
| T-INT-34 | — | — | ⛔ |
| T-INT-35 | — | — | ⛔ |
| T-INT-36 | — | — | ⛔ |
| T-INT-37 | — | — | ⛔ |
| T-INT-38 | — | — | ⛔ |
| T-INT-39 | — | — | ⛔ |
| T-INT-40 | — | — | ⛔ |
| T-INT-41 | — | — | ⛔ |
| T-INT-42 | — | — | ⛔ |
| T-INT-43 | — | — | ⛔ |
| T-INT-44 | — | — | ⛔ |
| T-INT-45 | — | — | ⛔ |
| T-INT-46 | — | — | ⛔ |
| T-INT-47 | — | — | ⛔ |
| T-INT-48 | — | — | ⛔ |
| T-INT-49 | — | — | ⛔ |
| T-INT-50 | — | — | ⛔ |
| T-INT-51 | — | — | ⛔ |
| T-INT-52 | — | — | ⛔ |
<!-- check_spec_state:end -->
