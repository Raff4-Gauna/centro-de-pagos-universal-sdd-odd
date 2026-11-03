---
spec: SPEC-00
actualizado: 2026-10-31
---
# Tareas — Módulo de Plataforma (fundaciones)

Reglas: rebanada vertical · ≤ ~300 líneas de diff · mergeable sola · cita AC · lista archivos esperados · incluye su plan de pruebas.

> Entradas: `spec.sdd.md` **Approved 1.0.0**, `design.md` (versiones de §8 con Q-059: Celery 5.6.3 / kombu 5.6.2 /
> redis 6.4.0, MUI 9.5.0), `clarifications.md` (incluida "Aprobación"), `context/08-control-de-versiones-ci-cd.md`.
> `design.md` no trae un orden de tareas propio: el orden de abajo sale de §3, §3.5 (cadena del pipeline) y §9.

## Convenciones de esta lista
- **Tamaño** (líneas de diff, **sin** lockfiles `uv.lock`/`pnpm-lock.yaml` ni archivos generados
  `specs/_contracts/openapi.yaml`/`frontend/src/types/api.d.ts`): **S** ≤ 100 · **M** ≤ 200 · **L** ≤ 300.
- **Zona roja = reviewer obligatorio** (label `zona-roja` + veredicto que cita el SHA). Criterio: Q-051 (contrato
  OpenAPI/errores, migraciones y su chequeo, tests de arquitectura) + Q-058 (todo lo que toca `.github/**`,
  `scripts/**`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `ruff.toml`, `backend/pyproject.toml`,
  `frontend/{tsconfig.json,eslint.config.mjs,vitest.config.mts}`) + credenciales (T-PLT-39). Donde dice "No (reviewer
  recomendado)" la tarea no cae en la lista pero toca seguridad (logs, BFF): conviene revisión igual.
- **Ningún archivo de código pasa de ~250 líneas** según el diseño (§3.1); ninguna tarea necesita división extra por
  `C-14`. Si un archivo de tests se acerca a 400 líneas, se parte **por AC** (ya previsto en T-PLT-06/07).
- **El CI crece por tarea.** `ci.yml` nace en T-PLT-03 con los jobs que ya tienen algo que correr; cada tarea que
  agrega un paso inserta su job **en su lugar de la cadena** de `design.md §3.5` (`lint → file-size → secrets +
  deps-audit → typecheck → architecture → tests → coverage → migrations → build`) y mueve el `needs` del job
  siguiente. Nunca se agrega un job "vacío" que pase en verde sin chequear nada. `test_AC_PLT_20_pipeline_chain.py`
  (T-PLT-03) valida en cada PR que los jobs presentes respetan ese orden; T-PLT-40 exige los 11. Los `needs:` que
  nombra cada detalle suponen que el job anterior de la cadena ya existe; si esa tarea todavía no entró, el job se
  engancha al **anterior presente** y la tarea que llega después corrige el enganche.

## Ramas, PR y merge
- **Prerrequisito:** la rama `spec/00-platform` (spec *Approved*, `design.md`, ADR-0005 y este `tasks.md`) se mergea a
  `main` **antes** de abrir `task/T-PLT-01-…`: las tareas salen de `main` y tienen que ver la spec aprobada.
- Cada tarea en `task/T-PLT-NN-slug` desde `main` actualizado; un PR por tarea; merge **squash** (`gh pr merge --squash
  --match-head-commit <sha>`). El PR actualiza el **Estado** de su fila en este archivo.
- **Quién mergea (Q-057):** el agente solo con certeza total (pipeline completo en verde en el último commit,
  veredicto del reviewer sin bloqueantes —obligatorio en zona roja—, DoD completo, squash). **Mientras no existan los
  11 checks y el ruleset (hasta T-PLT-40 inclusive) "pipeline completo" no se puede cumplir: mergea el dueño.** También
  mergea el dueño todo PR que cambie ruleset/ajustes del repo (T-PLT-40) o que quede con duda.
- Varias tareas editan `ci.yml`, `backend/pyproject.toml`, `config/settings/base.py`, `frontend/package.json`: en
  paralelo habrá conflictos de texto chicos; se rebasea sobre `main` antes de pedir el veredicto (un push nuevo
  invalida el veredicto anterior, AC-PLT-32).
- Antes de que exista `zona-roja.yml` (T-PLT-07) el veredicto del reviewer en zona roja se exige igual, por proceso.

## Resumen
| ID | Título | AC | Capa | Archivos esperados (ver detalle) | Depende de | Agente | Tamaño | Zona roja | Estado |
|---|---|---|---|---|---|---|---|---|---|
| T-PLT-01 | Esqueleto del repo + `check_file_size.py` | AC-PLT-13, AC-PLT-27 (parcial) | Infra | `scripts/check_file_size.py`, `.gitattributes`, … | — | backend-dev | M | Sí | ◐ en revisión (reviewer: aprobado con observaciones; falta PR/merge) |
| T-PLT-02 | Toolchain Python (uv) + `ruff.toml` | AC-PLT-12 | Infra | `backend/pyproject.toml`, `backend/uv.lock`, `ruff.toml` | T-PLT-01 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-03 | CI mínimo: `lint` → `file-size` → `tests` | AC-PLT-20 (parcial), AC-PLT-13 | CI | `.github/workflows/ci.yml`, `.github/actions/setup/action.yml` | T-PLT-02 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR; verificación manual en GitHub pendiente: push bloqueado) |
| T-PLT-04 | Pre-commit + gitleaks + job `secrets` | AC-PLT-19, AC-PLT-27, AC-PLT-13 | Infra/CI | `.pre-commit-config.yaml`, `.gitleaks.toml` | T-PLT-03 | backend-dev | M | Sí | ☐ |
| T-PLT-05 | `check_workflows.py` en `lint` | AC-PLT-33 | CI | `scripts/check_workflows.py` | T-PLT-03 | backend-dev | L | Sí | ☐ |
| T-PLT-06 | Check `zona-roja`: reglas y rutas | AC-PLT-32 | CI | `scripts/check_zona_roja.py`, `.github/zona-roja-paths.txt` | T-PLT-03 | backend-dev | L | Sí | ☐ |
| T-PLT-07 | Check `zona-roja`: API de GitHub + workflow | AC-PLT-32 | CI | `scripts/github_api.py`, `.github/workflows/zona-roja.yml` | T-PLT-05, T-PLT-06 | backend-dev | L | Sí | ☐ |
| T-PLT-08 | Proyecto Django + settings validados | AC-PLT-03 | Backend | `backend/config/settings/*`, `manage.py` | T-PLT-03 | backend-dev | L | Sí | ☐ |
| T-PLT-09 | `prod` endurecido + lecturas de entorno + feature flags | AC-PLT-04, AC-PLT-06 (parcial) | Backend | `config/settings/prod.py`, `apps/common/feature_flags.py` | T-PLT-08 | backend-dev | L | No | ☐ |
| T-PLT-10 | mypy + job `typecheck` (backend) | AC-PLT-21 (backend) | CI/Backend | `backend/pyproject.toml`, `tests/typing/` | T-PLT-08 | backend-dev | M | Sí | ☐ |
| T-PLT-11 | `/healthz` + `/readyz` + servicios en CI | AC-PLT-02 | Backend/CI | `apps/common/health/` | T-PLT-08 | backend-dev | M | Sí | ☐ |
| T-PLT-12 | Logger structlog JSON + `X-Request-ID` | AC-PLT-09 | Backend | `apps/common/logging/`, `middleware/request_id.py` | T-PLT-08 | backend-dev | L | No (reviewer recomendado) | ☐ |
| T-PLT-13 | Log de acceso (plantilla de ruta, `duration_ms`) | AC-PLT-07 | Backend | `middleware/access_log.py` | T-PLT-12 | backend-dev | M | No (reviewer recomendado) | ☐ |
| T-PLT-14 | Redacción de secretos en logs | AC-PLT-08 | Backend | `apps/common/domain/redaction.py` | T-PLT-13 | backend-dev | M | No (reviewer recomendado) | ☐ |
| T-PLT-15 | Errores `problem+json` | AC-PLT-34 | Backend/API | `apps/common/api/{problems,exceptions}.py` | T-PLT-12 | backend-dev | L | Sí | ☐ |
| T-PLT-16 | Throttling DRF con Redis | AC-PLT-30 | Backend/API | `apps/common/api/throttling.py` | T-PLT-11, T-PLT-15 | backend-dev | M | No | ☐ |
| T-PLT-17 | Celery + tarea de diagnóstico con `request_id` | AC-PLT-11 | Backend | `config/celery.py`, `apps/common/celery_signals.py` | T-PLT-11, T-PLT-12 | backend-dev | L | No (reviewer recomendado) | ☐ |
| T-PLT-18 | Contrato OpenAPI commiteado + `--check` | AC-PLT-23 (backend) | API/Contrato | `export_openapi.py`, `specs/_contracts/openapi.yaml` | T-PLT-15 | backend-dev | M | Sí | ☐ |
| T-PLT-19 | Tests de arquitectura C-09 y C-01 + job | AC-PLT-14, AC-PLT-15 | Arquitectura/CI | `backend/tests/architecture/` | T-PLT-08 | backend-dev | L | Sí | ☐ |
| T-PLT-20 | Chequeo C-02 (`float` en dinero) | AC-PLT-31 | Arquitectura | `ast_rules.py`, `allowlists.py` | T-PLT-19 | backend-dev | M | Sí | ☐ |
| T-PLT-21 | Gate de cobertura + job `coverage` | AC-PLT-22 | CI | `scripts/check_coverage.py`, `scripts/coverage_thresholds.toml` | T-PLT-08 | backend-dev | L | Sí | ☐ |
| T-PLT-22 | Migraciones: faltante + job `migrations` | AC-PLT-16 | Migraciones/CI | `tests/migrations/` | T-PLT-08, T-PLT-11 | backend-dev | M | Sí | ☐ |
| T-PLT-23 | Migraciones: nombres `auto_` y `RunPython` mezclado | AC-PLT-18 | Migraciones | `apps/common/migration_lint/`, `lint_migrations.py` | T-PLT-22 | backend-dev | L | Sí | ☐ |
| T-PLT-24 | Migraciones: reversibilidad + ida y vuelta | AC-PLT-17 | Migraciones/CI | `check_migrations_roundtrip.py` | T-PLT-23 | backend-dev | L | Sí | ☐ |
| T-PLT-25 | Imagen Docker del backend | AC-PLT-25 (backend) | Infra | `backend/Dockerfile`, `config/gunicorn.conf.py` | T-PLT-12 | backend-dev | M | Sí | ☐ |
| T-PLT-26 | Compose de desarrollo (db, redis, backend, worker, beat) | AC-PLT-01 (parcial), AC-PLT-02 (manual) | Infra | `infra/docker-compose.yml` | T-PLT-11, T-PLT-17, T-PLT-25 | backend-dev | L | Sí | ☐ |
| T-PLT-27 | Frontend: proyecto Next + toolchain + CI frontend | AC-PLT-21 (frontend) | Frontend/CI | `frontend/package.json`, `tsconfig.json`, … | T-PLT-03 | frontend-dev | L | Sí | ☐ |
| T-PLT-28 | Auditoría de dependencias + Dependabot | AC-PLT-26 | CI | `scripts/audit_deps.py`, `.github/dependabot.yml` | T-PLT-27 | backend-dev | L | Sí | ☐ |
| T-PLT-29 | Pre-commit de eslint/prettier | — (RF-PLT-12) | Infra | `scripts/precommit_frontend.py` | T-PLT-04, T-PLT-27 | frontend-dev | M | Sí | ☐ |
| T-PLT-30 | Base visual: tokens, tema, estados de carga | AC-PLT-28 (parcial), AC-PLT-22 (FE) | UI | `src/lib/{design-tokens,theme,query-client}.ts`, `src/components/*` | T-PLT-21, T-PLT-27 | frontend-dev | L | Sí | ☐ |
| T-PLT-31 | Shell `(dashboard)` + Inicio | AC-PLT-28 | UI | `src/components/shell/*`, `app/(dashboard)/inicio/*` | T-PLT-30 | frontend-dev | L | No | ☐ |
| T-PLT-32 | Configuración (secciones deshabilitadas) | AC-PLT-28 | UI | `app/(dashboard)/configuracion/*`, `src/modules/settings/*` | T-PLT-31 | frontend-dev | M | No | ☐ |
| T-PLT-33 | BFF pass-through con `X-Request-ID` | AC-PLT-10, AC-PLT-09 (BFF) | BFF | `app/api/[...path]/route.ts`, `src/lib/server/*` | T-PLT-27 | frontend-dev | L | No (reviewer recomendado) | ☐ |
| T-PLT-34 | BFF: rutas seguras y errores 400/502/504 | AC-PLT-10 (robustez) | BFF | `src/lib/server/backend-proxy.ts` | T-PLT-33 | frontend-dev | M | No (reviewer recomendado) | ☐ |
| T-PLT-35 | Cliente tipado + tipos desde OpenAPI + diff en CI | AC-PLT-23 (frontend) | Frontend/CI | `src/lib/{api-client,problem}.ts`, `src/types/api.d.ts` | T-PLT-18, T-PLT-27 | frontend-dev | M | Sí | ☐ |
| T-PLT-36 | Imagen del frontend + chequeo de bundle + servicio en Compose | AC-PLT-29, AC-PLT-25 (FE), AC-PLT-01 | Infra/Frontend | `frontend/Dockerfile`, `frontend/scripts/check-client-bundle.ts` | T-PLT-26, T-PLT-33 | frontend-dev | L | Sí | ☐ |
| T-PLT-37 | Job `build` (imágenes por SHA, no root) | AC-PLT-25, AC-PLT-20 | CI | `infra/docker-compose.ci.yml`, `ci.yml` | T-PLT-24, T-PLT-36 | backend-dev | M | Sí | ☐ |
| T-PLT-38 | Smoke del stack en el paso 9 | AC-PLT-01, AC-PLT-02, AC-PLT-10, AC-PLT-29 (E2E) | CI | `scripts/smoke_stack.py` | T-PLT-15, T-PLT-37 | backend-dev | L | Sí | ☐ |
| T-PLT-39 | `.env.example` + `spikes/.env.example` + paridad — **BLOQUEADA por Q-048** | AC-PLT-05, AC-PLT-06, AC-PLT-01 | Config | `.env.example`, `spikes/.env.example` | T-PLT-09, T-PLT-12, T-PLT-16, T-PLT-26, T-PLT-33 | usuario / backend-dev | M | Sí | ⛔ |
| T-PLT-40 | Ruleset de `main` + verificación de protección | AC-PLT-24, AC-PLT-20 (cierre) | Gobierno | `.github/rulesets/main.json`, `scripts/verify_repo_protection.py` | T-PLT-07, T-PLT-10, T-PLT-19, T-PLT-21, T-PLT-24, T-PLT-28, T-PLT-38 | backend-dev (+ dueño) | L | Sí | ☐ |
| T-PLT-41 | "Comandos de desarrollo" en `AGENTS.md` + `infra/README.md` | — (RF-PLT-16) | Docs | `AGENTS.md`, `infra/README.md` | T-PLT-38, T-PLT-40 | backend-dev | S | No | ☐ |

## Cobertura AC → tareas
| AC | Tareas |
|---|---|
| AC-PLT-01 | T-PLT-26 (5 servicios, manual), T-PLT-36 (6 servicios en Windows, manual), T-PLT-38 (smoke CI), T-PLT-39 (clon limpio con `.env` copiado de `.env.example`) |
| AC-PLT-02 | T-PLT-11 (integración), T-PLT-26 (manual con Redis detenido), T-PLT-38 (E2E) |
| AC-PLT-03 | T-PLT-08 |
| AC-PLT-04 | T-PLT-09 |
| AC-PLT-05 | T-PLT-39 ⛔ |
| AC-PLT-06 | T-PLT-09 (lecturas solo en `env.py` + patrones de proveedores), T-PLT-39 ⛔ (claves de `spikes/.env.example`) |
| AC-PLT-07 | T-PLT-13 (sobre la base de logger de T-PLT-12) |
| AC-PLT-08 | T-PLT-14 |
| AC-PLT-09 | T-PLT-12 (backend), T-PLT-33 (BFF) |
| AC-PLT-10 | T-PLT-33 (unitario), T-PLT-34, T-PLT-38 (E2E) |
| AC-PLT-11 | T-PLT-17 |
| AC-PLT-12 | T-PLT-02 |
| AC-PLT-13 | T-PLT-01 (script), T-PLT-03 (CI), T-PLT-04 (pre-commit) |
| AC-PLT-14 | T-PLT-19 |
| AC-PLT-15 | T-PLT-19 |
| AC-PLT-16 | T-PLT-22 |
| AC-PLT-17 | T-PLT-24 |
| AC-PLT-18 | T-PLT-23 |
| AC-PLT-19 | T-PLT-04 |
| AC-PLT-20 | T-PLT-03 (forma de la cadena), T-PLT-37 (build último), T-PLT-40 (11 jobs + PR de sacrificio) |
| AC-PLT-21 | T-PLT-10 (mypy), T-PLT-27 (tsc `strict`) |
| AC-PLT-22 | T-PLT-21 (script + backend/scripts), T-PLT-30 (umbral frontend) |
| AC-PLT-23 | T-PLT-18 (`openapi.yaml`), T-PLT-35 (tipos del frontend) |
| AC-PLT-24 | T-PLT-40 |
| AC-PLT-25 | T-PLT-25, T-PLT-36, T-PLT-37 |
| AC-PLT-26 | T-PLT-28 |
| AC-PLT-27 | T-PLT-01 (`.gitattributes`), T-PLT-04 (hook `mixed-line-ending`) |
| AC-PLT-28 | T-PLT-30 (`EmptyState`, `ErrorNotice`), T-PLT-31, T-PLT-32 |
| AC-PLT-29 | T-PLT-36, T-PLT-38 |
| AC-PLT-30 | T-PLT-16 |
| AC-PLT-31 | T-PLT-20 |
| AC-PLT-32 | T-PLT-06, T-PLT-07 |
| AC-PLT-33 | T-PLT-05 |
| AC-PLT-34 | T-PLT-15 |

**Sin AC propio** (cubiertos por tarea y test nombrado por RF/RN): RF-PLT-01 → T-PLT-01; RF-PLT-16 → T-PLT-41;
RF-PLT-19 → T-PLT-09; RNF-PLT-05 (hot-reload en Windows) → T-PLT-26/T-PLT-36 (manual); Q-056 → T-PLT-17/T-PLT-18.
**Huecos: ninguno.** AC-PLT-05 y la parte de spikes de AC-PLT-06 quedan cubiertos solo por T-PLT-39, bloqueada por Q-048.

## Orden y paralelismo
| Ola | Tareas | Notas |
|---|---|---|
| 0 (secuencial) | T-PLT-01 → T-PLT-02 → T-PLT-03 | Desde T-PLT-03 todo PR corre CI |
| 1 (tres carriles en paralelo) | **Gobierno:** T-PLT-04, T-PLT-05, T-PLT-06 (entre sí en paralelo) → T-PLT-07 · **Backend:** T-PLT-08 · **Frontend:** T-PLT-27 | |
| 2 | **Backend (tras T-PLT-08), en paralelo:** T-PLT-09, T-PLT-10, T-PLT-11, T-PLT-12, T-PLT-19, T-PLT-21 · **Frontend (tras T-PLT-27):** T-PLT-28, T-PLT-29, T-PLT-33 | |
| 3 | T-PLT-13 → T-PLT-14 · T-PLT-15 → {T-PLT-16, T-PLT-18} · T-PLT-17 · T-PLT-20 · T-PLT-22 → T-PLT-23 → T-PLT-24 · T-PLT-25 → T-PLT-26 · T-PLT-30 → T-PLT-31 → T-PLT-32 · T-PLT-34 · T-PLT-35 (tras T-PLT-18) | |
| 4 (secuencial) | T-PLT-36 → T-PLT-37 → T-PLT-38 → T-PLT-40 → T-PLT-41 | T-PLT-39 entra apenas se destrabe Q-048 (y antes de T-PLT-41) |

---

## Detalle por tarea

### T-PLT-01 — Esqueleto del repo + `check_file_size.py`
- **Objetivo:** primera pieza que hace cumplir una regla (C-14); estructura raíz y fin de línea LF.
- **AC:** AC-PLT-13; AC-PLT-27 (parte `.gitattributes`). RF-PLT-01, RF-PLT-08. **Zona roja:** sí (`scripts/**`).
- **Archivos:** `.gitattributes` (`* text=auto eol=lf` + binarios), `.editorconfig`, `.gitignore` (+ `coverage/`,
  `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`), `scripts/check_file_size.py`, `scripts/glob_paths.py`,
  `scripts/pytest.ini` (`-p no:django`), `scripts/tests/conftest.py` (repo git temporal),
  `scripts/tests/test_AC_PLT_13_check_file_size.py`, `scripts/tests/test_glob_paths.py`, `infra/scripts/README.md`
  (bitácora vacía, `08 §5`).
- **Cambios:** el script recorre `git ls-files -z`, cuenta líneas físicas, falla con 401+ nombrando cada archivo;
  exclusiones explícitas en el script: `backend/**/migrations/**` (acotada tras la revisión), `**/fixtures/**`, `frontend/src/types/**`,
  `next-env.d.ts`, `context/legacy-source/**` (Q-055), cada una comentada. Paths no ASCII (`Programación-2026`).
  Aplicar `git add --renormalize .`; si produce diff en archivos existentes, va en un commit separado dentro del PR.
- **Fuera de esta tarea:** hook de pre-commit (T-PLT-04), job de CI (T-PLT-03), carpetas de `backend/`/`frontend/`
  (las crea la tarea que pone código ahí; sin `.gitkeep` vacíos).
- **Plan de pruebas:** `test_AC_PLT_13_file_with_401_lines_fails_naming_it`,
  `test_AC_PLT_13_test_file_with_401_lines_fails`, `test_AC_PLT_13_file_with_400_lines_passes`,
  `test_AC_PLT_13_migration_and_generated_types_are_excluded`, `test_AC_PLT_13_legacy_source_is_excluded`,
  `test_AC_PLT_13_non_ascii_repo_path`, `test_AC_PLT_13_only_tracked_files_are_checked`; `test_glob_paths_*`
  (`**`, raíz, sin coincidencia). Local: pytest 9.2.0 en un venv/`uvx` (CI lo corre desde T-PLT-03).
- **DoD extra:** `python scripts/check_file_size.py` da 0 sobre el repo actual.

### T-PLT-02 — Toolchain Python (uv) + `ruff.toml`
- **Objetivo:** entorno Python fijado con lockfile para backend y `scripts/`; lint/format únicos.
- **AC:** AC-PLT-12. RN-PLT-11, RN-PLT-14 (lockfile). **Zona roja:** sí.
- **Archivos:** `backend/pyproject.toml` (deps runtime y grupo dev **exactas** de `design.md §8`: django 5.2.18, DRF
  3.16.1, celery[redis] 5.6.3, redis 6.4.0, psycopg[binary] 3.3.6, pydantic-settings 2.16.2, structlog 26.1.0,
  drf-spectacular 0.30.0, gunicorn 26.2.0; dev: ruff 0.17.3, mypy 1.19.1, django-stubs 5.2.9,
  djangorestframework-stubs 3.16.9, celery-types 0.26.0, pytest 9.2.0, pytest-django 4.14.0, pytest-cov 7.1.0,
  pip-audit 2.10.1, pyyaml 6.0.3; `requires-python ==3.12.*`), `backend/uv.lock`, `ruff.toml` (config de §3.6,
  `extend-exclude` comentado por Q-055, `force-exclude = true`, `per-file-ignores` tests `S101`, `scripts/**` `T20`),
  `scripts/tests/test_AC_PLT_12_ruff_print.py`.
- **Cambios:** `ruff.toml` además ignora **`N802`** en tests (`per-file-ignores` para `**/tests/**` y `test_*.py`):
  la convención `test_AC_…` de `AGENTS.md` usa mayúsculas y `select` incluye `N` (avisado por el reviewer en T-PLT-01).
- **Fuera de esta tarea:** `[tool.mypy]` (T-PLT-10), `[tool.pytest.ini_options]` de Django (T-PLT-08),
  `[tool.coverage]` (T-PLT-21). Sin código Django.
- **Plan de pruebas:** `test_AC_PLT_12_print_in_backend_apps_fails_lint` (`ruff check --stdin-filename
  backend/apps/demo/x.py -`), `test_AC_PLT_12_print_in_scripts_is_allowed`,
  `test_AC_PLT_12_legacy_source_is_force_excluded` (Q-055).
- **DoD extra:** `uv lock --check` limpio; `ruff check .` y `ruff format --check .` en verde sobre el repo.

### T-PLT-03 — CI mínimo: `lint` → `file-size` → `tests`
- **Objetivo:** que el CI exista desde ya; todas las tareas siguientes mergean con checks.
- **AC:** AC-PLT-20 (forma de la cadena), AC-PLT-13 (en CI). RN-PLT-11, RN-PLT-18. **Zona roja:** sí.
- **Archivos:** `.github/workflows/ci.yml` (`on: pull_request` a `main`, `push` a `main` y tags `v*`; `permissions:
  {contents: read}` top-level; `concurrency` con `cancel-in-progress` en PR; `env` común no secreto; jobs `lint` (ruff
  check + format --check), `file-size` (`needs: lint`), `tests` (`needs: file-size`; `pytest -c scripts/pytest.ini
  scripts/tests`); `uses:` por SHA de 40 hex), `.github/actions/setup/action.yml` (input `python`: setup-uv v10.3.3 +
  `uv python install 3.12.16` + `uv sync --frozen`; input `node` lo agrega T-PLT-27),
  `scripts/tests/test_AC_PLT_20_pipeline_chain.py`.
- **Fuera de esta tarea:** `secrets` (T-PLT-04), `check_workflows` (T-PLT-05), backend Django en `tests` (T-PLT-08).
- **Plan de pruebas:** `test_AC_PLT_20_jobs_follow_canonical_order` (jobs presentes = subsecuencia de la cadena de
  §3.5), `test_AC_PLT_20_each_job_needs_previous_present_job`, `test_AC_PLT_20_lint_is_first_without_needs`,
  `test_AC_PLT_20_no_job_level_if_on_required_jobs`.
- **Verificación manual:** el propio PR corre los 3 jobs en verde.

### T-PLT-04 — Pre-commit + gitleaks + job `secrets`
- **AC:** AC-PLT-19, AC-PLT-27, AC-PLT-13 (pre-commit). RF-PLT-12, RN-PLT-13, RNF-PLT-04. **Zona roja:** sí.
- **Archivos:** `.pre-commit-config.yaml` (hooks 1, 2, 3 y 5 de `design.md §3.6`; fixers excluyen
  `^context/legacy-source/`, gitleaks no), `.gitleaks.toml` (`useDefault = true`, allowlist `regexTarget = "secret"`
  para `<ver \.env: …>`, sin allowlist por ruta), `.github/workflows/ci.yml` (job `secrets`, `needs: file-size`,
  `fetch-depth: 0`, gitleaks v8.30.1 por digest sobre `base..head` / `before..after`, `--redact`, corre además
  `test_AC_PLT_19_gitleaks.py`; `tests` pasa a `needs: secrets`), `scripts/pytest.ini` (marker `gitleaks`, deseleccionado
  en `tests`), `scripts/tests/test_AC_PLT_19_gitleaks.py`, `scripts/tests/test_AC_PLT_27_line_endings.py`.
- **Fuera de esta tarea:** hooks de eslint/prettier (T-PLT-29), `deps-audit` (T-PLT-28).
- **Plan de pruebas:** `test_AC_PLT_19_token_shaped_secret_is_detected` (token falso generado en runtime, repo git
  temporal), `test_AC_PLT_19_env_placeholder_is_not_flagged`,
  `test_AC_PLT_19_placeholder_and_real_token_on_same_line_still_fails`;
  `test_AC_PLT_27_gitattributes_forces_lf_for_sh_and_dockerfile` (`git check-attr eol`),
  `test_AC_PLT_27_precommit_has_mixed_line_ending_fix_lf`, `test_RNF_PLT_04_precommit_has_no_tests_nor_migrations`.
- **Verificación manual (design §9):** `pre-commit install` + `pre-commit run --all-files` en verde; un commit con un
  token falso queda bloqueado; un `.sh` con CRLF queda normalizado a LF.

### T-PLT-05 — `check_workflows.py` en el job `lint`
- **AC:** AC-PLT-33. RN-PLT-18, RF-PLT-11. **Zona roja:** sí.
- **Archivos:** `scripts/check_workflows.py` (reglas de §3.5: `pull_request_target`/`workflow_run`, `permissions`
  top-level ausente o con scope que no es `read`/`none`, escritura de job fuera de `JOB_PERMISSION_ALLOWLIST` vacía,
  `secrets.*` distinto de `GITHUB_TOKEN`, `uses:` remoto sin SHA de 40 hex, `if:` a nivel de job requerido; clave `on`
  parseada como `True` por PyYAML), `scripts/tests/test_AC_PLT_33_check_workflows.py` (YAML sintético inline en el
  test), `.github/workflows/ci.yml` (step en `lint`).
- **Plan de pruebas:** `test_AC_PLT_33_pull_request_target_fails_naming_file`,
  `test_AC_PLT_33_write_token_by_default_fails_naming_file`, `test_AC_PLT_33_missing_top_level_permissions_fails`,
  `test_AC_PLT_33_workflow_run_fails`, `test_AC_PLT_33_unpinned_action_fails`,
  `test_AC_PLT_33_job_level_if_on_required_job_fails`, `test_AC_PLT_33_non_github_token_secret_fails`,
  `test_AC_PLT_33_repo_workflows_pass`.

### T-PLT-06 — Check `zona-roja`: reglas y lista de rutas
- **Objetivo:** la decisión del check como función pura, probada sin red.
- **AC:** AC-PLT-32. RN-PLT-12, Q-058. **Zona roja:** sí.
- **Archivos:** `scripts/check_zona_roja.py` (`evaluate(changed_paths, labels, verdicts, head_sha) -> Result`; parser
  del veredicto `<!-- reviewer-verdict -->` / `Veredicto del reviewer: APROBADO|RECHAZADO` / `SHA: <40 hex>`; carga
  de la lista de rutas con `glob_paths`), `.github/zona-roja-paths.txt` (rutas de §3.7.2, incluidas las del gate
  por Q-058, ya decidida), `scripts/tests/test_AC_PLT_32_zona_roja_rules.py`.
- **Fuera de esta tarea:** llamadas a la API, workflow (T-PLT-07).
- **Plan de pruebas:** `test_AC_PLT_32_no_red_paths_no_label_passes`, `test_AC_PLT_32_red_path_without_label_fails`,
  `test_AC_PLT_32_label_and_approved_verdict_by_writer_on_head_sha_passes`,
  `test_AC_PLT_32_verdict_by_account_without_write_is_ignored`, `test_AC_PLT_32_verdict_on_previous_sha_does_not_count`,
  `test_AC_PLT_32_latest_verdict_rejected_fails`, `test_AC_PLT_32_label_without_red_paths_still_needs_verdict`,
  `test_AC_PLT_32_renamed_file_old_path_counts`, `test_Q058_gate_paths_are_red`.

### T-PLT-07 — Check `zona-roja`: API de GitHub + workflow
- **AC:** AC-PLT-32. RN-PLT-12, RN-PLT-18. **Zona roja:** sí.
- **Archivos:** `scripts/github_api.py` (REST mínimo con `urllib`, paginado por `Link`, cualquier error o respuesta
  inesperada → excepción), `scripts/check_zona_roja.py` (`main()`: archivos del PR con rutas viejas y nuevas, labels,
  comentarios, `/collaborators/{u}/permission`; resumen en `$GITHUB_STEP_SUMMARY`; error de API → falla "no
  verificado"), `.github/workflows/zona-roja.yml` (tipos de `pull_request` de §3.7.3, **sin `paths:`**, permisos
  `contents/pull-requests/issues: read`, checkout de `pull_request.base.sha`, corre script y lista de la base — D-09),
  `scripts/tests/test_github_api.py`, `scripts/tests/test_AC_PLT_32_zona_roja_cli.py` (cliente HTTP falso inyectado).
- **Plan de pruebas:** `test_AC_PLT_32_api_error_fails_as_not_verified`,
  `test_AC_PLT_32_cli_reads_pr_data_and_writes_summary`, `test_AC_PLT_32_workflow_checks_out_base_sha_without_paths`;
  `test_github_api_paginates_link_header`, `test_github_api_unexpected_payload_raises`. `check_workflows.py` pasa
  sobre `zona-roja.yml`.
- **Verificación manual (dueño):** crear el label `zona-roja`; en un PR real: rutas rojas sin label → rojo; label +
  veredicto con el SHA → verde tras re-run; push nuevo → rojo.

### T-PLT-08 — Proyecto Django + settings validados
- **AC:** AC-PLT-03. RN-PLT-02, RF-PLT-03 (Q-040, Q-046). **Zona roja:** sí (`backend/pyproject.toml`, `ci.yml`).
- **Archivos:** `backend/manage.py`, `backend/config/__init__.py`, `backend/config/settings/__init__.py`,
  `backend/config/settings/env.py` (`PlatformEnv`: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
  `DATABASE_URL`, `REDIS_URL`, `APP_VERSION`; `env_file=None`, `case_sensitive=True`; `load_env()` →
  `ImproperlyConfigured(...) from None` con `errors(include_input=False, include_url=False)`),
  `backend/config/settings/{base,dev,test,prod}.py` (`prod.py` con `ProdEnv` sin defaults en lo obligatorio y
  validador de `DEBUG`; sin `django.contrib.*`; `USE_TZ`, `TIME_ZONE`, `LANGUAGE_CODE`), `backend/config/urls.py`,
  `backend/config/urls_dev.py`, `backend/config/wsgi.py`, `backend/apps/__init__.py`,
  `backend/apps/common/{__init__,apps}.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`,
  `backend/tests/config/test_AC_PLT_03_missing_required_var.py`, `backend/pyproject.toml`
  (`[tool.pytest.ini_options]`), `.github/workflows/ci.yml` (step `pytest` del backend en `tests`).
- **Fuera de esta tarea:** endurecimiento de `prod` y `check --deploy` (T-PLT-09), `LOG_LEVEL` (T-PLT-12),
  throttle/proxy (T-PLT-16), `REST_FRAMEWORK` (T-PLT-15).
- **Plan de pruebas (subproceso con `config.settings.prod`):**
  `test_AC_PLT_03_each_missing_required_var_fails_naming_it` (parametrizado por cada obligatoria),
  `test_AC_PLT_03_invalid_format_fails_naming_it`, `test_AC_PLT_03_error_contains_no_sentinel_value`,
  `test_RF_PLT_03_timezone_and_language_defaults`.

### T-PLT-09 — `prod` endurecido + lecturas de entorno + feature flags
- **AC:** AC-PLT-04; AC-PLT-06 (parte AST + patrones). RNF-PLT-02, RN-PLT-04, RF-PLT-19 (Q-052). **Zona roja:** no.
- **Archivos:** `backend/config/settings/prod.py` (SSL redirect con `SECURE_REDIRECT_EXEMPT` de health, proxy SSL
  header, HSTS 1 año + subdominios, cookies `Secure`, `X_FRAME_OPTIONS="DENY"`, `SECRET_KEY` fuerte; único
  silenciamiento `security.W021`, comentado), `backend/config/settings/env.py` (`FEATURE_<NOMBRE>` contra `REGISTRY`),
  `backend/apps/common/feature_flags.py`, `backend/tests/config/test_AC_PLT_04_check_deploy.py`,
  `backend/tests/config/test_AC_PLT_06_no_provider_env.py`, `backend/tests/config/test_RF_PLT_19_feature_flags.py`.
- **Fuera de esta tarea:** comparación contra claves de `spikes/.env.example` (T-PLT-39).
- **Plan de pruebas:** `test_AC_PLT_04_check_deploy_has_no_warnings` (subproceso `check --deploy --fail-level
  WARNING`), `test_AC_PLT_04_debug_true_in_prod_does_not_start`, `test_AC_PLT_04_weak_secret_key_in_prod_does_not_start`;
  `test_AC_PLT_06_env_is_read_only_in_env_py` (AST sobre `config/` y `apps/`; se admite solo
  `os.environ.setdefault("DJANGO_SETTINGS_MODULE", …)` en `wsgi.py`/`celery.py`),
  `test_AC_PLT_06_no_setting_matches_provider_patterns` (`^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_`);
  `test_RF_PLT_19_flag_off_by_default`, `test_RF_PLT_19_unregistered_flag_name_raises`,
  `test_RF_PLT_19_unregistered_feature_env_var_prevents_start`.

### T-PLT-10 — mypy + job `typecheck` (backend)
- **AC:** AC-PLT-21 (backend). RNF-PLT-09 (Q-033). **Zona roja:** sí.
- **Archivos:** `backend/pyproject.toml` (`[tool.mypy]` de §3.2.9: plugins, `check_untyped_defs`,
  `warn_unused_ignores`, override estricto enumerado para `apps.common.*` y `apps.*.domain.*`, `exclude` de
  `synthetic/`), `backend/tests/typing/__init__.py`, `backend/tests/typing/test_AC_PLT_21_mypy_strict.py`,
  `backend/tests/typing/synthetic/apps/common/untyped.py`, `…/synthetic/apps/demo/domain/untyped.py`,
  `…/synthetic/apps/demo/services/untyped.py`, `.github/workflows/ci.yml` (job `typecheck`, `needs: secrets`;
  `mypy . ../scripts`), arreglos de tipos mínimos en `scripts/*.py` si mypy los pide.
- **Cambios:** si los settings usan `django_stubs_ext.monkeypatch()`, mover `django-stubs-ext` (hoy fijado
  `==5.2.9` en el grupo dev por T-PLT-02) a las dependencias de runtime: en la imagen sin grupo dev el import
  fallaría (NB-3 del reviewer de T-PLT-02).
- **Fuera de esta tarea:** `export_openapi --check` (T-PLT-18), `tsc` (T-PLT-27).
- **Plan de pruebas:** `test_AC_PLT_21_untyped_def_in_common_fails`, `test_AC_PLT_21_untyped_def_in_domain_fails`,
  `test_AC_PLT_21_untyped_def_in_services_passes`, `test_AC_PLT_21_type_error_fails` (`mypy.api.run`).

### T-PLT-11 — `/healthz` + `/readyz` + servicios en CI
- **AC:** AC-PLT-02. RN-PLT-17, RF-PLT-07 (Q-039). **Zona roja:** sí (`ci.yml`).
- **Archivos:** `backend/apps/common/health/{__init__,checks,views}.py`, `backend/config/urls.py`,
  `backend/tests/health/__init__.py`, `backend/tests/health/test_AC_PLT_02_readyz.py`, `backend/pyproject.toml`
  (marker `integration`), `.github/workflows/ci.yml` (servicios `postgres:17.11-trixie` y `redis:7.4.12-bookworm` por
  digest en `tests`).
- **Plan de pruebas:** `test_AC_PLT_02_readyz_200_when_db_and_redis_up` (integration),
  `test_AC_PLT_02_readyz_503_when_redis_down_without_internal_details`, `test_AC_PLT_02_readyz_503_when_db_down`,
  `test_AC_PLT_02_healthz_200_with_short_sha_while_redis_down`, `test_AC_PLT_02_health_is_no_store_and_unauthenticated`.

### T-PLT-12 — Logger structlog JSON + `X-Request-ID`
- **AC:** AC-PLT-09 (base de AC-PLT-07). RN-PLT-05, RN-PLT-07, RF-PLT-05 (Q-034, Q-041).
  **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/apps/common/logging/{__init__,setup,processors,context}.py`,
  `backend/apps/common/domain/{__init__,request_id}.py`, `backend/apps/common/middleware/{__init__,request_id}.py`,
  `backend/config/settings/base.py` (`LOGGING`, `MIDDLEWARE` con `RequestId` primero),
  `backend/config/settings/env.py` (`LOG_LEVEL`), `backend/tests/logging/{__init__,conftest}.py` (captura de stdout),
  `backend/tests/logging/test_AC_PLT_09_request_id.py`, `backend/tests/logging/test_RN_PLT_05_json_renderer.py`,
  `backend/tests/api/{__init__,urls_test}.py`.
- **Fuera de esta tarea:** log de acceso (T-PLT-13), redacción (T-PLT-14), Celery (T-PLT-17), gunicorn (T-PLT-25).
- **Plan de pruebas:** `test_AC_PLT_09_valid_uuid4_is_kept_in_log_and_response`,
  `test_AC_PLT_09_non_uuid_is_replaced_by_new_uuid4`, `test_AC_PLT_09_trailing_newline_is_replaced`,
  `test_AC_PLT_09_oversized_header_is_replaced`; en `backend/tests/logging/test_RN_PLT_05_json_renderer.py`:
  `test_RN_PLT_05_one_json_event_per_line_on_stdout`, `test_RN_PLT_05_stdlib_logger_goes_through_same_renderer`.

### T-PLT-13 — Log de acceso
- **AC:** AC-PLT-07. RN-PLT-06 (plantilla de ruta), RNF-PLT-03. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/apps/common/middleware/access_log.py`, `backend/config/settings/base.py` (middleware;
  `django.server` y `django.request` silenciados), `backend/tests/api/urls_test.py` (ruta con parámetro),
  `backend/tests/logging/test_AC_PLT_07_access_log_json.py`.
- **Plan de pruebas:** `test_AC_PLT_07_line_is_valid_json_with_required_fields_and_utc_timestamp`,
  `test_AC_PLT_07_access_log_has_method_route_status_duration_ms`,
  `test_AC_PLT_07_request_id_equals_response_header`, `test_AC_PLT_07_unmatched_route_logs_placeholder`,
  `test_AC_PLT_07_health_requests_logged_at_debug`, `test_AC_PLT_07_5xx_logged_at_error`.

### T-PLT-14 — Redacción de secretos en logs
- **AC:** AC-PLT-08. RN-PLT-06 (C-06). **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/apps/common/domain/redaction.py` (recursiva, claves de §3.2.3),
  `backend/apps/common/logging/processors.py` (procesador de redacción), `backend/tests/logging/test_AC_PLT_08_redaction.py`.
- **Plan de pruebas:** `test_AC_PLT_08_bearer_cookie_and_query_never_logged` (request con `Authorization: Bearer
  <centinela>`, `Cookie`, query string a ruta con parámetro; ningún centinela en stdout),
  `test_AC_PLT_08_access_log_shows_route_template_not_raw_path`, `test_AC_PLT_08_redacts_nested_secret_like_keys`.

### T-PLT-15 — Errores `problem+json`
- **AC:** AC-PLT-34. RN-PLT-15 (Q-036), RN-PLT-16 (sin CORS). **Zona roja:** sí (contrato de errores).
- **Archivos:** `backend/apps/common/api/{__init__,problems,exceptions}.py`, `backend/config/settings/base.py`
  (`REST_FRAMEWORK`: auth `[]`, `AllowAny` provisorio, `UNAUTHENTICATED_USER=None`, solo JSON, `EXCEPTION_HANDLER`),
  `backend/config/urls.py` (`handler404`/`handler500`), `backend/tests/api/urls_test.py` (vista que explota),
  `backend/tests/api/test_AC_PLT_34_problem_json.py`, `backend/tests/api/test_RN_PLT_16_no_cors_headers.py`.
- **Plan de pruebas:** `test_AC_PLT_34_unhandled_exception_returns_problem_json_500`,
  `test_AC_PLT_34_500_has_code_and_request_id_without_trace_hosts_or_detail`,
  `test_AC_PLT_34_trace_only_in_log_with_same_request_id`, `test_AC_PLT_34_validation_error_has_errors_list`,
  `test_AC_PLT_34_unknown_api_route_returns_problem_404`, `test_AC_PLT_34_exception_headers_are_preserved`,
  `test_RN_PLT_16_backend_sends_no_cors_headers`.

### T-PLT-16 — Throttling DRF con Redis
- **AC:** AC-PLT-30. RN-PLT-19, RF-PLT-17 (Q-038). **Zona roja:** no.
- **Archivos:** `backend/apps/common/api/throttling.py` (`HubAnonRateThrottle`, `get_rate()` en runtime, fail-open
  D-06), `backend/config/settings/base.py` (`DEFAULT_THROTTLE_*`, `CACHES` `RedisCache` `KEY_PREFIX="hub"`),
  `backend/config/settings/test.py` (`LocMemCache` salvo `integration`), `backend/config/settings/env.py`
  (`API_THROTTLE_ANON_RATE` default `300/min`, `TRUSTED_PROXY_COUNT` → `NUM_PROXIES`),
  `backend/tests/api/test_AC_PLT_30_throttle_429.py`.
- **Plan de pruebas:** `test_AC_PLT_30_exceeding_anon_rate_returns_429_with_retry_after`,
  `test_AC_PLT_30_429_body_is_problem_json_throttled`, `test_AC_PLT_30_rate_read_from_settings_at_runtime`,
  `test_AC_PLT_30_counts_in_redis` (integration), `test_D06_throttle_fails_open_when_redis_down`,
  `test_RN_PLT_17_health_not_throttled`.

### T-PLT-17 — Celery + tarea de diagnóstico con `request_id`
- **AC:** AC-PLT-11. RN-PLT-05, RN-PLT-07, RNF-PLT-03, Q-056. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/config/celery.py`, `backend/config/__init__.py` (`celery_app`),
  `backend/apps/common/celery_signals.py`, `backend/apps/common/tasks.py` (`diagnostic_ping`),
  `backend/apps/common/apps.py` (`ready()` → señales), `backend/apps/common/api/dev_views.py`,
  `backend/config/urls_dev.py` (`/api/dev/diagnostic-task/`), `backend/config/settings/base.py` (`CELERY_*`:
  `worker_hijack_root_logger=False`, reintentos de broker), `backend/tests/logging/test_AC_PLT_11_celery_task_log.py`,
  `backend/tests/api/test_Q056_dev_routes_absent_in_prod.py`.
- **Plan de pruebas:** `test_AC_PLT_11_task_log_is_json_with_task_id_and_origin_request_id` (`start_worker`,
  integration), `test_AC_PLT_11_task_log_has_duration_ms_and_result_without_args`,
  `test_AC_PLT_11_invalid_request_id_in_task_header_is_replaced`,
  `test_AC_PLT_11_diagnostic_endpoint_returns_202_with_task_id_and_request_id`, `test_Q056_dev_routes_absent_in_prod`.

### T-PLT-18 — Contrato OpenAPI commiteado + `--check`
- **AC:** AC-PLT-23 (backend). RN-PLT-15, RF-PLT-14, ADR-0005. **Zona roja:** sí (contrato público).
- **Archivos:** `backend/apps/common/api/schema.py` (`API_VERSION="0.1.0"`, componente `Problem`, hook 4XX/5XX),
  `backend/apps/common/management/__init__.py`, `backend/apps/common/management/commands/__init__.py`,
  `backend/apps/common/management/commands/export_openapi.py` (`--check` imprime el diff),
  `specs/_contracts/openapi.yaml` (generado; se borra `specs/_contracts/.gitkeep`), `backend/config/settings/base.py`
  (`SPECTACULAR_SETTINGS`), `backend/config/urls_dev.py` (`/api/dev/schema/`, `/api/dev/docs/`),
  `backend/tests/contract/{__init__,test_AC_PLT_23_openapi_up_to_date}.py`,
  `backend/tests/api/test_Q056_dev_routes_absent_in_prod.py` (+ schema/docs), `.github/workflows/ci.yml` (step
  `export_openapi --check` en `typecheck`).
- **Plan de pruebas:** `test_AC_PLT_23_committed_openapi_matches_generated`,
  `test_AC_PLT_23_check_mode_fails_and_prints_diff_when_outdated`, `test_AC_PLT_23_problem_component_on_4xx_5xx`,
  `test_RN_PLT_15_info_version_set_and_no_version_in_url`.
- **Nota:** ADR-0005 figura **Propuesto**; conviene pasarlo a *Aceptado* antes de mergear esta tarea.

### T-PLT-19 — Tests de arquitectura C-09 y C-01 + job `architecture`
- **AC:** AC-PLT-14, AC-PLT-15. RN-PLT-09, RF-PLT-09. **Zona roja:** sí.
- **Archivos:** `backend/tests/architecture/{__init__,ast_rules,allowlists}.py` (C-09 con `Import`, `ImportFrom`
  relativos e `importlib.import_module("<literal>")`; C-01 `.objects`/`._default_manager`/`._base_manager` en
  `apps/*/services/**`; `ADAPTER_IMPORT_ALLOWLIST` y `ALLOWED_TENANT_MANAGERS` vacíos),
  `backend/tests/architecture/synthetic/charges/services/bad_provider_import.py`,
  `…/synthetic/integrations/providers/mercadopago/ok_internal_import.py`,
  `…/synthetic/integrations/providers/clover/bad_cross_provider.py`, `…/synthetic/charges/services/bad_objects.py`,
  `backend/tests/architecture/test_AC_PLT_14_adapter_boundary.py`,
  `backend/tests/architecture/test_AC_PLT_15_no_raw_objects_in_services.py`, `backend/pyproject.toml`
  (`norecursedirs`, `exclude` de mypy), `.github/workflows/ci.yml` (job `architecture`).
- **Plan de pruebas:** `test_AC_PLT_14_service_importing_provider_fails`, `test_AC_PLT_14_import_inside_same_provider_passes`,
  `test_AC_PLT_14_cross_provider_import_fails`, `test_AC_PLT_14_relative_and_importlib_imports_detected`,
  `test_AC_PLT_14_real_code_has_no_violations`; `test_AC_PLT_15_objects_in_services_fails`,
  `test_AC_PLT_15_default_and_base_manager_fail`, `test_AC_PLT_15_real_code_has_no_violations`.

### T-PLT-20 — Chequeo C-02 (`float` en dinero)
- **AC:** AC-PLT-31. RN-PLT-20, RF-PLT-18 (Q-047). **Zona roja:** sí.
- **Archivos:** `backend/tests/architecture/ast_rules.py` (regla C-02), `backend/tests/architecture/allowlists.py`
  (`AllowEntry(path, symbol, reason)`, `FLOAT_ALLOWLIST` vacía en el código real; falla con `reason` vacío o entrada
  muerta), `…/synthetic/charges/domain/bad_float.py`, `…/synthetic/charges/models.py` (`FloatField`),
  `…/synthetic/integrations/providers/mercadopago/ok_float.py`, `backend/tests/architecture/test_AC_PLT_31_no_float_money.py`.
- **Plan de pruebas:** `test_AC_PLT_31_floatfield_in_model_fails`,
  `test_AC_PLT_31_float_call_in_domain_services_selectors_api_fails`, `test_AC_PLT_31_float_inside_providers_passes`,
  `test_AC_PLT_31_allowlisted_entry_passes`, `test_AC_PLT_31_entry_without_reason_fails`,
  `test_AC_PLT_31_dead_allowlist_entry_fails`, `test_AC_PLT_31_real_code_has_no_violations`.

### T-PLT-21 — Gate de cobertura + job `coverage`
- **AC:** AC-PLT-22 (backend y `scripts/`; el parser del reporte frontend se prueba con fixture). RNF-PLT-08 (Q-032).
  **Zona roja:** sí.
- **Archivos:** `scripts/check_coverage.py`, `scripts/coverage_thresholds.toml` (backend `apps/`+`config/` 85 %
  líneas y ramas; `scripts/` 85 %; la entrada de frontend la agrega T-PLT-30; un reporte declarado que falta → falla),
  `scripts/tests/test_AC_PLT_22_check_coverage.py`, `backend/pyproject.toml` (`[tool.coverage.run]` `branch = true`,
  `patch = ["subprocess"]`, `source`), `.github/workflows/ci.yml` (`tests` genera y sube reportes con
  `upload-artifact` 7 días; job `coverage`, `needs: tests`, los baja y corre el script).
- **Plan de pruebas:** `test_AC_PLT_22_backend_lines_below_85_fails`, `test_AC_PLT_22_backend_branches_below_85_fails`,
  `test_AC_PLT_22_scripts_below_85_fails`, `test_AC_PLT_22_frontend_below_70_in_lib_hooks_modules_fails`,
  `test_AC_PLT_22_frontend_app_dir_is_not_gated`, `test_AC_PLT_22_declared_report_missing_fails`,
  `test_AC_PLT_22_exactly_at_threshold_passes`.
- **DoD extra:** la cobertura real de backend y `scripts/` al mergear ya está ≥ 85 %.

### T-PLT-22 — Migraciones: faltante + job `migrations`
- **AC:** AC-PLT-16. RN-PLT-10, RF-PLT-10. **Zona roja:** sí.
- **Archivos:** `backend/tests/migrations/{__init__,conftest,settings_synthetic}.py` (BD `hub_synthetic` creada y
  borrada por el test; comandos en subproceso), `backend/tests/migrations/synthetic_apps/__init__.py`,
  `…/synthetic_apps/missing_migration/{__init__,apps,models}.py` + `migrations/{__init__,0001_initial}.py`,
  `backend/tests/migrations/test_AC_PLT_16_missing_migration.py`, `.github/workflows/ci.yml` (job `migrations`,
  `needs: coverage`, servicio Postgres; `makemigrations --check --dry-run`).
- **Cambios:** evaluar reemplazar la exclusión total `**/migrations` de `ruff.toml` por `per-file-ignores` para
  migraciones (p. ej. `E501`, `RUF012`, `N806`), manteniendo `T20` y `S` activos en migraciones de datos; si se
  adopta, `ruff.toml` entra en los archivos de esta tarea (NB-2 del reviewer de T-PLT-02).
- **Plan de pruebas:** `test_AC_PLT_16_model_change_without_migration_fails_check`,
  `test_AC_PLT_16_real_apps_have_no_missing_migrations`.

### T-PLT-23 — Migraciones: nombres `auto_` y `RunPython` mezclado
- **AC:** AC-PLT-18. RN-PLT-10. **Zona roja:** sí.
- **Archivos:** `backend/apps/common/migration_lint/{__init__,rules}.py`,
  `backend/apps/common/management/commands/lint_migrations.py` (vía `MigrationLoader`, solo módulos `apps.*`),
  `…/synthetic_apps/bad_autoname/…` (`0001_initial` + `0002_auto_<fecha>`), `…/synthetic_apps/bad_mixed/…`,
  `backend/tests/migrations/test_AC_PLT_18_names_and_mixing.py`, `.github/workflows/ci.yml` (step `lint_migrations`).
- **Plan de pruebas:** `test_AC_PLT_18_auto_named_migration_fails`, `test_AC_PLT_18_0001_initial_is_accepted`,
  `test_AC_PLT_18_runpython_mixed_with_schema_ops_fails`, `test_AC_PLT_18_runpython_alone_passes`.

### T-PLT-24 — Migraciones: reversibilidad + ida y vuelta
- **AC:** AC-PLT-17. RN-PLT-10 (C-17). **Zona roja:** sí.
- **Archivos:** `backend/apps/common/migration_lint/rules.py` (`reversible is False`, `RunPython` sin `reverse_code`,
  `RunSQL` sin `reverse_sql`, dentro de `SeparateDatabaseAndState`; `RunPython.noop` aceptado),
  `backend/apps/common/management/commands/check_migrations_roundtrip.py`, `…/synthetic_apps/good_reversible/…`,
  `…/synthetic_apps/bad_irreversible/…`, `backend/tests/migrations/test_AC_PLT_17_reversibility.py`,
  `.github/workflows/ci.yml` (step `check_migrations_roundtrip`).
- **Plan de pruebas:** `test_AC_PLT_17_runpython_without_reverse_fails`, `test_AC_PLT_17_runsql_without_reverse_fails`,
  `test_AC_PLT_17_irreversible_inside_separate_db_and_state_fails`,
  `test_AC_PLT_17_reversible_migration_roundtrips_on_disposable_db`.

### T-PLT-25 — Imagen Docker del backend
- **AC:** AC-PLT-25 (backend, estático). RNF-PLT-01, RN-PLT-14, D-05. **Zona roja:** sí (`scripts/tests/`).
- **Archivos:** `backend/Dockerfile` (stages `builder`/`dev`/`runtime` de §3.4.2, `uv sync --frozen --no-dev`, uid
  10001, `ARG GIT_SHA` → `APP_VERSION`, label `revision`; imágenes por tag + digest resueltos acá),
  `backend/.dockerignore`, `backend/config/gunicorn.conf.py` (`logconfig_dict` de `logging/setup.py`, `accesslog=None`),
  `scripts/tests/test_AC_PLT_25_dockerfiles.py`.
- **Plan de pruebas:** `test_AC_PLT_25_backend_installs_from_frozen_lock`, `test_AC_PLT_25_backend_runtime_user_is_not_root`,
  `test_AC_PLT_25_backend_base_images_pinned_by_digest`, `test_RNF_PLT_01_dockerignore_excludes_env_and_git`,
  `test_RNF_PLT_01_runtime_has_no_dev_group_nor_tests`.
- **Verificación manual:** `docker build --target runtime --build-arg GIT_SHA=$(git rev-parse HEAD) backend` y `id -u` ≠ 0.

### T-PLT-26 — Compose de desarrollo (db, redis, backend, worker, beat)
- **AC:** AC-PLT-01 (parcial: 5 servicios), AC-PLT-02 (manual). RN-PLT-01, RF-PLT-02, RNF-PLT-05, D-04, D-05.
  **Zona roja:** sí (`scripts/tests/`).
- **Archivos:** `infra/docker-compose.yml` (`name: centro-pagos`; servicios, healthchecks y `depends_on` de §3.4.1;
  `environment:` explícito con `${VAR:?…}`, sin `env_file:`; `migrate` solo en `backend`; `beat` réplica 1 con
  `tmpfs`; puertos en `127.0.0.1`; volumen `pgdata`), `backend/apps/common/health/beat_alive.py`,
  `backend/tests/health/test_RF_PLT_02_beat_alive.py`, `scripts/tests/test_RF_PLT_02_compose_dev.py`,
  `infra/README.md` (prerrequisitos del host Q-060, recrear la BD, hot-reload por polling en Windows).
- **Fuera de esta tarea:** servicio `frontend` (T-PLT-36); bind mounts de `.env.example`/`spikes/.env.example`
  (T-PLT-39: montar un archivo inexistente crea un directorio).
- **Plan de pruebas:** `test_RF_PLT_02_every_service_has_healthcheck`, `test_RF_PLT_02_depends_on_service_healthy`,
  `test_RF_PLT_02_no_migrate_in_worker_or_beat`, `test_RF_PLT_02_single_beat_replica`,
  `test_RN_PLT_04_compose_uses_explicit_environment_without_env_file`, `test_RF_PLT_02_ports_bound_to_localhost`;
  `test_RF_PLT_02_beat_alive_stale_schedule_is_unhealthy`.
- **Verificación manual (dueño, Windows 11 + Docker Desktop, con un `.env` propio):** `up -d --build --wait` → 5
  servicios `healthy`, `/healthz` 200; `stop redis` → `/readyz` 503, `/healthz` 200, worker reintenta logueando;
  al volver Redis todo `healthy`; hot-reload del backend al editar un `.py`.

### T-PLT-27 — Frontend: proyecto Next + toolchain + CI frontend
- **AC:** AC-PLT-21 (frontend). RN-PLT-11, RN-PLT-14 (pnpm), Q-059 (MUI 9.5.0). **Zona roja:** sí.
- **Archivos:** `frontend/package.json` (versiones exactas de §8 incluidas MUI 9.5.0 y su ecosistema; `packageManager`
  pnpm 12.16.1 con hash; scripts `dev`, `build`, `lint`, `format:check`, `typecheck`, `test`), `frontend/pnpm-lock.yaml`,
  `frontend/.nvmrc` (24.22.2), `frontend/tsconfig.json` (`strict: true`), `frontend/eslint.config.mjs`,
  `frontend/.prettierrc.json`, `frontend/vitest.config.mts`, `frontend/vitest.setup.ts`, `frontend/next.config.ts`
  (§3.3.3), `frontend/next-env.d.ts`, `frontend/src/app/layout.tsx` (mínimo), `frontend/src/app/api/health/route.ts`,
  `frontend/src/app/api/health/route.test.ts`, `frontend/src/hooks/.gitkeep`, `.github/actions/setup/action.yml`
  (input `node`), `.github/workflows/ci.yml` (eslint `--max-warnings 0` + prettier en `lint`, `tsc --noEmit` en
  `typecheck`, `vitest --coverage` en `tests`), `scripts/tests/test_AC_PLT_21_tsconfig_strict.py`.
- **Fuera de esta tarea:** tema/MUI providers (T-PLT-30), páginas (T-PLT-31/32), BFF (T-PLT-33), Dockerfile (T-PLT-36).
- **Plan de pruebas:** `test_AC_PLT_21_tsconfig_has_strict_true`; vitest `test_RF_PLT_07_bff_health_returns_ok`.
  Manual: un error de tipos deliberado hace fallar `pnpm typecheck`.
- **DoD extra:** confirmar en npm que `@mui/material-nextjs` 9.5.0 tiene el subpath de App Router para Next 16
  (riesgo de §11.2) y anotar el resultado en el PR.

### T-PLT-28 — Auditoría de dependencias + Dependabot
- **AC:** AC-PLT-26. RN-PLT-14 (Q-037), D-10. **Zona roja:** sí.
- **Archivos:** `scripts/audit_deps.py` (pip-audit sobre `uv export --frozen --all-groups` + `pnpm audit --json`;
  severidad vía OSV; desconocida = alta; excepciones con vencimiento), `scripts/audit_exceptions.toml` (vacío,
  formato comentado), `scripts/tests/test_AC_PLT_26_audit_deps.py` (OSV y subprocesos mockeados, reloj fijo),
  `.github/dependabot.yml` (semanal: `uv` `/backend`, `npm` `/frontend`, `docker` `/backend`, `github-actions`;
  parches agrupados), `.github/workflows/ci.yml` (job `deps-audit`, `needs: file-size`; `typecheck` pasa a `needs:
  [secrets, deps-audit]`).
- **Plan de pruebas:** `test_AC_PLT_26_high_vuln_without_exception_fails`, `test_AC_PLT_26_critical_vuln_fails`,
  `test_AC_PLT_26_expired_exception_fails`, `test_AC_PLT_26_valid_exception_passes`,
  `test_AC_PLT_26_unknown_severity_counts_as_high`, `test_AC_PLT_26_pnpm_high_vuln_fails`,
  `test_RN_PLT_14_dependabot_weekly_for_all_ecosystems`.

### T-PLT-29 — Pre-commit de eslint/prettier
- **AC:** ninguno propio (RF-PLT-12: eslint/prettier en pre-commit; Q-060). **Zona roja:** sí.
- **Archivos:** `scripts/precommit_frontend.py` (quita el prefijo `frontend/`, excluye `src/types/`, llama a `pnpm
  --dir frontend exec`), `scripts/tests/test_RF_PLT_12_precommit_frontend.py`, `.pre-commit-config.yaml` (hooks locales
  `eslint` y `prettier`, `files: ^frontend/`).
- **Plan de pruebas:** `test_RF_PLT_12_strips_frontend_prefix`, `test_RF_PLT_12_excludes_generated_types`,
  `test_RF_PLT_12_propagates_tool_exit_code`. Manual: `pre-commit run --all-files` en el host con Node 24 + pnpm.

### T-PLT-30 — Base visual: tokens, tema, estados de carga
- **AC:** AC-PLT-28 (`EmptyState`, aviso con "Reintentar"); AC-PLT-22 (umbral frontend). RF-PLT-15 (Q-045).
  **Zona roja:** sí (`scripts/coverage_thresholds.toml`).
- **Archivos:** `frontend/src/lib/{design-tokens,theme,query-client}.ts`, `frontend/tailwind.config.ts` (`prefix:
  "tw-"`, `preflight: false`, Tailwind 3.4.19), `frontend/postcss.config.mjs`, `frontend/src/app/globals.css`,
  `frontend/src/app/providers.tsx`, `frontend/src/app/layout.tsx`, `frontend/src/components/{PageSkeleton,EmptyState,
  ErrorNotice}.tsx`, `frontend/src/components/{PageSkeleton,EmptyState,ErrorNotice}.test.tsx`,
  `frontend/src/lib/{theme,query-client}.test.ts`, `scripts/coverage_thresholds.toml` (frontend 70 % en `lib/`,
  `hooks/`, `modules/`), `.github/workflows/ci.yml` (el reporte de vitest se sube con los demás y lo lee `coverage`).
  La entrada del frontend entra acá y no en T-PLT-27 porque antes no hay código en `lib/` que medir.
- **Plan de pruebas:** `test_AC_PLT_28_error_notice_shows_retry_and_calls_on_retry`,
  `test_AC_PLT_28_empty_state_renders_title_and_text`, `test_RF_PLT_15_page_skeleton_variants`,
  `test_RF_PLT_15_theme_built_from_design_tokens`, `test_RF_PLT_15_query_client_defaults`.

### T-PLT-31 — Shell `(dashboard)` + Inicio
- **AC:** AC-PLT-28. RF-PLT-15, spec §14. **Zona roja:** no.
- **Archivos:** `frontend/src/components/shell/{AppShell,TopBar,NavMenu,OrgBranchSelectorPlaceholder,
  UserMenuPlaceholder}.tsx`, `frontend/src/components/shell/AppShell.test.tsx`, `frontend/src/app/(dashboard)/layout.tsx`,
  `frontend/src/app/(dashboard)/inicio/{page,loading,error}.tsx`, `frontend/src/app/page.tsx` (→ `/inicio`),
  `frontend/src/modules/home/components/HomeEmpty.tsx`, `frontend/src/modules/home/components/HomeEmpty.test.tsx`.
- **Plan de pruebas:** `test_AC_PLT_28_top_bar_has_disabled_org_branch_selector`,
  `test_AC_PLT_28_nav_links_to_inicio_and_configuracion`, `test_AC_PLT_28_active_item_follows_pathname`,
  `test_AC_PLT_28_home_shows_empty_state_never_blank`, `test_AC_PLT_28_route_error_shows_notice_with_retry`.

### T-PLT-32 — Configuración (secciones deshabilitadas)
- **AC:** AC-PLT-28 (destino de la navegación). Spec §14, `07 §5.3`. **Zona roja:** no.
- **Archivos:** `frontend/src/app/(dashboard)/configuracion/{page,loading,error}.tsx`,
  `frontend/src/modules/settings/settings-sections.ts`, `frontend/src/modules/settings/components/SettingsSectionList.tsx`,
  `frontend/src/modules/settings/components/SettingsSectionList.test.tsx`.
- **Plan de pruebas:** `test_AC_PLT_28_settings_lists_nine_sections_disabled_with_module_chip`,
  `test_AC_PLT_28_settings_route_error_shows_retry`.

### T-PLT-33 — BFF pass-through con `X-Request-ID`
- **AC:** AC-PLT-10, AC-PLT-09 (lado BFF). RN-PLT-07, RN-PLT-16, RF-PLT-06 (Q-050). **Zona roja:** no (reviewer
  recomendado).
- **Archivos:** `frontend/src/lib/server/{env,request-id,backend-proxy,log}.ts` (`import "server-only"`),
  `frontend/src/app/api/[...path]/route.ts` (`runtime="nodejs"`, `dynamic="force-dynamic"`),
  `frontend/src/lib/server/request-id.test.ts`, `frontend/src/lib/server/backend-proxy.test.ts` (fetch mockeado).
- **Fuera de esta tarea:** validación de path y errores 400/502/504 (T-PLT-34).
- **Plan de pruebas:** `test_AC_PLT_09_bff_keeps_valid_uuid4`, `test_AC_PLT_09_bff_replaces_invalid_or_newline`,
  `test_AC_PLT_10_bff_generates_request_id_when_missing_forwards_and_returns_it`,
  `test_RN_PLT_16_bff_forwards_only_allowlisted_headers_never_cookie`, `test_RN_PLT_16_bff_strips_set_cookie`,
  `test_RN_PLT_16_bff_preserves_query_string`, `test_RF_PLT_06_bff_logs_one_json_line_without_path`,
  `test_RN_PLT_16_backend_url_read_at_runtime_server_only`.

### T-PLT-34 — BFF: rutas seguras y errores
- **AC:** AC-PLT-10 (robustez del reenvío). RN-PLT-16, RF-PLT-06. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `frontend/src/lib/server/backend-proxy.ts` (rechaza `..`, `\`, `%2f`, `%5c` → `400 bff.bad_path`;
  mismo origen; timeout 30 s → `504 bff.upstream_timeout`; caído → `502 bff.upstream_unavailable`; siempre
  `problem+json` con `X-Request-ID`), `frontend/src/lib/server/backend-proxy.errors.test.ts`.
- **Plan de pruebas:** `test_RN_PLT_16_bff_rejects_dotdot_and_encoded_separators`,
  `test_RN_PLT_16_bff_rejects_cross_origin_target`, `test_RF_PLT_06_bff_upstream_down_returns_502_problem`,
  `test_RF_PLT_06_bff_timeout_returns_504_problem`.

### T-PLT-35 — Cliente tipado + tipos desde OpenAPI + diff en CI
- **AC:** AC-PLT-23 (frontend). RN-PLT-15, RF-PLT-15, ADR-0005. **Zona roja:** sí (`ci.yml`, consumidor del contrato).
- **Archivos:** `frontend/src/types/api.d.ts` (generado), `frontend/package.json` (script `openapi:types`),
  `frontend/src/lib/{problem,api-client}.ts`, `frontend/src/lib/{problem,api-client}.test.ts`,
  `.github/workflows/ci.yml` (en `typecheck`: `pnpm openapi:types && git diff --exit-code -- frontend/src/types`).
- **Plan de pruebas:** `test_AC_PLT_23_problem_json_becomes_api_error`, `test_RF_PLT_15_api_client_uses_same_origin`.
  Manual: cambiar `openapi.yaml` sin regenerar tipos → `typecheck` rojo mostrando el diff.

### T-PLT-36 — Imagen del frontend + chequeo de bundle + servicio en Compose
- **AC:** AC-PLT-29, AC-PLT-25 (frontend), AC-PLT-01 (6 servicios). RNF-PLT-01, RNF-PLT-05. **Zona roja:** sí.
- **Archivos:** `frontend/Dockerfile` (`deps`/`dev`/`builder` con centinelas para variables solo-servidor + bundle
  check/`runtime` standalone con `USER node`), `frontend/.dockerignore`, `frontend/scripts/check-client-bundle.ts`,
  `frontend/scripts/check-client-bundle.test.ts`, `frontend/vitest.config.mts` (incluye `scripts/`),
  `infra/docker-compose.yml` (servicio `frontend`, volúmenes `frontend_node_modules` y `pnpm_store`,
  `WATCHPACK_POLLING`), `.github/dependabot.yml` (`docker` `/frontend`), `scripts/tests/test_AC_PLT_25_dockerfiles.py`,
  `scripts/tests/test_RF_PLT_02_compose_dev.py`.
- **Plan de pruebas:** `test_AC_PLT_29_bundle_with_sentinel_fails`, `test_AC_PLT_29_bundle_with_non_public_var_name_fails`,
  `test_AC_PLT_29_clean_bundle_passes`, `test_AC_PLT_25_frontend_frozen_lockfile_and_non_root`,
  `test_RF_PLT_02_frontend_depends_on_healthy_backend`.
- **Verificación manual (dueño, Windows 11):** los 6 servicios `healthy`; hot-reload del frontend (si Turbopack
  ignora el polling, plan B `next dev --webpack` documentado en `infra/README.md`).

### T-PLT-37 — Job `build`
- **AC:** AC-PLT-25, AC-PLT-20 (build último de la cadena). Q-049. **Zona roja:** sí.
- **Archivos:** `infra/docker-compose.ci.yml` (imágenes `hub-*:${GIT_SHA}` target `runtime`, sin bind mounts,
  `config.settings.prod` con valores ficticios inline), `.github/workflows/ci.yml` (job `build`, `needs: migrations`;
  buildx + build-push ×2 `push: false`, `load: true`, tags `:${sha}` y `:vX.Y.Z` en tags, caché `gha`; `id -u` ≠ 0),
  `scripts/tests/test_AC_PLT_20_pipeline_chain.py` (build último).
- **Plan de pruebas:** `test_AC_PLT_20_build_is_last_and_needs_migrations`, `test_AC_PLT_25_ci_override_uses_sha_tagged_runtime_images`;
  el propio job en el PR es la prueba de AC-25.

### T-PLT-38 — Smoke del stack en el paso 9
- **AC:** AC-PLT-01, AC-PLT-02, AC-PLT-10, AC-PLT-29 (E2E). RF-PLT-07. **Zona roja:** sí.
- **Archivos:** `scripts/smoke_stack.py` (secuencia de §3.5; `down -v` siempre; cada fallo nombra servicio o check),
  `scripts/tests/test_smoke_stack.py` (subprocesos/HTTP mockeados, para la cobertura de `scripts/`),
  `.github/workflows/ci.yml` (step smoke en `build`).
- **Plan de pruebas:** `test_AC_PLT_01_smoke_requires_all_services_healthy`, `test_AC_PLT_02_smoke_expects_503_with_redis_stopped`,
  `test_AC_PLT_02_smoke_rejects_internal_details_in_body`, `test_AC_PLT_10_smoke_matches_bff_request_id_in_backend_logs`,
  `test_AC_PLT_01_smoke_always_tears_down`; E2E real en el job `build`.

### T-PLT-39 — `.env.example` + `spikes/.env.example` + paridad — ⛔ BLOQUEADA por Q-048
- **Bloqueo:** `.claude/settings.json` niega `Read(./.env.*)` y el archivo actual mezcla claves de spikes. Ningún agente
  puede leerlo ni reescribirlo con seguridad. Se destraba si **el usuario** (a) hace él mismo los cambios de archivos de
  esta tarea, (b) agrega una excepción de lectura para `.env.example` en `.claude/settings.json`, o (c) lo renombra.
  Los agentes no tocan esa configuración. También es acción del usuario mover las claves de spikes del `.env` local a
  `spikes/.env` (design §3.2.2).
- **AC:** AC-PLT-05, AC-PLT-06 (claves de spikes), AC-PLT-01 (clon limpio con `.env` copiado). RN-PLT-03, RN-PLT-04,
  RF-PLT-04. **Zona roja:** sí (separación de credenciales, C-06).
- **Archivos:** `.env.example` (solo plataforma, por grupos, valores ficticios de baja entropía),
  `spikes/.env.example` (claves de spikes con `<ver .env: NOMBRE>`),
  `backend/tests/config/test_AC_PLT_05_env_example_parity.py` (`COMPOSE_ONLY_VARS`, `FRONTEND_SERVER_VARS`),
  `backend/tests/config/test_AC_PLT_06_no_provider_env.py` (+ claves de `spikes/.env.example`),
  `infra/docker-compose.yml` (bind mounts `:ro` de ambos archivos en `backend`).
- **Plan de pruebas:** `test_AC_PLT_05_setting_missing_from_env_example_fails_naming_it`,
  `test_AC_PLT_05_env_example_var_not_read_fails_naming_it`, `test_AC_PLT_05_real_env_example_in_parity`,
  `test_AC_PLT_06_no_setting_matches_spike_keys`, `test_RN_PLT_04_spike_keys_absent_from_root_env_example`.
  Gitleaks pasa sobre ambos archivos.
- **Verificación manual (dueño):** clon limpio → `copy .env.example .env` → comando documentado → 6 servicios
  `healthy` y `/healthz` 200 (AC-PLT-01 literal).
- **DoD extra:** desde que esta tarea entra, toda tarea que agregue una variable a `env.py` también edita `.env.example`.

### T-PLT-40 — Ruleset de `main` + verificación de protección
- **AC:** AC-PLT-24; AC-PLT-20 (cierre: los 11 checks y PR de sacrificio). RN-PLT-12, RN-PLT-13, RN-PLT-18,
  RF-PLT-13, D-11. **Zona roja:** sí. **Merge: el dueño** (cambia ajustes del repo).
- **Archivos:** `.github/rulesets/main.json` (§3.7.1, `bypass_actors: []`, 0 aprobaciones, solo squash, los 11
  checks con `integration_id` de Actions), `.github/repo-settings.expected.json`, `scripts/verify_repo_protection.py`
  (usa `github_api.py`; exit 0/1/2), `scripts/tests/test_AC_PLT_24_verify_repo_protection.py` (fixtures de API inline),
  `scripts/tests/test_AC_PLT_20_pipeline_chain.py` (los 10 jobs de `ci.yml` + `zona-roja` = checks del ruleset),
  `infra/README.md` (sección "Repo público": Q-054 ya resuelta —repo público, gitleaks sobre todo el historial con 0
  hallazgos—; pendiente rotar tokens de MP y App Secret de Clover; cómo aplicar el ruleset).
- **Plan de pruebas:** `test_AC_PLT_24_matching_config_exits_0`, `test_AC_PLT_24_each_difference_is_named_and_exits_1`
  (aprobaciones ≠ 0, actor con bypass, check faltante, merge distinto de squash, force-push o borrado permitidos,
  secret scanning o push protection apagados, permisos de Actions de escritura),
  `test_AC_PLT_24_api_failure_exits_2_never_success`, `test_AC_PLT_20_ruleset_checks_equal_pipeline_jobs_plus_zona_roja`.
- **Verificación manual (dueño):** aplicar `main.json` con `gh api` + ajustes por UI (los checks ya corrieron al menos
  una vez); `python scripts/verify_repo_protection.py` con `GH_TOKEN` de admin propio → 0; PR de sacrificio con un error
  de lint → `lint` rojo, `build` no corre y el PR figura no mergeable.

### T-PLT-41 — "Comandos de desarrollo" en `AGENTS.md` + `infra/README.md`
- **AC:** ninguno propio (RF-PLT-16; Q-057). **Zona roja:** no.
- **Archivos:** `AGENTS.md` (sección "Comandos de desarrollo" con la tabla de `design.md §10.2` y la regla de merge
  de Q-057 / §3.7.4), `infra/README.md` (enlace a esos comandos, recrear BD antes de 01 por Q-053).
- **Plan de pruebas:** revisión manual: cada comando de la tabla se ejecuta una vez desde la raíz (PowerShell) y
  funciona; `pre-commit run --all-files` en verde.
