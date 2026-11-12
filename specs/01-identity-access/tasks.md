---
spec: SPEC-01
actualizado: 2026-11-06
---
# Tareas — Módulo de Identidad y Acceso

Reglas: rebanada vertical · ≤ ~300 líneas de diff · mergeable sola · cita AC · lista archivos esperados · incluye su plan de pruebas.

> Entradas: `spec.sdd.md` **Approved 1.0.2**, `design.md` **Aprobado**, `clarifications.md` (incluida "Confirmación
> (2026-11-06)"), ADR-0004 (**Aceptado** 2026-11-07),
> `context/08-control-de-versiones-ci-cd.md`.
> **Se cierra junto con SPEC-02 (Q-108):** ninguno de los dos pasa a `Verified` sin el otro.
> `specs/02-tenancy-rbac/tasks.md` depende de `T-IDA-01`, `T-IDA-06`, `T-IDA-07`, `T-IDA-13`, `T-IDA-27` y `T-IDA-29`.
> Lo que cruza de vuelta: `T-TEN-12`, `T-TEN-17` y `T-TEN-18` cierran AC de este módulo con los puertos reales.

## Convenciones de esta lista
- **Tamaño** (líneas de diff, **sin** lockfiles ni los generados `specs/_contracts/openapi.yaml` y
  `frontend/src/types/api.d.ts`): **S** ≤ 100 · **M** ≤ 200 · **L** ≤ 300.
- **Zona roja = reviewer obligatorio** (label `zona-roja` + veredicto que cita el SHA). Todo `backend/apps/identity/**`
  es zona roja por `.github/zona-roja-paths.txt`, y desde `T-IDA-22` también `frontend/src/app/api/**` y
  `frontend/src/lib/server/**`. Solo `T-IDA-29` y `T-IDA-30`, de pantallas, no lo son.
- **Ninguna tarea toca `.github/workflows/`**: si una lo necesitara, es scope drift y el PR lo mergea el dueño (Q-063).
- **Contrato:** toda tarea que agrega o cambia un endpoint corre `export_openapi` y `openapi:types` y commitea el
  resultado (AC-PLT-23). `auth/bff/*` va con tag `bff-internal`.
- **Variables de entorno:** toda variable nueva va en `backend/config/settings/env.py` y en `env.example` en la misma
  tarea (AC-PLT-05). Una del BFF va además en `FRONTEND_SERVER_VARS`.
- **Tests:** `test_AC_IDA_NN_<caso>`. Lo que no tiene AC propio se nombra por su RF, RN o RNF
  (`test_RNF_IDA_06_<caso>`). Google nunca se llama en CI (`design.md §9`).
- **C-01:** cada `.objects` nuevo en `apps/identity/services/` necesita su entrada en `ALLOWED_TENANT_MANAGERS`
  (`backend/tests/architecture/allowlists.py`), con motivo "entidad global, spec §9". La regla falla por entrada
  muerta o sin motivo, así que la entrada viaja con el código que la usa.

### Estados de una tarea
Los de `specs/00-platform/tasks.md`: ☐ pendiente · 🔄 en curso · 🟡 en revisión · ✅ mergeada (PR **y** SHA) · 🧪 verificada
· ⛔ bloqueada (`Q-xxx`). Camino: `☐ → 🔄 → 🟡 → ✅ → 🧪`. La fila se actualiza en el mismo PR que cambia el estado.

## Ramas, PR y merge
- **Prerrequisito:** esta lista, los diseños y las specs 1.0.1 se mergean a `main` antes de abrir `task/T-IDA-…`.
- Cada tarea en `task/T-IDA-NN-slug` desde `main` actualizado; un PR por tarea; merge squash con
  `--match-head-commit <sha>`. Quién mergea: Q-057 (`AGENTS.md`).
- `backend/config/settings/`, `env.py`, `env.example` y `ALLOWED_TENANT_MANAGERS` los tocan muchas tareas: en paralelo
  habrá conflictos chicos; se rebasea antes de pedir veredicto.

## Ajustes al diseño
El diseño se escribió antes de que existiera el código de SPEC-00. Donde difieren, manda esta tabla.

| `design.md` dice | Se implementa | Por qué |
|---|---|---|
| `frontend/src/lib/bff/*` | `frontend/src/lib/server/*`, mismos nombres de archivo | Ya existe esa carpeta `server-only`, con el proxy (T-PLT-33/34) |
| `lib/bff/config.ts`, `HUB_API_INTERNAL_URL` | `lib/server/env.ts`, `BACKEND_INTERNAL_URL` | Ya existe; el test de paridad lee `env.ts` y `FRONTEND_SERVER_VARS` |
| `apps/identity/settings.py` con `pydantic-settings` propio | Campos en `PlatformEnv` (`config/settings/env.py`) | Es el único módulo que lee el entorno (RN-PLT-02, AC-PLT-06) |
| `APP_ENV ∈ {local, test}` | Setting `IDENTITY_FAKE_OIDC_ALLOWED`: `True` solo en `dev.py` y `test.py` | `APP_ENV` no existe: el entorno lo da `DJANGO_SETTINGS_MODULE`, y staging corre `prod.py` |
| `app/api/[...path]/route.ts` como proxy nuevo | Se extiende el existente; la parte de sesión va en `lib/server/session-proxy.ts` | `backend-proxy.ts` tiene 277 líneas (`C-14`) |
| `bootstrap_organization`, `tenancy.organization_bootstrapped` | `tenancy_create_org`, `organization.created` + `invitation.created` | Dueña SPEC-02; `design.md §6.5` y `§7.4` ya corregidos |
| E2E sin herramienta definida; SPEC-02 nombra Playwright | Script por HTTP sin navegador (`scripts/e2e_login.py`) | Playwright es dependencia nueva (`C-13`, ADR); no es necesaria para estos AC |

## Resumen

> La columna **Evidencia** es obligatoria para `✅` y la verifica `scripts/check_spec_state.py`.

| ID | Título | AC | Capa | Archivos esperados (ver detalle) | Depende de | Agente | Tamaño | Zona roja | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|---|---|
| T-IDA-00 | Guarda de `check_migrations_roundtrip` (deuda de 00) | AC-PLT-17 (regresión) | Migraciones | `check_migrations_roundtrip.py` | — | backend-dev | M | Sí | ✅ | #63 · c57db14 |
| T-IDA-01 | `User` + `AUTH_USER_MODEL` + migración 0001 | AC-IDA-31 (normalización) | DB | `apps/identity/models/user.py`, `domain/emails.py`, `domain/profile.py` | T-IDA-00 | backend-dev | L | Sí | ✅ | #65 · c5c3136 |
| T-IDA-02 | Reglas puras de sesión y formato de secretos | AC-IDA-15, AC-IDA-16, AC-IDA-28 (decisión) | Dominio | `domain/session_policy.py`, `domain/secrets_format.py`, `domain/errors.py` | T-IDA-01 | backend-dev | M | Sí | 🟡 | PR abierto |
| T-IDA-03 | `AuthSession`, `RefreshToken` + migración 0002 | AC-IDA-14 (solo hash), AC-IDA-16 (constraints) | DB | `models/auth_session.py`, `models/refresh_token.py`, `services/session_lifecycle.py` | T-IDA-02 | backend-dev | L | Sí | 🟡 | |
| T-IDA-04 | JWT del Hub: claves, emisión y verificación | AC-IDA-10, AC-IDA-11, AC-IDA-12, AC-IDA-13, AC-IDA-34 | Dominio | `tokens/keys.py`, `tokens/access_token.py`, `backend/pyproject.toml` | T-IDA-01 | backend-dev | L | Sí | 🟡 | PR abierto |
| T-IDA-05 | Puertos, stubs, registro y catálogo de auditoría | AC-IDA-24 (catálogo) | Puertos | `ports/*`, `domain/audit_events.py` | T-IDA-01 | backend-dev | M | Sí | 🟡 | PR abierto |
| T-IDA-06 | `HubJWTAuthentication` y deny-by-default | AC-IDA-10, AC-IDA-11, AC-IDA-12, AC-IDA-22, AC-IDA-26, AC-IDA-34 | API | `api/authentication.py`, `selectors/auth_sessions.py`, `config/settings/base.py` | T-IDA-03, T-IDA-04 | backend-dev | L | Sí | 🟡 | rama `task/T-IDA-06-hub-jwt-auth`, sin PR |
| T-IDA-07 | `GET /api/me` | AC-IDA-21, AC-IDA-22, AC-IDA-30 (API) | API | `api/views_me.py`, `api/urls.py`, `api/serializers.py` | T-IDA-05, T-IDA-06 | backend-dev | M | Sí | ☐ | |
| T-IDA-08 | Gateway de Google + validación del ID token | AC-IDA-07, AC-IDA-08 (`nonce`), AC-IDA-36 | Integración | `oidc/google_gateway.py`, `oidc/id_token.py`, `tests/fakes/google.py` | T-IDA-04 | backend-dev | L | Sí | ☐ | |
| T-IDA-09 | Credencial BFF, IP del cliente y throttles | AC-IDA-20, AC-IDA-37 | API | `api/bff_auth.py`, `api/client_ip.py`, `api/throttles.py`, `tests/config/test_RF_PLT_19_feature_flags.py` | T-IDA-01 | backend-dev | M | Sí | 🟡 | PR abierto |
| T-IDA-10 | Iniciar login: `LoginAttempt` + migración 0003 | AC-IDA-19 (servidor), AC-IDA-20, AC-IDA-37 | DB/API | `models/login_attempt.py`, `domain/return_path.py`, `services/login_start.py`, `api/views_bff.py`, `infra/docker-compose.yml` | T-IDA-08, T-IDA-09 | backend-dev | L | Sí | ☐ | |
| T-IDA-11 | Reglas del callback y usuario existente | AC-IDA-09 (callback), AC-IDA-29, AC-IDA-30 | Servicio | `domain/login_rules.py`, `services/user_provisioning.py` | T-IDA-03, T-IDA-05 | backend-dev | L | Sí | ☐ | |
| T-IDA-12 | Usuario nuevo por invitación y carrera de callbacks | AC-IDA-02, AC-IDA-03, AC-IDA-04, AC-IDA-05, AC-IDA-31 | Servicio | `services/user_provisioning.py` | T-IDA-11 | backend-dev | L | Sí | ☐ | |
| T-IDA-13 | Completar login: orquestación y vista | AC-IDA-01, AC-IDA-03, AC-IDA-06, AC-IDA-08, AC-IDA-09, AC-IDA-20, AC-IDA-24 (login) | Servicio/API | `services/login_complete.py`, `api/views_bff.py` | T-IDA-10, T-IDA-12 | backend-dev | L | Sí | ☐ | |
| T-IDA-14 | Refresh: rotación y vencimientos | AC-IDA-09 (refresh), AC-IDA-14, AC-IDA-16, AC-IDA-22 | Servicio/API | `services/refresh.py`, `api/views_bff.py` | T-IDA-06, T-IDA-09 | backend-dev | L | Sí | ☐ | |
| T-IDA-15 | Refresh: gracia, reuso y concurrencia | AC-IDA-15, AC-IDA-20 (refresh), AC-IDA-28 | Servicio | `services/refresh.py` | T-IDA-14 | backend-dev | M | Sí | ☐ | |
| T-IDA-16 | Logout | AC-IDA-17 (backend), AC-IDA-35 | Servicio/API | `services/logout.py`, `api/views_bff.py` | T-IDA-14 | backend-dev | M | Sí | ☐ | |
| T-IDA-17 | Sesiones propias: listar y revocar | AC-IDA-25, AC-IDA-26, AC-IDA-33 (API) | Servicio/API | `services/sessions.py`, `api/views_sessions.py`, `domain/client_hint.py` | T-IDA-06, T-IDA-13 | backend-dev | L | Sí | ☐ | |
| T-IDA-18 | Comandos de desactivar y reactivar usuario | AC-IDA-27, AC-IDA-32 (parte 01) | Comandos | `services/user_status.py`, `management/commands/*` | T-IDA-17 | backend-dev | M | Sí | ☐ | |
| T-IDA-19 | Purga periódica | AC-IDA-38 | Asíncrono | `tasks.py`, `beat.py`, `services/purge.py` | T-IDA-10, T-IDA-14 | backend-dev | M | Sí | ☐ | |
| T-IDA-20 | Chequeos de arranque y proveedor OIDC falso | — (RN-IDA-01, RN-IDA-16, RNF-IDA-06) | Config | `checks.py`, `apps.py`, `dev_oidc/*` | T-IDA-08 | backend-dev | L | Sí | ☐ | |
| T-IDA-21 | Redacción de logs, métricas y catálogo completo | AC-IDA-23, AC-IDA-24 | Observabilidad | `apps/common/domain/redaction.py`, tests de identity | T-IDA-13, T-IDA-15, T-IDA-16, T-IDA-17, T-IDA-18 | backend-dev | M | Sí | ☐ | |
| T-IDA-22 | BFF: cookies, IP, retorno y cliente a Django | AC-IDA-18, AC-IDA-19, AC-IDA-37 (BFF) | BFF | `src/lib/server/{cookies,client-ip,return-path,django,problem}.ts`, `.github/zona-roja-paths.txt` | T-IDA-10 | frontend-dev | L | Sí | ☐ | |
| T-IDA-23 | BFF: CSRF y refresh con coalescencia | AC-IDA-19 (CSRF), AC-IDA-28 (BFF) | BFF | `src/lib/server/{csrf,refresh}.ts` | T-IDA-14, T-IDA-22 | frontend-dev | M | Sí | ☐ | |
| T-IDA-24 | Route Handlers de inicio y callback | AC-IDA-01 (cookies), AC-IDA-18, AC-IDA-19 | BFF | `app/api/auth/google/{start,callback}/route.ts` | T-IDA-13, T-IDA-22 | frontend-dev | M | Sí | ☐ | |
| T-IDA-25 | Route Handlers de logout y organización activa | AC-IDA-17 (cookies) | BFF | `app/api/auth/logout/route.ts`, `app/api/session/active-organization/route.ts` | T-IDA-16, T-IDA-23 | frontend-dev | M | Sí | ☐ | |
| T-IDA-26 | Smoke: 3xx y URL de ejemplo (deuda de 00) | AC-PLT-29 (regresión) | CI | `scripts/smoke_stack.py`, `scripts/smoke_pages.py`, `scripts/tests/test_smoke_stack.py`, `scripts/tests/test_smoke_pages.py`, `scripts/tests/test_smoke_stack_wiring.py`, `scripts/tests/test_smoke_client_bundle.py` | — | backend-dev | M | Sí | 🟡 | PR abierto |
| T-IDA-27 | Proxy con sesión: Bearer, CSRF y refresh transparente | AC-IDA-18, AC-IDA-26 (UX), AC-IDA-28 | BFF | `src/lib/server/session-proxy.ts`, `src/lib/api-client.ts`, `context/07-frontend-ui-guidelines.md` | T-IDA-23 | frontend-dev | L | Sí | ☐ | |
| T-IDA-28 | Pantalla "Ingresar" y protección de rutas | AC-IDA-19 (UI) | UI | `src/proxy.ts`, `app/(auth)/login/page.tsx`, `src/modules/identity/components/{LoginCard,LoginErrorAlert}.tsx`, `src/modules/identity/lib/login-errors.ts`, `scripts/smoke_pages.py`, `scripts/tests/test_smoke_pages.py` | T-IDA-24, T-IDA-26, T-IDA-27 | frontend-dev | M | Sí | ☐ | |
| T-IDA-29 | Mi perfil, menú de usuario y "sin empresas" | AC-IDA-30 (UI) | UI | `src/modules/identity/components/{ProfileCard,UserMenu,NoOrganizationState}.tsx` | T-IDA-07, T-IDA-25, T-IDA-28 | frontend-dev | M | No | ☐ | |
| T-IDA-30 | Pantalla "Seguridad" | AC-IDA-33 (UI) | UI | `app/(dashboard)/configuracion/seguridad/page.tsx`, `src/modules/identity/components/SessionsTable.tsx` | T-IDA-17, T-IDA-29 | frontend-dev | L | No | ☐ | |
| T-IDA-31 | E2E de login con proveedor falso | AC-IDA-01, AC-IDA-17, AC-IDA-33 | E2E | `scripts/e2e_login.py`, `scripts/tests/test_e2e_login.py` | T-IDA-20, T-IDA-29, T-IDA-30 | backend-dev | M | Sí | ☐ | |

## Cobertura AC → tareas
| AC | Tareas |
|---|---|
| AC-IDA-01 | T-IDA-13, T-IDA-24, T-IDA-31 |
| AC-IDA-02 | T-IDA-12 (puerto en memoria), T-TEN-17 (puerto real) |
| AC-IDA-03 | T-IDA-12, T-IDA-13 |
| AC-IDA-04 | T-IDA-12, T-TEN-17 |
| AC-IDA-05 | T-IDA-12, T-TEN-17 |
| AC-IDA-06 | T-IDA-13 |
| AC-IDA-07 | T-IDA-08 |
| AC-IDA-08 | T-IDA-08 (`nonce`), T-IDA-13 (`state`, callback repetido) |
| AC-IDA-09 | T-IDA-11, T-IDA-13 (callback), T-IDA-14 (refresh) |
| AC-IDA-10 | T-IDA-04, T-IDA-06 |
| AC-IDA-11 | T-IDA-04, T-IDA-06 |
| AC-IDA-12 | T-IDA-04, T-IDA-06 |
| AC-IDA-13 | T-IDA-04 |
| AC-IDA-14 | T-IDA-03, T-IDA-14 |
| AC-IDA-15 | T-IDA-02, T-IDA-15 |
| AC-IDA-16 | T-IDA-02, T-IDA-03, T-IDA-14 |
| AC-IDA-17 | T-IDA-16, T-IDA-25, T-IDA-31 |
| AC-IDA-18 | T-IDA-22, T-IDA-24, T-IDA-27 |
| AC-IDA-19 | T-IDA-10, T-IDA-22, T-IDA-23, T-IDA-24, T-IDA-28 |
| AC-IDA-20 | T-IDA-09, T-IDA-10, T-IDA-13, T-IDA-15 |
| AC-IDA-21 | T-IDA-07, T-TEN-12 (selector real) |
| AC-IDA-22 | T-IDA-06, T-IDA-07, T-IDA-14 (refresh) |
| AC-IDA-23 | T-IDA-21 |
| AC-IDA-24 | T-IDA-05, T-IDA-13, T-IDA-21 |
| AC-IDA-25 | T-IDA-17 |
| AC-IDA-26 | T-IDA-06, T-IDA-17, T-IDA-27 |
| AC-IDA-27 | T-IDA-18 |
| AC-IDA-28 | T-IDA-02, T-IDA-15, T-IDA-23, T-IDA-27 |
| AC-IDA-29 | T-IDA-11 |
| AC-IDA-30 | T-IDA-07, T-IDA-11, T-IDA-29 |
| AC-IDA-31 | T-IDA-01, T-IDA-12, T-TEN-17 |
| AC-IDA-32 | T-IDA-18 (sin endpoints, admin), T-TEN-18 (comando de bootstrap) |
| AC-IDA-33 | T-IDA-17, T-IDA-30, T-IDA-31 |
| AC-IDA-34 | T-IDA-04, T-IDA-06 |
| AC-IDA-35 | T-IDA-16 |
| AC-IDA-36 | T-IDA-08 |
| AC-IDA-37 | T-IDA-09, T-IDA-10, T-IDA-22 |
| AC-IDA-38 | T-IDA-19 |

**RF → tareas:** RF-IDA-01 → T-IDA-10, T-IDA-24 · RF-IDA-02 → T-IDA-11, T-IDA-12, T-IDA-13, T-IDA-24 · RF-IDA-03 →
T-IDA-06 · RF-IDA-04 → T-IDA-14, T-IDA-15, T-IDA-23 · RF-IDA-05 → T-IDA-16, T-IDA-25 · RF-IDA-06 → T-IDA-07, T-TEN-12 ·
RF-IDA-07 → T-IDA-17, T-IDA-30 · RF-IDA-08 → T-IDA-18, T-TEN-18 · RF-IDA-09 → T-IDA-05, T-IDA-21 · RF-IDA-10 → T-IDA-19.

**RNF → tareas:** RNF-IDA-01 → T-IDA-04, T-IDA-08 · RNF-IDA-02 → T-IDA-06 · RNF-IDA-03 → T-IDA-21 · RNF-IDA-04 →
T-IDA-19, T-IDA-21 · RNF-IDA-05 → T-IDA-01, T-IDA-03 · RNF-IDA-06 → T-IDA-01, T-IDA-03, T-IDA-10, T-IDA-20 ·
RNF-IDA-07 → T-IDA-03, T-IDA-30.

**Spec §14 → tareas:** Ingresar → T-IDA-28 · sesión vencida → T-IDA-27 · sin empresas, Mi perfil, menú → T-IDA-29 ·
Seguridad → T-IDA-30.

**Huecos: ninguno.** Dos partes solo se verifican a mano (`design.md §9`, fila Manual): Google real en staging y dos
pestañas tras 15 min; van al `verification.md`, no a una tarea.

## Orden y paralelismo
| Ola | Tareas | Notas |
|---|---|---|
| 0 | T-IDA-00 → T-IDA-01 | Antes que cualquier tarea de SPEC-02 con FK a usuario |
| 1 | T-IDA-02 → T-IDA-03 · T-IDA-04 · T-IDA-05 · T-IDA-09 (paralelas) · T-IDA-26 | T-IDA-26 no depende de nada y puede entrar cuando quiera, pero antes de T-IDA-28 |
| 2 | T-IDA-06 → T-IDA-07 · T-IDA-08 | Con T-IDA-07 ya hay una API autenticada de punta a punta |
| 3 | T-IDA-10 · T-IDA-11 → T-IDA-12 → T-IDA-13 · T-IDA-20 | Con T-IDA-13 hay login completo por API, con el stub de invitaciones |
| 4 | T-IDA-14 → {T-IDA-15, T-IDA-16} · T-IDA-17 → T-IDA-18 · T-IDA-19 | |
| 5 | T-IDA-21 · T-IDA-22 → {T-IDA-23, T-IDA-24} → {T-IDA-25, T-IDA-27} | El frontend puede arrancar con los contratos de T-IDA-10, 13 y 14 mergeados |
| 6 | T-IDA-28 → T-IDA-29 → T-IDA-30 → T-IDA-31 | |

SPEC-02 corre en paralelo desde la ola 1 (ver su lista). **El cierre es conjunto** (Q-108): `verification.md` de los dos
módulos se aprueba en la misma pasada, después de `T-TEN-36`.

---

## Detalle por tarea

### T-IDA-00 — Guarda de `check_migrations_roundtrip` (deuda de 00)
- **AC:** AC-PLT-17 (regresión). C-17. **Zona roja:** sí.
- **Archivos:** `backend/apps/common/management/commands/check_migrations_roundtrip.py`,
  `backend/tests/migrations/test_AC_PLT_17_roundtrip_guard.py`, `backend/tests/migrations/conftest.py`,
  `backend/tests/migrations/test_AC_PLT_17_reversibility.py`.
- **Cambios:** `--allow-data-loss` no mira a qué BD apunta y la de CI se llama `hub`, igual que la de desarrollo: un
  chequeo por nombre obligaría a cambiar `ci.yml` (Q-063). Por eso se mira el contenido: antes del primer `migrate`,
  si cualquier tabla del `search_path` salvo `django_migrations` tiene filas (`EXISTS` real, no estadísticas), sale con 2
  nombrando BD y tabla, sin ningún valor. Son todas y no solo las de las apps pedidas: `migrate identity zero` también
  revierte lo que depende de `identity`. `hub_synthetic` se comparte y `test_AC_PLT_17_runpython_without_reverse_fails`
  deja una fila de `0004_seed_items`: los roundtrips de la suite tienen que partir de una BD vacía, o saldrían con 2.
  Imprime siempre a qué BD apunta (nombre y host, nunca la URL).
- **Fuera:** cambiar el job `migrations`; `AGENTS.md` sigue válido.
- **Pruebas:** `test_AC_PLT_17_refuses_database_with_rows`, `test_AC_PLT_17_empty_tables_pass`,
  `test_AC_PLT_17_refusal_shows_no_values`, `test_AC_PLT_17_labels_still_check_dependent_tables`, sobre la BD sintética de `tests/migrations/conftest.py`.

### T-IDA-01 — `User` + `AUTH_USER_MODEL` + migración 0001
- **AC:** AC-IDA-31 (normalización). RN-IDA-04, RNF-IDA-05, RNF-IDA-06. **Zona roja:** sí.
- **Archivos:** `backend/apps/identity/{__init__,apps}.py`, `models/{__init__,user}.py`, `domain/{__init__,emails,profile}.py`,
  `migrations/0001_users.py`, `backend/config/settings/base.py`, `backend/tests/identity/test_AC_IDA_31_normalization.py`,
  `test_user_constraints.py`, `backend/tests/migrations/test_AC_PLT_17_reversibility.py` (afirma "Round trip passed for
  0 app(s)": deja de ser cierto con la primera app migrada).
- **Cambios:** tabla `users` de `design.md §5`, con `CHECK` de email normalizado y `CHECK is_active = (deactivated_at IS
  NULL)`; `USERNAME_FIELD = "google_sub"`; manager sin `create_superuser`; contraseña inutilizable. **D-03 se mantiene:**
  sin ningún `django.contrib.*` instalado; `AbstractBaseUser` se importa de `base_user`. Si algo lo exigiera, es scope
  drift.
- **Fuera:** sesiones, autenticación, comandos.
- **Pruebas:** `test_AC_IDA_31_normalize_email_trims_and_lowers`, `test_AC_IDA_31_dots_and_alias_are_not_equivalent`,
  `test_RN_IDA_04_google_sub_is_unique`, `test_RNF_IDA_05_no_usable_password`; ida y vuelta por el job `migrations`.
- **DoD extra:** `makemigrations --check` limpio; `lint_migrations` en verde.

### T-IDA-02 — Reglas puras de sesión y formato de secretos
- **AC:** AC-IDA-15, AC-IDA-16, AC-IDA-28 (decisión). RN-IDA-10, RN-IDA-11. **Zona roja:** sí.
- **Archivos:** `apps/identity/domain/{session_policy,secrets_format,errors}.py`, `backend/tests/identity/domain/test_*`.
- **Cambios:** duraciones (15 min, 7 d, 30 d, gracia 30 s); `decide_refresh` → rotar / gracia / reuso; formato
  `rt1.<sid>.<secret>`, hash SHA-256, `state`, `nonce`, binding, PKCE; enum de códigos de error. Sin Django ni red.
- **Fuera:** modelos y servicios.
- **Pruebas:** `test_AC_IDA_16_idle_and_absolute_expiry`, `test_AC_IDA_16_absolute_never_extends`,
  `test_AC_IDA_28_within_grace_is_not_reuse`, `test_AC_IDA_15_outside_grace_is_reuse`.

### T-IDA-03 — `AuthSession`, `RefreshToken` + migración 0002
- **AC:** AC-IDA-14 (solo hash), AC-IDA-16 (constraints). RNF-IDA-05, 06, 07. **Zona roja:** sí.
- **Archivos:** `models/{auth_session,refresh_token}.py`, `migrations/0002_sessions_refresh_tokens.py`,
  `services/session_lifecycle.py`, `backend/tests/architecture/allowlists.py`, `backend/tests/identity/test_session_*.py`.
- **Cambios:** tablas de `design.md §5` con todos sus `CHECK` e índices parciales; `open_session`, `revoke`, `expire` con
  `UPDATE … WHERE status='active'`. Sin columna de IP ni User-Agent crudo.
- **Fuera:** emisión de tokens, vistas.
- **Pruebas:** `test_AC_IDA_16_absolute_expiry_constraint`, `test_AC_IDA_14_only_hash_is_stored`,
  `test_RN_IDA_10_one_live_token_per_session`, `test_session_terminal_never_returns_to_active`.

### T-IDA-04 — JWT del Hub: claves, emisión y verificación
- **AC:** AC-IDA-10, 11, 12, 13, 34 (nivel token). RN-IDA-08, RN-IDA-09, RNF-IDA-01. **Zona roja:** sí (dependencia nueva:
  ADR-0004, `C-13`).
- **Archivos:** `apps/identity/tokens/{keys,access_token}.py`, `backend/pyproject.toml` y `uv.lock` (`PyJWT[crypto]`
  2.15.1), `config/settings/env.py`, `config/settings/{base,dev,test,prod}.py`, `env.example`,
  `backend/tests/identity/tokens/test_*`.
- **Cambios:** ES256 con allowlist fija, `typ=at+jwt`, `kid`, leeway 60 s, claims exactos de `design.md §8.2`; variables
  `IDENTITY_JWT_*`.
- **Fuera:** la clase de autenticación de DRF.
- **Pruebas:** por AC, sin BD: `test_AC_IDA_10_expired_over_60s`, `test_AC_IDA_10_issued_14_min_ago_is_valid`,
  `test_AC_IDA_11_alg_none_and_hs256_rejected`, `test_AC_IDA_12_foreign_iss_aud`, `test_AC_IDA_13_exact_claims`,
  `test_AC_IDA_34_skew_30s_accepted_120s_rejected`.
- **DoD extra:** `pip-audit` en verde con la dependencia nueva.

### T-IDA-05 — Puertos, stubs, registro y catálogo de auditoría
- **AC:** AC-IDA-24 (catálogo). RF-IDA-09, RN-IDA-17. **Zona roja:** sí.
- **Archivos:** `apps/identity/ports/{invitations,memberships,audit,stubs,registry}.py`, `domain/audit_events.py`,
  `config/settings/base.py`, `backend/tests/architecture/test_identity_boundaries.py`, `backend/tests/identity/test_ports.py`.
- **Cambios:** firmas exactas de `design.md §6.4`; `NullInvitationPort`, `EmptyMembershipSelector`, `LogAuditPort`;
  `IDENTITY_*_PORT` son dotted paths fijos en settings, sin variable de entorno.
- **Fuera:** implementaciones reales (SPEC-02, SPEC-10). `AuditPort` y `apps/common/audit` de SPEC-02 son dos entradas
  al mismo canal `audit`; unificarlas queda para SPEC-10, que aporta el sink real.
- **Pruebas:** `test_AC_IDA_24_catalog_matches_spec`, `test_identity_does_not_import_tenancy_or_audit`,
  `test_domain_has_no_django_imports`, `test_null_port_finds_nothing`.

### T-IDA-06 — `HubJWTAuthentication` y deny-by-default
- **AC:** AC-IDA-10, 11, 12, 22, 26 (`401 session_revoked`), 34 (nivel API). RF-IDA-03, RN-IDA-19, RN-IDA-20, RNF-IDA-02.
  **Zona roja:** sí.
- **Archivos:** `apps/identity/api/authentication.py`, `selectors/auth_sessions.py`, `config/settings/base.py`,
  `backend/tests/identity/api/test_authentication.py`, tests de 00 que dependan de `AllowAny`.
- **Cambios:** una consulta por PK con `JOIN users`, sin caché ni escrituras; `401` con `WWW-Authenticate: Bearer
  realm="hub"`; `DEFAULT_AUTHENTICATION_CLASSES` y `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`, como anuncia
  `base.py`. Las rutas públicas de 00 (`/healthz`, `/readyz`, esquema en dev) quedan explícitamente abiertas.
- **Fuera:** `/api/me`, refresh.
- **Pruebas:** `test_AC_IDA_22_api_key_is_not_a_session`, `test_AC_IDA_26_revoked_session_next_request_401`,
  `test_AC_IDA_10_expired_via_api`, `test_AC_IDA_11_bad_signature_via_api`, `test_AC_IDA_12_google_token_is_401`,
  `test_AC_IDA_34_skew_via_api`, `test_RN_IDA_20_one_query_no_cache`, `test_no_session_authentication_in_settings`.
- **DoD extra:** una ruta nueva sin permiso explícito responde `401`.

### T-IDA-07 — `GET /api/me`
- **AC:** AC-IDA-21, AC-IDA-22, AC-IDA-30 (API). RF-IDA-06, RN-IDA-18, RN-IDA-22. **Zona roja:** sí.
- **Archivos:** `api/{views_me,urls,serializers}.py`, `config/urls.py`, `specs/_contracts/openapi.yaml`,
  `frontend/src/types/api.d.ts`, `backend/tests/identity/api/test_AC_IDA_21_me.py`.
- **Cambios:** primera rebanada autenticada completa, con `memberships: []` del stub.
- **Fuera:** selector real (`T-TEN-12`).
- **Pruebas:** `test_AC_IDA_21_returns_only_own_data`, `test_AC_IDA_21_anonymous_is_401_unauthenticated`,
  `test_AC_IDA_22_api_key_on_me`, `test_AC_IDA_30_no_memberships_returns_empty_list`.

### T-IDA-08 — Gateway de Google + validación del ID token
- **AC:** AC-IDA-07, AC-IDA-08 (`nonce`), AC-IDA-36. RN-IDA-02, RN-IDA-03, RNF-IDA-01. **Zona roja:** sí (dependencia
  nueva `httpx` 0.28.1).
- **Archivos:** `oidc/{google_gateway,id_token}.py`, `backend/tests/fakes/google.py`, `backend/pyproject.toml`, `uv.lock`,
  `config/settings/env.py`, `env.example`, `backend/tests/identity/oidc/test_*`.
- **Cambios:** `build_authorization_url`, `exchange_code` con timeouts de `design.md §8.2` y sin reintentos;
  `verify_id_token` con `PyJWKClient`; refresco una vez ante `kid` desconocido con *cooldown*; mapeo a
  `unavailable`/`rejected`. Variables `IDENTITY_GOOGLE_*`, `IDENTITY_OIDC_PROVIDER`.
- **Fuera:** decisiones de acceso (`T-IDA-11`), `dev_oidc` (`T-IDA-20`).
- **Pruebas:** `test_AC_IDA_07_{bad_signature,foreign_aud,foreign_iss,expired}`, `test_AC_IDA_08_nonce_mismatch`,
  `test_AC_IDA_36_{timeout,5xx,429,jwks_down}_is_unavailable`, `test_RNF_IDA_01_unknown_kid_refreshes_once`.

### T-IDA-09 — Credencial BFF, IP del cliente y throttles
- **AC:** AC-IDA-20, AC-IDA-37. RN-IDA-15. **Zona roja:** sí.
- **Archivos:** `api/{bff_auth,client_ip,throttles}.py`, `config/settings/{env,base}.py`, `env.example`,
  `apps/common/feature_flags.py`, `backend/tests/identity/api/test_throttles.py`,
  `backend/tests/config/test_RF_PLT_19_feature_flags.py` (dos aserciones suponían `REGISTRY` vacío; la flag lo llena).
- **Cambios:** `IsBffCaller` con comparación en tiempo constante, `404` sin credencial, lista vigente/anterior; IP desde
  `X-Hub-Client-IP` solo con credencial válida; scopes de `design.md §7.6`; flag `IDENTITY_GOOGLE_LOGIN` en `REGISTRY`.
- **Vistas:** `BffAPIView` (en `bff_auth.py`) responde sin credencial lo mismo que una ruta inexistente (bytes, sin `Allow`),
  no autentica por `Authorization` y convierte el exceso en `429 rate_limited` (`design.md §6.1`, §6.3).
- **Redis caído:** los tres throttles heredan el fail-open de D-06; aceptado por el reviewer (#78). Conviene alertar sobre
  `throttle.cache_unavailable`.
- **Fuera:** las vistas que los usan (`T-IDA-10`, `13`, `14`).
- **Pruebas:** `test_AC_IDA_20_key_is_per_ip_and_scope`, `test_AC_IDA_37_ten_client_ips_share_no_quota`,
  `test_client_ip_header_ignored_without_credential`, `test_bff_endpoint_without_credential_is_404`.

### T-IDA-10 — Iniciar login: `LoginAttempt` + migración 0003
- **AC:** AC-IDA-19 (servidor), AC-IDA-20, AC-IDA-37. RF-IDA-01, RN-IDA-13, RNF-IDA-06. **Zona roja:** sí.
- **Archivos:** `models/login_attempt.py`, `migrations/0003_login_attempts.py`, `domain/return_path.py`,
  `services/login_start.py`, `api/views_bff.py`, `api/urls.py`, `infra/docker-compose.yml`,
  `apps/common/logging/report_filter.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `POST /api/auth/bff/login/start`; solo hashes salvo `code_verifier`; `503 login_disabled` con el flag
  apagado.
- **Compose:** `infra/docker-compose.yml` pasa `IDENTITY_BFF_CREDENTIALS` y `FEATURE_*`, para que `auth/bff/*` funcione en dev antes de `T-IDA-27`.
- **Reportes de error:** adelantado desde `T-IDA-21`: `report_filter.py` oculta `HTTP_X_HUB_BFF_CREDENTIAL`, que empieza a circular acá.
- **Vistas:** extienden `BffAPIView` (`T-IDA-09`: ya trae `authentication_classes = ()`, el `404` idéntico y
  `rate_limited`) y declaran `throttle_classes` explícitos.
- **Fuera:** callback.
- **Pruebas:** `test_AC_IDA_19_hostile_return_path_goes_home` (absoluto, esquema, `//host`, otro dominio),
  `test_AC_IDA_20_eleventh_start_is_429_without_google`, `test_AC_IDA_37_ten_ips_via_bff_no_429`,
  `test_RNF_IDA_06_flag_off_is_503`.

### T-IDA-11 — Reglas del callback y usuario existente
- **AC:** AC-IDA-09 (callback), AC-IDA-29, AC-IDA-30. RF-IDA-02, RN-IDA-03, 05 caso (a), 07, 21, 22. **Zona roja:** sí.
- **Archivos:** `domain/login_rules.py`, `selectors/users.py`, `services/user_provisioning.py` (caso a), tests.
- **Cambios:** `evaluate_identity` (`email_verified` ∈ `True`/`"true"`); `_sync_existing_user`: email libre actualiza y
  audita, colisión no cambia y audita, nombre y avatar se sincronizan; `sub` nuevo con email ajeno → `identity_conflict`
  con alerta. **Q-121:** el caso (a) no llama al puerto de invitaciones.
- **Fuera:** caso (b).
- **Pruebas:** `test_AC_IDA_29_email_change_free`, `test_AC_IDA_29_new_sub_with_taken_email_is_conflict`,
  `test_AC_IDA_29_collision_keeps_old_email`, `test_AC_IDA_09_inactive_user_rejected`,
  `test_AC_IDA_30_no_memberships_still_logs_in`, `test_Q_121_case_a_never_touches_invitations`.
- **Notas del reviewer de #65:** los `CHECK` de `users` dejan pasar tabuladores, NBSP, U+3000 y `""`: antes de esta tarea se decide si el callback valida el email con la normalización de Python o si se endurece el `CHECK`. El texto de `IntegrityError` trae email y `sub`: esta tarea y `T-IDA-12` no usan `logger.exception` ni `str(exc)` con ese error. Un NUL en nombre o avatar lanza `DataError`, aunque el docstring de `domain/profile.py` dice que un dato inutilizable nunca rechaza un login. `AC-IDA-31` queda ⚠ en el `verification.md` de 01, cuando exista, hasta `T-IDA-12` y `T-TEN-17`.

### T-IDA-12 — Usuario nuevo por invitación y carrera de callbacks
- **AC:** AC-IDA-02, 03, 04, 05, 31. RN-IDA-05 caso (b), RN-IDA-06. **Zona roja:** sí.
- **Archivos:** `services/user_provisioning.py`, `backend/tests/identity/fakes.py` (puerto en memoria),
  `backend/tests/identity/test_AC_IDA_02_invited_user.py`, `test_AC_IDA_05_rollback.py`.
- **Cambios:** una `atomic()`: insertar usuario → `find_valid_invitations` → `accept_invitations`; `IntegrityError` →
  rollback del savepoint y un reintento (`design.md §4.3`).
- **Fuera:** puerto real (`T-TEN-17`), que repite 02, 04, 05 y 31.
- **Pruebas:** `test_AC_IDA_02_concurrent_callbacks_one_user` (dos hilos, `transaction=True`),
  `test_AC_IDA_03_no_invitation_creates_nothing`, `test_AC_IDA_04_expired_or_revoked_is_not_invited`,
  `test_AC_IDA_05_accept_failure_rolls_back_all`, `test_AC_IDA_31_alias_is_not_invited`.
- **División (`C-14`):** el test de carrera va en archivo propio; `user_provisioning.py` queda ≤ 250 líneas.

### T-IDA-13 — Completar login: orquestación y vista
- **AC:** AC-IDA-01, 03, 06, 08, 09, 20, 24 (login). RF-IDA-02, RN-IDA-17. **Zona roja:** sí.
- **Archivos:** `services/login_complete.py`, `api/views_bff.py`, `api/serializers.py`, `openapi.yaml`, `api.d.ts`,
  `backend/tests/identity/api/test_login_complete.py`.
- **Cambios:** tabla de `design.md §4.2` en orden fijo; `DELETE … RETURNING` del intento. Éxito audita dentro de la
  transacción; rechazo después del rollback, solo con el motivo (**Q-125:** sin email ni `sub`).
- **Vistas:** extienden `BffAPIView` (`T-IDA-09`: ya trae `authentication_classes = ()`, el `404` idéntico y
  `rate_limited`) y declaran `throttle_classes` explícitos.
- **Fuera:** cookies.
- **Pruebas:** `test_AC_IDA_01_active_user_gets_session`, `test_AC_IDA_03_rejected_is_audited`,
  `test_AC_IDA_06_unverified_email`, `test_AC_IDA_08_bad_state_never_calls_google`, `test_AC_IDA_08_repeated_callback`,
  `test_AC_IDA_09_inactive_gets_no_tokens`, `test_AC_IDA_20_eleventh_callback_is_429`,
  `test_AC_IDA_24_login_events_have_null_org`, `test_Q_125_rejection_has_no_email_nor_sub`.

### T-IDA-14 — Refresh: rotación y vencimientos
- **AC:** AC-IDA-09 (refresh), AC-IDA-14, AC-IDA-16. RF-IDA-04, RN-IDA-11. **Zona roja:** sí.
- **Archivos:** `services/refresh.py`, `api/views_bff.py`, `api/serializers.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** `POST /api/auth/bff/refresh`, camino de rotación de `design.md §4.5` con `FOR UPDATE`; el vencimiento
  materializa `expired`.
- **Vistas:** extienden `BffAPIView` (`T-IDA-09`: ya trae `authentication_classes = ()`, el `404` idéntico y
  `rate_limited`) y declaran `throttle_classes` explícitos.
- **`sid`:** unificar el parseo local de `api/throttles.py` con `domain/secrets_format.py`.
- **Tope por IP:** el refresh limita solo por `sid`; un `sid` aleatorio con formato válido estrena cupo y no hay tope por IP.
  Decidirlo acá (planner).
- **Fuera:** gracia y reuso (`T-IDA-15`).
- **Pruebas:** `test_AC_IDA_14_rotation_new_pair`, `test_AC_IDA_16_idle_expired_refresh`,
  `test_AC_IDA_16_absolute_expired_refresh`, `test_AC_IDA_16_refresh_never_moves_absolute`,
  `test_AC_IDA_09_inactive_user_refresh`, `test_AC_IDA_22_api_key_on_refresh`.

### T-IDA-15 — Refresh: gracia, reuso y concurrencia
- **AC:** AC-IDA-15, AC-IDA-20 (refresh), AC-IDA-28. RN-IDA-10. **Zona roja:** sí.
- **Archivos:** `services/refresh.py`, `api/views_bff.py`, `backend/tests/identity/test_refresh_concurrency.py`.
- **Cambios:** gracia → solo access, `refresh=null`, sin auditar; reuso → revoca, audita `refresh_reuse_detected` con
  alerta y confirma; throttle 30/min por `sid`.
- **Fuera:** coalescencia del BFF (`T-IDA-23`).
- **Pruebas:** `test_AC_IDA_15_reuse_revokes_session`, `test_AC_IDA_28_two_concurrent_refreshes` (hilos),
  `test_AC_IDA_20_31st_refresh_is_429`.
- **División (`C-14`):** si `refresh.py` pasa de 250 líneas, la decisión queda en `session_policy.py` y el servicio solo
  orquesta.

### T-IDA-16 — Logout
- **AC:** AC-IDA-17 (backend), AC-IDA-35. RF-IDA-05, RN-IDA-14. **Zona roja:** sí.
- **Archivos:** `services/logout.py`, `api/views_bff.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** busca por hash del refresh (vigente o usado) o por `sid` de un JWT con firma válida aunque vencido;
  `204` siempre; `reason=superseded` para el login sobre sesión previa.
- **Pruebas:** `test_AC_IDA_17_logout_revokes_and_audits`, `test_AC_IDA_17_second_logout_no_effects`,
  `test_AC_IDA_35_expired_jwt_still_revokes`.

### T-IDA-17 — Sesiones propias: listar y revocar
- **AC:** AC-IDA-25, AC-IDA-26, AC-IDA-33 (API). RF-IDA-07, RN-IDA-24. **Zona roja:** sí.
- **Archivos:** `services/sessions.py`, `selectors/auth_sessions.py`, `api/views_sessions.py`, `domain/client_hint.py`,
  `api/urls.py`, `openapi.yaml`, `api.d.ts`, tests.
- **Cambios:** tres rutas de `design.md §6.2`; `get_own_session` → `404` si es ajena; `client_hint` puro de ~60 líneas;
  `open_session` guarda navegador y SO.
- **Pruebas:** `test_AC_IDA_25_foreign_session_is_404`, `test_AC_IDA_26_revoked_from_security_next_request`,
  `test_AC_IDA_33_revoke_others_keeps_current`, `test_AC_IDA_33_list_has_no_ip`.

### T-IDA-18 — Comandos de desactivar y reactivar usuario
- **AC:** AC-IDA-27, AC-IDA-32 (parte 01). RF-IDA-08, RN-IDA-07, RN-IDA-23. **Zona roja:** sí.
- **Archivos:** `services/user_status.py`, `management/commands/{deactivate_user,reactivate_user}.py`,
  `backend/tests/identity/test_AC_IDA_27_deactivate.py`, `backend/tests/identity/test_AC_IDA_32_no_endpoints.py`.
- **Cambios:** `design.md §6.5`; actor `platform_operator` con `--operator` y usuario del SO.
- **Fuera:** comando de bootstrap (`T-TEN-18`). No hay admin que apagar: D-03 sigue en pie y Q-228 decidió que no hay admin en el MVP.
- **Pruebas:** `test_AC_IDA_27_two_sessions_revoked_and_next_request_401`,
  `test_AC_IDA_27_reactivate_does_not_revive`, `test_AC_IDA_32_schema_has_no_provisioning_endpoints`,
  `test_AC_IDA_32_admin_does_not_answer`.

### T-IDA-19 — Purga periódica
- **AC:** AC-IDA-38. RF-IDA-10, RN-IDA-25, RNF-IDA-04. **Zona roja:** sí.
- **Archivos:** `tasks.py`, `beat.py`, `services/purge.py`, `config/celery.py`, tests.
- **Cambios:** `design.md §3.3`: materializa `expired`, borra intentos vencidos y sesiones terminales de más de 90 días en
  lotes de 1000; gauge `auth.sessions_active`.
- **Pruebas:** `test_AC_IDA_38_91_days_purged_89_kept`, `test_AC_IDA_38_user_is_never_deleted`, `test_purge_is_idempotent`.

### T-IDA-20 — Chequeos de arranque y proveedor OIDC falso
- **AC:** — (RN-IDA-01, RN-IDA-16, RNF-IDA-06, Q-122). **Zona roja:** sí.
- **Archivos:** `checks.py`, `apps.py`, `dev_oidc/{views,urls}.py`, `config/settings/{base,dev,test,prod}.py`,
  `config/urls_dev.py`, `backend/tests/identity/test_RNF_IDA_06_*.py`.
- **Cambios:** ver "Ajustes al diseño" por `APP_ENV`; `IdentityConfig.ready()` lanza `ImproperlyConfigured` si
  `IDENTITY_OIDC_PROVIDER=fake` sin `IDENTITY_FAKE_OIDC_ALLOWED`; `checks.py` exige secretos distintos y, en prod, issuer y
  endpoints exactos de Google. `/dev-oidc/*` no se monta en prod.
- **Credencial BFF:** evaluar una longitud mínima de `IDENTITY_BFF_CREDENTIALS` en prod (hoy no se exige), y que prod
  rechace el placeholder público de `env.example`.
- **Pruebas:** `test_RNF_IDA_06_fake_provider_fails_in_prod_settings`, `test_RN_IDA_16_equal_secrets_fail_check`,
  `test_RN_IDA_01_dev_oidc_routes_absent_in_prod`.

### T-IDA-21 — Redacción de logs, métricas y catálogo completo
- **AC:** AC-IDA-23, AC-IDA-24. RF-IDA-09, RNF-IDA-03, RNF-IDA-04. **Zona roja:** sí.
- **Archivos:** `apps/common/domain/redaction.py`, servicios que falten eventos, `backend/tests/identity/test_AC_IDA_23_*.py`,
  `test_AC_IDA_24_events.py`.
- **Cambios:** claves de `design.md §7.5`; eventos `auth.*` con `outcome`/`reason` y `alert=true`.
- **Reportes de error:** el ocultamiento de `HTTP_X_HUB_BFF_CREDENTIAL` en `report_filter.py` se adelantó a `T-IDA-10`.
- **Pruebas:** `test_AC_IDA_23_no_secret_in_logs_or_errors` (login, refresh, logout, rechazo),
  `test_AC_IDA_24_every_event_is_emitted`, `test_AC_IDA_24_429_is_not_audited`.
- **Aviso de `T-IDA-05`:** el logger `audit` hereda el nivel del root, así que con `LOG_LEVEL=WARNING` se pierden los eventos `info`: darle nivel propio en `apps/common/logging/setup.py` (sumarlo a los archivos). Una clave de `metadata` con `session` o `token` sale `[REDACTED]` en ese canal.

### T-IDA-22 — BFF: cookies, IP, retorno y cliente a Django
- **AC:** AC-IDA-18, AC-IDA-19, AC-IDA-37 (BFF). RN-IDA-12, RN-IDA-13. **Zona roja:** sí.
- **Archivos:** `frontend/src/lib/server/{cookies,client-ip,return-path,django,problem}.ts` y sus tests, `env.ts`,
  `env.example`, `backend/tests/config/test_AC_PLT_05_env_example_parity.py`, `.github/zona-roja-paths.txt`.
- **Cambios:** cookies de `design.md §7.1`; agrega `frontend/src/app/api/**`, `frontend/src/lib/server/**` y
  `frontend/src/proxy.ts` a la zona roja, como anuncia ese archivo. Variables `HUB_BFF_CREDENTIAL`, `HUB_APP_ORIGIN`, `HUB_TRUSTED_PROXY_HOPS`.
- **`django.ts`:** envía `X-Forwarded-Proto: https` (Q-065); sin eso, `SECURE_SSL_REDIRECT` responde 301 en prod.
- **Fuera:** rutas.
- **Pruebas:** `test_AC_IDA_18` en `cookies.test.ts` (atributos y prefijo `__Host-`), `test_AC_IDA_19` en
  `return-path.test.ts`, `test_AC_IDA_37` en `client-ip.test.ts`.

### T-IDA-23 — BFF: CSRF y refresh con coalescencia
- **AC:** AC-IDA-19 (CSRF), AC-IDA-28 (BFF). RN-IDA-10, RN-IDA-13. **Zona roja:** sí.
- **Archivos:** `src/lib/server/{csrf,refresh}.ts` y sus tests.
- **Cambios:** `design.md §7.2` y `§4.5`: `refresh=null` no pisa `rt`.
- **Pruebas:** `test_AC_IDA_19` sin `Origin`, con `Origin` ajeno y con token distinto; `test_AC_IDA_28` con coalescencia y
  con `refresh=null`.

### T-IDA-24 — Route Handlers de inicio y callback
- **AC:** AC-IDA-01 (cookies), AC-IDA-18, AC-IDA-19. RF-IDA-01, RF-IDA-02. **Zona roja:** sí.
- **Archivos:** `src/app/api/auth/google/{start,callback}/route.ts` y sus tests.
- **Cambios:** `design.md §6.3`: binding reusado, `no-store`, `Referrer-Policy: no-referrer`, allowlist de `error`,
  `logout(reason=superseded)` *best effort*.
- **Pruebas:** `test_AC_IDA_18` (ningún token en el cuerpo), `test_AC_IDA_19` (`return_to` hostil), `test_AC_IDA_01` (cookies
  seteadas y redirección interna).

### T-IDA-25 — Route Handlers de logout y organización activa
- **AC:** AC-IDA-17 (cookies). RF-IDA-05, Q-119. **Zona roja:** sí.
- **Archivos:** `src/app/api/auth/logout/route.ts`, `src/app/api/session/active-organization/route.ts` y sus tests.
- **Pruebas:** `test_AC_IDA_17` (borra `at`, `rt`, `csrf`, `org`; sin sesión responde `204`), `test_Q_119_cookie_is_format_only`.

### T-IDA-26 — Smoke: 3xx y URL de ejemplo (deuda de 00)
- **AC:** AC-PLT-29 (regresión). **Zona roja:** sí (`scripts/**`).
- **Archivos:** `scripts/smoke_stack.py`, `scripts/smoke_pages.py` (nuevo), `scripts/tests/test_smoke_stack.py`,
  `scripts/tests/test_smoke_pages.py`, `scripts/tests/test_smoke_stack_wiring.py`, `scripts/tests/test_smoke_client_bundle.py`.
  Los dos últimos se sumaron al implementar: la división de `C-14` mueve `page_paths` y `check_client_bundle`, y esos
  tests los fijan (allowlist de imports y parches sobre `smoke_stack`).
- **División (`C-14`), obligatoria:** `smoke_stack.py` tiene 371 líneas; `page_paths`, `check_client_bundle` y lo nuevo se
  mueven a `smoke_pages.py` para que ninguno pase de ~400.
- **Cambios:** `200 <= status < 400` contaba un 3xx como página revisada, y con `T-IDA-28` todas las
  páginas protegidas responden 302. El smoke separa `revisadas` (2xx) de `redirigidas`: una redirección esperada (lista
  explícita: `/` y las protegidas → `/login`) se sigue una vez dentro del mismo origen y se revisa el destino; una no
  listada falla; una protegida que responde 200 sin sesión también falla. `0` revisadas falla. Agrega `SAMPLE_URLS` para
  rutas con `[id]`; una ruta parametrizada sin muestra sigue fallando.
- **Pruebas:** `test_AC_PLT_29_redirect_is_not_counted_as_reviewed`, `test_AC_PLT_29_protected_page_answering_200_fails`,
  `test_AC_PLT_29_parametrized_route_uses_sample`, `test_AC_PLT_29_unknown_redirect_fails`.
- **DoD extra:** debe mergearse **antes** de `T-IDA-28`.

### T-IDA-27 — Proxy con sesión: Bearer, CSRF y refresh transparente
- **AC:** AC-IDA-18, AC-IDA-26 (UX), AC-IDA-28. Spec §14 (sesión vencida). **Zona roja:** sí.
- **Archivos:** `src/lib/server/session-proxy.ts` (nuevo) y su test, `backend-proxy.ts`, `src/lib/api-client.ts`,
  `context/07-frontend-ui-guidelines.md`, `frontend/README.md`.
- **División (`C-14`), obligatoria:** `backend-proxy.ts` tiene 277 líneas; solo gana `x-organization-id` en la allowlist y un
  punto de enganche. La sesión, el reintento y la denylist van en `session-proxy.ts`.
- **Cambios:** `design.md §4.4` y `§6.3`; `404` para `auth/bff/**` y `auth/google/**`; `api-client` manda `X-CSRF-Token` y
  ante `401` va a `/login?error=session_expired`. Aplica `design.md §13` a `07 §3.2`.
- **Compose:** `infra/docker-compose.yml` ya pasa `IDENTITY_BFF_CREDENTIALS` y `FEATURE_*` desde `T-IDA-10`; acá no se toca.
- **Pruebas:** `test_AC_IDA_28` (reintento único tras `token_expired`), `test_AC_IDA_26` (`session_revoked` no reintenta y
  borra cookies), `test_AC_IDA_18` (denylist), cookies y `authorization` del navegador nunca se reenvían.

### T-IDA-28 — Pantalla "Ingresar" y protección de rutas
- **AC:** AC-IDA-19 (UI). Spec §14. **Zona roja:** sí (`src/proxy.ts` decide acceso).
- **Archivos:** `src/proxy.ts`, `src/app/(auth)/login/page.tsx`, `src/modules/identity/components/{LoginCard,LoginErrorAlert}.tsx`,
  `src/modules/identity/lib/login-errors.ts` y sus tests, `scripts/smoke_pages.py` y `scripts/tests/test_smoke_pages.py`.
- **Cambios:** `design.md §3.4`. Primera ruta protegida: por eso depende de `T-IDA-26`. Agrega las páginas protegidas a
  `EXPECTED_REDIRECTS` de `smoke_pages.py`, con `/login` como destino. El smoke sigue un solo salto y compara el origen:
  `/` tiene que ir directo a `/login` o quedar listada con su destino real, y un `Location` absoluto con otro host falla.
- **Pruebas:** `test_AC_IDA_19` en `login-errors.test.ts` (código desconocido → genérico), un caso por estado de §14.

### T-IDA-29 — Mi perfil, menú de usuario y "sin empresas"
- **AC:** AC-IDA-30 (UI). Spec §14. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `src/app/(dashboard)/configuracion/perfil/page.tsx`, `src/modules/identity/components/{ProfileCard,UserMenu,NoOrganizationState}.tsx`,
  `src/modules/identity/hooks/{useMe,useLogout}.ts`, `src/components/shell/TopBar.tsx`, `src/modules/settings/settings-sections.ts`.
- **Cambios:** reemplaza `UserMenuPlaceholder`. `NoOrganizationState` es el componente que después reutiliza `T-TEN-30`.
- **Pruebas:** `test_AC_IDA_30` (`memberships` vacías muestra el estado), estados de carga y error de `07 §2`.

### T-IDA-30 — Pantalla "Seguridad"
- **AC:** AC-IDA-33 (UI). RF-IDA-07, RNF-IDA-07. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `src/app/(dashboard)/configuracion/seguridad/page.tsx`, `src/modules/identity/components/{SessionsTable,RevokeSessionDialog,RevokeOthersDialog}.tsx`,
  `src/modules/identity/hooks/{useSessions,useRevokeSession,useRevokeOtherSessions}.ts`, `lib/format-dates.ts`.
- **Pruebas:** `test_AC_IDA_33` (acción deshabilitada sin otras sesiones; la actual usa logout del BFF), fechas en
  `America/Argentina/Buenos_Aires`.

### T-IDA-31 — E2E de login con proveedor falso
- **AC:** AC-IDA-01, AC-IDA-17, AC-IDA-33. **Zona roja:** sí (`scripts/**`).
- **Archivos:** `scripts/e2e_login.py`, `scripts/tests/test_e2e_login.py`, `infra/README.md`.
- **Cambios:** contra el Compose de desarrollo con `IDENTITY_OIDC_PROVIDER=fake`: ingresar → `/api/me` → sesiones →
  cerrar las demás → logout, con jar de cookies propio. Sin navegador ni dependencias nuevas. Corre a mano y lo usa
  `verification.md`; sumarlo a CI tocaría `ci.yml` (Q-063) y queda para el dueño.
- **Pruebas:** `test_AC_IDA_01_e2e_flow_parses_redirects`, `test_AC_IDA_17_e2e_logout_step`, `test_AC_IDA_33_e2e_revoke_others`
  con respuestas simuladas; la corrida real se registra en `verification.md`.

---
**Hecho:** 32 tareas, 38 AC y 10 RF cubiertos, olas y división de archivos.
**Pendiente / dudas:** ninguna de 01.
**Siguiente rol sugerido:** `backend-dev` en la ola 1 (`T-IDA-02`, `04`, `05`, `09`) y `T-IDA-26`; después `reviewer`.
