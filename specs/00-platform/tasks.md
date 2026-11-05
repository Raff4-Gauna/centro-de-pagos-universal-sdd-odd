---
spec: SPEC-00
actualizado: 2026-11-01
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
| T-PLT-04 | Pre-commit + gitleaks + job `secrets` | AC-PLT-19, AC-PLT-27, AC-PLT-13 | Infra/CI | `.pre-commit-config.yaml`, `.gitleaks.toml` | T-PLT-03 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-05 | `check_workflows.py` en `lint` | AC-PLT-33 | CI | `scripts/check_workflows.py` | T-PLT-03 | backend-dev | L | Sí | ☐ |
| T-PLT-06 | Check `zona-roja`: reglas y rutas | AC-PLT-32 | CI | `scripts/check_zona_roja.py`, `.github/zona-roja-paths.txt` | T-PLT-03 | backend-dev | L | Sí | ☐ |
| T-PLT-07 | Check `zona-roja`: API de GitHub + workflow | AC-PLT-32 | CI | `scripts/github_api.py`, `.github/workflows/zona-roja.yml` | T-PLT-05, T-PLT-06 | backend-dev | L | Sí | ☐ |
| T-PLT-08 | Proyecto Django + settings validados | AC-PLT-03 | Backend | `backend/config/settings/*`, `manage.py` | T-PLT-03 | backend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-09 | `prod` endurecido + lecturas de entorno + feature flags | AC-PLT-04, AC-PLT-06 (parcial) | Backend | `config/settings/prod.py`, `apps/common/feature_flags.py` | T-PLT-08 | backend-dev | L | No | ◐ en revisión (falta reviewer/PR) |
| T-PLT-10 | mypy + job `typecheck` (backend) | AC-PLT-21 (backend) | CI/Backend | `backend/pyproject.toml`, `tests/typing/` | T-PLT-08 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-11 | `/healthz` + `/readyz` + servicios en CI | AC-PLT-02 | Backend/CI | `apps/common/health/` | T-PLT-08 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-12 | Logger structlog JSON + `X-Request-ID` | AC-PLT-09 | Backend | `apps/common/logging/`, `middleware/request_id.py` | T-PLT-08 | backend-dev | L | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-13 | Log de acceso (plantilla de ruta, `duration_ms`) | AC-PLT-07 | Backend | `middleware/access_log.py` | T-PLT-12 | backend-dev | M | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-14 | Redacción de secretos en logs | AC-PLT-08 | Backend | `apps/common/domain/redaction.py` | T-PLT-13 | backend-dev | M | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-15 | Errores `problem+json` | AC-PLT-34 | Backend/API | `apps/common/api/{problems,exceptions}.py` | T-PLT-12 | backend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-16 | Throttling DRF con Redis | AC-PLT-30 | Backend/API | `apps/common/api/throttling.py` | T-PLT-11, T-PLT-15 | backend-dev | M | No | ◐ en revisión (falta reviewer/PR) |
| T-PLT-17 | Celery + tarea de diagnóstico con `request_id` | AC-PLT-11 | Backend | `config/celery.py`, `apps/common/celery_signals.py` | T-PLT-11, T-PLT-12 | backend-dev | L | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-18 | Contrato OpenAPI commiteado + `--check` | AC-PLT-23 (backend) | API/Contrato | `export_openapi.py`, `specs/_contracts/openapi.yaml` | T-PLT-15 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-19 | Tests de arquitectura C-09 y C-01 + job | AC-PLT-14, AC-PLT-15 | Arquitectura/CI | `backend/tests/architecture/` | T-PLT-08 | backend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-20 | Chequeo C-02 (`float` en dinero) | AC-PLT-31 | Arquitectura | `ast_rules.py`, `allowlists.py` | T-PLT-19 | backend-dev | M | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-21 | Gate de cobertura + job `coverage` | AC-PLT-22 | CI | `scripts/check_coverage.py`, `scripts/coverage_thresholds.toml` | T-PLT-08 | backend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-22 | Migraciones: faltante + job `migrations` | AC-PLT-16 | Migraciones/CI | `tests/migrations/` | T-PLT-08, T-PLT-11 | backend-dev | M | Sí | ☐ |
| T-PLT-23 | Migraciones: nombres `auto_` y `RunPython` mezclado | AC-PLT-18 | Migraciones | `apps/common/migration_lint/`, `lint_migrations.py` | T-PLT-22 | backend-dev | L | Sí | ☐ |
| T-PLT-24 | Migraciones: reversibilidad + ida y vuelta | AC-PLT-17 | Migraciones/CI | `check_migrations_roundtrip.py` | T-PLT-23 | backend-dev | L | Sí | ☐ |
| T-PLT-25 | Imagen Docker del backend | AC-PLT-25 (backend) | Infra | `backend/Dockerfile`, `config/gunicorn.conf.py` | T-PLT-12 | backend-dev | M | Sí | ☐ |
| T-PLT-26 | Compose de desarrollo (db, redis, backend, worker, beat) | AC-PLT-01 (parcial), AC-PLT-02 (manual) | Infra | `infra/docker-compose.yml` | T-PLT-11, T-PLT-17, T-PLT-25 | backend-dev | L | Sí | ☐ |
| T-PLT-27 | Frontend: proyecto Next + toolchain + CI frontend | AC-PLT-21 (frontend) | Frontend/CI | `frontend/package.json`, `tsconfig.json`, … | T-PLT-03 | frontend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-28 | Auditoría de dependencias + Dependabot | AC-PLT-26 | CI | `scripts/audit_deps.py`, `.github/dependabot.yml` | T-PLT-27 | backend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-29 | Pre-commit de eslint/prettier | — (RF-PLT-12) | Infra | `scripts/precommit_frontend.py` | T-PLT-04, T-PLT-27 | frontend-dev | M | Sí | ☐ |
| T-PLT-30 | Base visual: tokens, tema, estados de carga | AC-PLT-28 (parcial), AC-PLT-22 (FE) | UI | `src/lib/{design-tokens,theme,query-client}.ts`, `src/components/*` | T-PLT-21, T-PLT-27 | frontend-dev | L | Sí | ◐ en revisión (falta reviewer/PR) |
| T-PLT-31 | Shell `(dashboard)` + Inicio | AC-PLT-28 | UI | `src/components/shell/*`, `app/(dashboard)/inicio/*` | T-PLT-30 | frontend-dev | L | No | ☐ |
| T-PLT-32 | Configuración (secciones deshabilitadas) | AC-PLT-28 | UI | `app/(dashboard)/configuracion/*`, `src/modules/settings/*` | T-PLT-31 | frontend-dev | M | No | ☐ |
| T-PLT-33 | BFF pass-through con `X-Request-ID` | AC-PLT-10, AC-PLT-09 (BFF) | BFF | `app/api/[...path]/route.ts`, `src/lib/server/*` | T-PLT-27 | frontend-dev | L | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-34 | BFF: rutas seguras y errores 400/502/504 | AC-PLT-10 (robustez) | BFF | `src/lib/server/backend-proxy.ts`, `next.config.ts` | T-PLT-33 | frontend-dev | M | No (reviewer recomendado) | ◐ en revisión (falta reviewer/PR) |
| T-PLT-35 | Cliente tipado + tipos desde OpenAPI + diff en CI | AC-PLT-23 (frontend) | Frontend/CI | `src/lib/{api-client,problem}.ts`, `src/types/api.d.ts` | T-PLT-18, T-PLT-27 | frontend-dev | M | Sí | ☐ |
| T-PLT-36 | Imagen del frontend + chequeo de bundle + servicio en Compose | AC-PLT-29, AC-PLT-25 (FE), AC-PLT-01 | Infra/Frontend | `frontend/Dockerfile`, `frontend/scripts/check-client-bundle.ts` | T-PLT-26, T-PLT-33, T-PLT-34 | frontend-dev | L | Sí | ☐ |
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
| 4 (secuencial) | T-PLT-36 → T-PLT-37 → T-PLT-38 → T-PLT-40 → T-PLT-41 | T-PLT-36 espera también a T-PLT-34 (el BFF no se expone en Compose sin la validación de rutas) · T-PLT-39 entra apenas se destrabe Q-048 (y antes de T-PLT-41) |

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
  3.16.1 (hoy 3.18.2: revisión de Q-059 del 2026-11-01), celery[redis] 5.6.3, redis 6.4.0, psycopg[binary] 3.3.6,
  pydantic-settings 2.16.2, structlog 26.1.0, drf-spectacular 0.30.0, gunicorn 26.2.0; dev: ruff 0.17.3, mypy 1.19.1, django-stubs 5.2.9,
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
  los tests `-m gitleaks`; `typecheck` pasa a `needs: secrets`), `scripts/pytest.ini` (marker `gitleaks`, deseleccionado
  en `tests`), `scripts/tests/test_AC_PLT_19_gitleaks.py`, `scripts/tests/test_AC_PLT_27_line_endings.py`. Tras la
  revisión de `3d50418` además `scripts/tests/{gitleaks_support,test_AC_PLT_19_secrets_job,test_AC_PLT_19_gitleaks_evasions}.py`
  y `scripts/tests/conftest.py` (fixtures `two_commits` y `scan`), al partir el módulo de tests que ya tenía 378 líneas.
- **Fuera de esta tarea:** hooks de eslint/prettier (T-PLT-29), `deps-audit` (T-PLT-28).
- **Plan de pruebas:** `test_AC_PLT_19_token_shaped_secret_is_detected` (token falso generado en runtime, repo git
  temporal), `test_AC_PLT_19_env_placeholder_is_not_flagged`,
  `test_AC_PLT_19_placeholder_and_real_token_on_same_line_still_fails`;
  `test_AC_PLT_27_gitattributes_forces_lf_for_sh_and_dockerfile` (`git check-attr eol`),
  `test_AC_PLT_27_precommit_has_mixed_line_ending_fix_lf`, `test_RNF_PLT_04_precommit_has_no_tests_nor_migrations`.
- **Verificación manual (design §9):** `pre-commit install` + `pre-commit run --all-files` en verde; un commit con un
  token falso queda bloqueado; un `.sh` con CRLF queda normalizado a LF.
- **Hecho (commits `feat(platform)`, `ci(platform)`, `test(platform)`):** hooks 1, 2, 3 y 5 de §3.6 con los repos
  remotos fijados por SHA (`# frozen: vX`, verificados con `git ls-remote`); `.gitleaks.toml` como dice §3.6, con
  `[[allowlists]]` (el `[allowlist]` único está deprecado en v8.30). Job `secrets` (`needs: file-size`; `typecheck`
  pasa a `needs: secrets`, no `tests`: el anterior presente de `typecheck` es `secrets`), imagen
  `zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0…bbb7f` (índice multi-arch, verificado con `docker pull` y la API del
  registry). El paso `range` valida que solo lleguen SHAs de 40 hex a `--log-opts` y, en `push`, escanea todo el
  historial de `after` si `before` son 40 ceros o no está en el clon. Tests extra: el paso `range` se ejecuta con bash
  (PR, push, primer push, `before` ausente, valores no-SHA) y la forma del job, de `.gitleaks.toml` y del hook. Los
  tests Docker corren en los dos modos (staged y rango de PR). Mutaciones verificadas: `regexTarget = "line"` hace
  fallar `placeholder_and_real_token_on_same_line`; allowlist `.*`, también `token_shaped_secret_is_detected`.
  gitleaks v8.30.1 sobre todo el historial (`--log-opts=--all`, 72 commits, 25 ramas locales): 0 hallazgos, con
  `.gitleaks.toml` y con las reglas por defecto.
- **Verificación manual** (clon temporal, contenedor `python:3.12.16-slim-trixie` + pre-commit 4.7.0; en el host
  Windows falló por `MAX_PATH` de la ruta del scratchpad, no por el repo): un commit con un token falso queda
  bloqueado por `gitleaks` (`github-pat`, valor `REDACTED`); un `.sh` CRLF lo reescribe `mixed-line-ending` y queda
  `i/lf w/lf`. `pre-commit run --all-files`: la primera pasada dio todo en verde **salvo `end-of-file-fixer`**
  sobre 3 archivos fuera de la tarea (sin salto final: `propuesta/evidencia-postman-mp/{1-crear-sucursal,2-crear-caja}.md`;
  3 líneas vacías al final: `propuesta/Universal_Payments_Hub___Propuesta_de_Proyecto.md`); después del commit
  `style(docs)` y con la regla de MP, los 15 hooks en verde (exit 0).
- **Scope drift (resuelto por el planner, opción a):** commit `style(docs): fix end of file in propuesta/` aparte
  (2 líneas cambiadas, 3 borradas); con eso `pre-commit run --all-files` queda en verde.
- **Decidido por el planner (spec 1.0.4, `design.md §3.6`):** (1) las reglas por defecto de gitleaks no detectaban
  `APP_USR-…` en ninguna forma ni `TEST-…` en JSON, headers o query strings (hueco de C-06): regla propia
  `mercadopago-access-token` en `.gitleaks.toml`, con `useDefault = true`. Tests:
  `test_AC_PLT_19_mercadopago_token_is_detected_in_every_form` (token falso generado en runtime, 4 formas, los dos
  prefijos y los dos modos), `test_AC_PLT_19_repo_history_has_no_findings` (`git log -p --all` por stdin) y la regla
  en el test de forma `RN_PLT_13`. Mutación: sin la regla fallan los 4 casos de MP. Historial completo
  (`--log-opts=--all`, repo principal en solo lectura, 83 commits): 0 hallazgos con `.gitleaks.toml` y 0 con la
  regla sola (control: la misma config detecta un token falso). (2) Repos de pre-commit fijados por SHA: registrado
  en §3.6.
- **Notas:** (3) hoy ninguna regla por defecto marca el placeholder (tiene espacios y `<`): la allowlist es
  defensiva y el test de forma la fija a ese patrón exacto. (4) En un PR, `secrets` usa la `.gitleaks.toml` del
  propio PR (un PR podría ampliar la allowlist); lo cubre el reviewer obligatorio de zona roja (Q-058), no el CI.
- **Revisión de `3d50418`: CAMBIOS REQUERIDOS, aplicados** (spec 1.0.5). Los tests de Docker ahora ejecutan el paso
  real `range` + `scan` del job (bash) y el `entry` real del hook, sin copia de las flags.
  - **B-1** `gitleaks:allow` en línea anulaba el hallazgo → `--ignore-gitleaks-allow` en job y hook.
    Test: `test_AC_PLT_19_inline_gitleaks_allow_does_not_hide_a_token` (los dos modos).
  - **B-2** `.gitleaksignore` se cargaba solo → paso `no-gitleaksignore` (`git ls-files ':(glob)**/.gitleaksignore'`)
    y ruta roja en design §3.7.2 (nota en T-PLT-06). Tests: `test_AC_PLT_19_tracked_gitleaksignore_fails_the_job`
    (raíz y profundo), `…_passes_without_one`, `…_runs_before_the_scan`.
  - **B-3** merge "malvado" → `--diff-merges=first-parent`. Test: `test_AC_PLT_19_secret_added_only_by_a_merge_commit_is_detected`
    (`--no-ff --no-commit` + archivo nuevo); con `--cc` en su lugar el test falla (verificado).
  - **B-4** diff binario → `--text`. Test: `test_AC_PLT_19_secret_in_a_file_git_treats_as_binary_is_detected`
    (`-diff` en `.gitattributes` y byte NUL). Solo CI: el hook no recibe `--text` (design §3.6: el gate es CI).
  - **B-5** allowlist sin anclar → `^<ver \.env: [A-Z][A-Z0-9_]*>$`. Test:
    `test_AC_PLT_19_private_key_with_a_placeholder_inside_is_detected` (sin el ancla el hallazgo `private-key`
    desaparece); el placeholder solo sigue sin marcarse, también en los 10 archivos reales que lo usan.
  - **B-6** allowlist global de rutas heredada con `useDefault` → **Q-062**, opción (b) por defecto.
  - **B-7** (verificación de `4790f6e`) esa allowlist saltea a cualquier profundidad rutas donde puede haber código
    → paso de guarda `no-allowlisted-paths` (`git ls-files -z` contra
    `gitleaks\.toml|(^|/)(node_modules|bower_components)/|(^|/)venv/lib/`, sin distinguir mayúsculas, salvo
    `.gitleaks.toml`). Tests: `test_AC_PLT_19_file_under_a_default_allowlisted_path_fails_the_job` (6 rutas,
    mayúsculas incluidas), `…_repo_gitleaks_config_alone_passes_the_guard`, `…_runs_before_the_scan`. Hoy 0
    falsos positivos en wt-04 y en el repo principal. Además `no-gitleaksignore` usa `':(glob,icase)…'` (caso
    `.GitLeaksIgnore`).
  - **N-2** gate real = CI, en design §3.6. **N-3** `--verbose` se mantiene: sin él gitleaks no dice regla,
    archivo, línea ni commit (justificado en `ci.yml` y §3.6); con `--redact` el valor no sale. **N-4** línea de
    archivos alineada (`typecheck`).
- **Para después:** (1) chequeo propio que falle si `frontend/pnpm-lock.yaml` tiene credenciales en URLs
  (`://user:pass@`, `_authToken`): mitigación de Q-062, cuando exista el lockfile (T-PLT-27). (2) Tokens de Mercado
  Pago que la regla no cubre (N-1): formato legado `__LX_LY__`, prefijo en minúsculas y refresh tokens `TG-…`; y la
  public key (`APP_USR-`/`TEST-` + UUID). (3) Credenciales en URLs del lockfile: por stdin, `generic-api-key` detecta
  `_authToken=…`, pero ninguna regla por defecto detecta `https://user:pass@registry…` (verificado con v8.30.1), así
  que el chequeo propio de (1) sigue pendiente. (4) Ninguno de estos bloquea T-PLT-04. (5) Re-verificación de
  `962a62a`: `scan-lockfiles` falla abierto si `git log` da error (`bash -e` sin `pipefail`: stdin vacío y
  gitleaks sale 0); no es provocable porque `range` valida las SHAs, pero conviene `set -o pipefail` al inicio del
  `run` más un test. (6) Un secreto agregado y borrado dentro del PR bajo una ruta de la allowlist por defecto
  (`a/node_modules/x.py`) no lo ve ningún paso (la guarda mira solo el árbol final); no llega a `main` por el
  squash, pero queda en los commits del PR.
- **`frontend/pnpm-lock.yaml` (decisión del planner):** la guarda lo exceptúa solo por ruta exacta
  (`GITLEAKS_EXEMPT_LOCKFILES`, lista única del job), y el paso `scan-lockfiles` pasa su diff del rango por
  `gitleaks stdin`. Tests: `test_AC_PLT_19_token_in_the_exempt_lockfile_fails_the_lockfile_scan` (el escaneo
  principal no lo ve; el paso nuevo sí), `test_AC_PLT_19_clean_exempt_lockfile_passes_the_lockfile_scan` (con y
  sin cambios en el rango), `test_AC_PLT_19_exempt_lockfile_passes_the_guard`,
  `test_AC_PLT_19_lockfile_at_another_path_still_fails_the_guard` (`x/`, raíz, `frontend/app/`) y la forma de la
  lista. Con la lista vacía fallan los de la guarda, la forma y el token (verificado). La guarda pasa sobre el
  árbol de T-PLT-27, y el historial real del lockfile da 0 hallazgos por stdin.
- **Guarda ampliada (después de B-7, decisión del coordinador):** `no-allowlisted-paths` lleva textuales las 21
  entradas de directorios o rutas de la allowlist por defecto de v8.30.1 (las 4 de extensiones quedan como riesgo
  aceptado en Q-062, `.svg` aparte) y falla cerrada si `grep` da error. Tests:
  `test_AC_PLT_19_guard_covers_every_directory_entry_of_the_default_allowlist` (`gitleaks`: lee la allowlist del
  binario de la imagen fijada y exige que la guarda y los ejemplos coincidan con ella),
  `test_AC_PLT_19_every_guard_entry_has_an_example_that_fails_the_guard` (un archivo por entrada; `sub/.git` git
  lo ignora), y los casos `env/lib/`, `virtualenv/lib/`, `venv/lib64/`, `lib/python3.12/`, `*-1.0.dist-info/`,
  `vendor/bundle/` y `vendor/github.com/…`. Con la guarda de B-7 fallan los 9 tests nuevos (verificado).

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
  Nota (review de T-PLT-28, B-1): la lista suma `frontend/pnpm-workspace.yaml`, `frontend/.npmrc`,
  `frontend/.pnpmfile.*` y `frontend/package.json` (por el campo `pnpm`), porque la config de pnpm (`auditConfig`,
  `auditLevel`, `registry`, hooks `updateConfig`) puede ocultar advisories; el gate `deps-audit` ya corre aislado
  de ellos, la ruta roja exige además el veredicto del reviewer.
  Nota (review de T-PLT-28, B-3), sugerencia para la lista: `backend/uv.lock` (una entrada con `source = {
  directory = ... }` mete código local en el install) y **cualquier directorio nuevo bajo `backend/` que no sea
  `apps/`, `config/` o `tests/`** (ahí vive el build backend que esa entrada apuntaría); también
  `scripts/audit_tool_requirements.txt` si la regla de rutas del gate (Q-058) no cubre ya todo `scripts/`. El
  gate ya no instala el venv del backend ni construye nada (`--no-build`); la ruta roja suma el veredicto.
  Nota (review final de T-PLT-28, B-4/B-5): también los **archivos sueltos nuevos en `backend/`** (no solo los
  directorios: un `backend/pip_audit.py` o `backend/rich.py` reemplazaba a pip-audit) y las configs de la raíz
  que leen las herramientas del gate: `/uv.toml`, `/pyproject.toml` (`[tool.uv]`), `/package.json`
  (`packageManager`), `/.npmrc` y `/.python-version`. El gate ya corre aislado de ellas (`-I`, `--no-config`,
  `pnpm --version` en `$RUNNER_TEMP`); la ruta roja suma el veredicto.
- **Fuera de esta tarea:** llamadas a la API, workflow (T-PLT-07).
- **Plan de pruebas:** `test_AC_PLT_32_no_red_paths_no_label_passes`, `test_AC_PLT_32_red_path_without_label_fails`,
  `test_AC_PLT_32_label_and_approved_verdict_by_writer_on_head_sha_passes`,
  `test_AC_PLT_32_verdict_by_account_without_write_is_ignored`, `test_AC_PLT_32_verdict_on_previous_sha_does_not_count`,
  `test_AC_PLT_32_latest_verdict_rejected_fails`, `test_AC_PLT_32_label_without_red_paths_still_needs_verdict`,
  `test_AC_PLT_32_renamed_file_old_path_counts`, `test_Q058_gate_paths_are_red`.
- **Nota (revisión de T-PLT-04, B-2):** `**/.gitleaksignore` entra en `.github/zona-roja-paths.txt` con las rutas
  del gate (design §3.7.2): gitleaks lo carga solo y cada huella anula un hallazgo. Test:
  `test_Q058_gitleaksignore_at_any_depth_is_red` (`.gitleaksignore` y `docs/x/.gitleaksignore` son rojas).

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
- **Desvío registrado (revisión, N-4):** el validador de `DEBUG` de `ProdEnv` es un `field_validator` y no el
  `model_validator` que nombra `design.md §3.2.2`, para que el error nombre la variable
  (`- DJANGO_DEBUG: debug_on_in_prod`). Tests agregados por la revisión: `backend/tests/config/__init__.py`,
  `test_C_06_env_secrets.py` (`repr`/`str`/`model_dump` y `__context__` sin valores; `del _env`) y
  `test_RF_PLT_03_env_parsing.py` (`databases()`, vacío = ausente).

- **Pendiente tras la revisión (O-2) — ✅ resuelto** en la rama de T-PLT-12 (commit `chore(platform): treat backend
  as first-party in ruff and drop N999 noqa`): `ruff.toml` suma `N999` a los `per-file-ignores` de `**/tests/**` y
  `**/test_*.py` y `src = ["backend"]` (`config`/`apps` son first-party); se quitaron los 4 `# ruff: noqa: N999`
  (los 3 de `backend/tests/config/` y el de `backend/tests/health/`) y `ruff check --fix` reordenó los imports
  (también `backend/config/urls.py` y `backend/tests/conftest.py`).

### T-PLT-09 — `prod` endurecido + lecturas de entorno + feature flags
- **AC:** AC-PLT-04; AC-PLT-06 (parte AST + patrones). RNF-PLT-02, RN-PLT-04, RF-PLT-19 (Q-052). **Zona roja:** no.
- **Archivos:** `backend/config/settings/prod.py` (SSL redirect con `SECURE_REDIRECT_EXEMPT` de health, proxy SSL
  header, HSTS 1 año + subdominios, cookies `Secure`, `X_FRAME_OPTIONS="DENY"`, `SECRET_KEY` fuerte; único
  silenciamiento `security.W021`, comentado), `backend/config/settings/env.py` (`FEATURE_<NOMBRE>` contra `REGISTRY`),
  `backend/apps/common/feature_flags.py`, `backend/tests/config/test_AC_PLT_04_check_deploy.py`,
  `backend/tests/config/test_AC_PLT_06_no_provider_env.py`, `backend/tests/config/test_RF_PLT_19_feature_flags.py`.
- **Fuera de esta tarea:** comparación contra claves de `spikes/.env.example` (T-PLT-39).
- **Pendiente de la revisión de T-PLT-08:** rechazar `DJANGO_ALLOWED_HOSTS='*'` en prod (N-10 de la revisión
  de T-PLT-08).
- **Pendiente de la revisión de T-PLT-13 (N-a):** decidir `django.security.DisallowedHost`: hoy loguea ERROR con
  `exc_info` (traza completa) por cada `Host` inválido, que en prod puede ser ruido de escaneos. Opciones: bajarlo
  a WARNING sin `exc_info`, o silenciarlo y quedarse con el 400 del access log.
- **Plan de pruebas:** `test_AC_PLT_04_check_deploy_has_no_warnings` (subproceso `check --deploy --fail-level
  WARNING`), `test_AC_PLT_04_debug_true_in_prod_does_not_start`, `test_AC_PLT_04_weak_secret_key_in_prod_does_not_start`;
  `test_AC_PLT_06_env_is_read_only_in_env_py` (AST sobre `config/` y `apps/`; se admite solo
  `os.environ.setdefault("DJANGO_SETTINGS_MODULE", …)` en `wsgi.py`/`celery.py`),
  `test_AC_PLT_06_no_setting_matches_provider_patterns` (`^(MP|MERCADOPAGO|CLOVER|PAYWAY|DECIDIR|PRISMA)_`);
  `test_RF_PLT_19_flag_off_by_default`, `test_RF_PLT_19_unregistered_flag_name_raises`,
  `test_RF_PLT_19_unregistered_feature_env_var_prevents_start`.
- **Hecho (4 commits, uno por AC/pendiente):** `prod.py` con lo de §3.2.2 y `SILENCED_SYSTEM_CHECKS =
  ["security.W021"]`; `ProdEnv` valida `DJANGO_SECRET_KEY` (≥ 50, ≥ 5 distintos, sin `django-insecure` en
  ninguna posición; tipos `secret_key_too_short/_few_characters/_insecure`) y rechaza `*` en
  `DJANGO_ALLOWED_HOSTS` (`allowed_hosts_wildcard`, N-10). `env.load_feature_flags(REGISTRY)` →
  `settings.FEATURE_FLAGS` (vacío = sin definir; no registrada → `feature_unregistered`; valor no
  `true`/`false` → `bool_format`; solo nombres). N-a: `django.security.DisallowedHost` sale como WARNING sin
  `exception` (filtro `WarningWithoutTraceback` en `logging/setup.py`; con `LOG_LEVEL=ERROR` se descarta); se
  conserva el mensaje, que nombra el host, para diagnosticar un `ALLOWED_HOSTS` mal puesto. Tests extra:
  `test_AC_PLT_04_wildcard_allowed_host_in_prod_does_not_start`,
  `test_AC_PLT_04_http_redirects_to_https_except_health`, `test_AC_PLT_06_scanner_finds_every_env_read`,
  `test_AC_PLT_06_provider_pattern`, `test_RF_PLT_19_{flag_follows_its_variable,empty_variable_counts_as_unset,
  invalid_value_fails_naming_only_the_variable,settings_expose_every_registered_flag}` y
  `tests/logging/test_RN_PLT_05_disallowed_host.py`.
- **Desvío de alcance:** `config/settings/{dev,test}.py` (cargan `FEATURE_FLAGS` igual que `prod`; sin eso
  `is_enabled` no vería las variables en dev/test) y `apps/common/logging/setup.py` + su test (N-a, que esta
  tarea hereda). No se tocaron `ci.yml` ni `backend/pyproject.toml`.
- **Preguntas para el planner (decisión conservadora aplicada):** (a) `DisallowedHost`: ¿reemplazar el mensaje
  por uno fijo para no loguear el `Host` del atacante? Hoy se conserva (útil y acotado por la redacción a 8192).
  (b) Si fallan el entorno y los flags a la vez, primero se informa el entorno: se ven en dos arranques. ¿Unificar
  el mensaje? (c) El escáner AST no ve `getattr(os, "environ")`, `importlib`/`__import__` ni `sys.modules`:
  ¿suficiente como red, o se suma al test de arquitectura (T-PLT-2x)? (d) `tests/conftest.py` repite
  `FEATURE_PREFIX`: podría importarlo de `env.py`.
- **Revisión de `e899175`: APROBADO.** Aplicado en el mismo PR: `SECURE_REDIRECT_EXEMPT` termina en `\Z` (con `$`,
  `/healthz%0A` quedaba exento del redirect) y el test suma `/HEALTHZ` y `/healthz%0A`. Respuestas: (a) conservar el
  `Host` en el log, cortado a ~255 caracteres; (b) no unificar por ahora; (c) no alcanza como única red: llevarlo al
  test de arquitectura junto con el punto 1 de abajo; (d) sí, en un commit aparte. Para después:
  1. AC-PLT-06: una subclase de `PlatformEnv` en `apps/` (`class MpEnv(PlatformEnv): MP_ACCESS_TOKEN: str`) y
     `from pydantic.v1 import BaseSettings` dan 0 hallazgos. Prohibir importar `config.settings.env` fuera de
     `config/settings/` y prohibir `pydantic.v1` (RN-PLT-04, C-09).
  2. **Despliegue (T-PLT-25/26):** con `SECURE_PROXY_SSL_HEADER`, un cliente que mande `X-Forwarded-Proto: https`
     saltea el redirect, y Django toma el primer valor de una lista. El proxy tiene que **pisar** el header (no
     agregar), el contenedor no puede ser alcanzable sin pasar por el proxy, y `/healthz`/`/readyz` no se publican
     por HTTP hacia afuera.
  3. `load_feature_flags` (`env.py:172`) distingue mayúsculas en Linux: `feature_x` se ignora en silencio (queda
     apagado, el default seguro de Q-052, pero un typo debería impedir arrancar).
  4. La nota "Hecho" dice 4 commits; son 5 contando el de docs.

### T-PLT-10 — mypy + job `typecheck` (backend)
- **AC:** AC-PLT-21 (backend). RNF-PLT-09 (Q-033). **Zona roja:** sí.
- **Archivos:** `backend/pyproject.toml` (`[tool.mypy]` de §3.2.9: plugins, `check_untyped_defs`,
  `warn_unused_ignores`, override estricto enumerado para `apps.common.*` y `apps.*.domain.*`, `exclude` de
  `synthetic/`), `backend/tests/typing/__init__.py`, `backend/tests/typing/test_AC_PLT_21_mypy_strict.py`,
  `backend/tests/typing/synthetic/apps/common/untyped.py`, `…/synthetic/apps/demo/domain/untyped.py`,
  `…/synthetic/apps/demo/services/untyped.py`, `.github/workflows/ci.yml` (job `typecheck`, `needs: file-size`, que pasa a `[secrets, deps-audit]` cuando existan;
  `mypy . ../scripts`), arreglos de tipos mínimos en `scripts/*.py` si mypy los pide.
- **Cambios:** si los settings usan `django_stubs_ext.monkeypatch()`, mover `django-stubs-ext` (hoy fijado
  `==5.2.9` en el grupo dev por T-PLT-02) a las dependencias de runtime: en la imagen sin grupo dev el import
  fallaría (NB-3 del reviewer de T-PLT-02).
- **Fuera de esta tarea:** `export_openapi --check` (T-PLT-18), `tsc` (T-PLT-27).
- **Plan de pruebas:** `test_AC_PLT_21_untyped_def_in_common_fails`, `test_AC_PLT_21_untyped_def_in_domain_fails`,
  `test_AC_PLT_21_untyped_def_in_services_passes`, `test_AC_PLT_21_type_error_fails` (`mypy.api.run`).
- **Hecho (commits `fix(tests)` y `ci(platform)`):** `[tool.mypy]` con `check_untyped_defs`, `warn_unused_ignores`,
  `exclude` de `synthetic/` y el override de `apps.common.*`/`apps.*.domain.*` con los 10 flags de §3.2.9 (los
  únicos de `strict` que mypy acepta por módulo; `warn_unused_configs`, `warn_redundant_casts` y `strict_bytes`
  son solo globales). Job `typecheck` (`mypy . ../scripts` desde `backend/`) enganchado a `file-size`, el anterior
  presente: pasa a `needs: [secrets, deps-audit]` cuando entren T-PLT-04 y T-PLT-28; `tests` pasa a `needs:
  typecheck`. Los sintéticos se pasan explícitos con `--explicit-package-bases` y `MYPYPATH=synthetic/` (solo
  nombran módulos). Mutaciones verificadas: sin override fallan los dos tests de strict; sin `check_untyped_defs`,
  `type_error_fails`. Test extra: `test_AC_PLT_21_typecheck_job_runs_mypy_on_backend_and_scripts` (como el de
  `pnpm typecheck` de T-PLT-27). Errores de mypy: 29 → 0. 9 se iban con el plugin `pydantic.mypy` (campos de
  `BaseSettings` leídos como argumentos obligatorios). Los otros 20 eran de tests y se corrigieron sin
  `# type: ignore`, incluida la nota 2 de la revisión de T-PLT-15. `django_stubs_ext.monkeypatch()` no hace falta: el
  único genérico subindexado en runtime (`serializers.Serializer[...]`, `tests/api/urls_test.py`) ya trae
  `__class_getitem__` de DRF, así que `django-stubs-ext` sigue en el grupo dev (NB-3).
- **Desvío de alcance:** los arreglos de tipos tocan 5 tests fuera de la lista
  (`tests/{api/test_AC_PLT_34_problem_json,config/test_C_06_env_secrets,config/test_RF_PLT_03_env_parsing,
  health/test_AC_PLT_02_readyz,logging/test_RN_PLT_05_json_renderer}.py`). `scripts/*.py` no necesitó cambios.
- **Preguntas para el planner (decisión conservadora aplicada):** (a) se agregó el plugin `pydantic.mypy`, que
  §3.2.9 no nombra: viene con pydantic, que ya es dependencia de runtime, así que no suma dependencias. ¿Va al
  design? (b) ¿`warn_redundant_casts` y `warn_unused_configs` globales? No los pide §3.2.9 y no se agregaron.
- **Revisión de `f774250`: APROBADO.** Aplicado en el mismo PR: `exclude` anclado a `tests/typing/synthetic/` (antes
  `(^|/)synthetic/` dejaba sin chequear cualquier carpeta `synthetic/` del código real; verificado con un def sin
  anotar en `apps/common/synthetic/`), y la línea "Archivos" pasa a `needs: file-size`. Para después:
  1. Registrar el plugin `pydantic.mypy` en design §3.2.9 con fila en el Historial (recomendado mantenerlo).
  2. Agregar `warn_redundant_casts` y `strict_bytes` globales (hoy 0 errores) con nota en el design; **no**
     `warn_unused_configs` (exige `--no-incremental` y avisa en las corridas de un solo sintético).
  3. `files = [".", "../scripts"]` en `[tool.mypy]`, para que `mypy` sin argumentos (pre-commit) replique CI.
  4. `tests/api/test_AC_PLT_34_problem_json.py:28` depende del tipo privado `_MonkeyPatchedWSGIResponse` de
     django-stubs: alias en un solo lugar o comentario.
  5. `tests/config/test_RF_PLT_03_env_parsing.py:22-26` repite a mano las claves de `REQUIRED`.
- **Merge con la línea frontend:** las dos agregan `typecheck`. Resolver con un solo job: `needs: deps-audit`
  (→ `[secrets, deps-audit]` con T-PLT-04), setup con `python: "true"` y `node: "true"`, y dos pasos:
  `mypy . ../scripts` (`working-directory: backend`) y `pnpm typecheck` (`working-directory: frontend`).

### T-PLT-11 — `/healthz` + `/readyz` + servicios en CI
- **AC:** AC-PLT-02. RN-PLT-17, RF-PLT-07 (Q-039). **Zona roja:** sí (`ci.yml`).
- **Archivos:** `backend/apps/common/health/{__init__,checks,views}.py`, `backend/config/urls.py`,
  `backend/tests/health/__init__.py`, `backend/tests/health/test_AC_PLT_02_readyz.py`, `backend/pyproject.toml`
  (marker `integration`), `.github/workflows/ci.yml` (servicios `postgres:17.11-trixie` y `redis:7.4.12-bookworm` por
  digest en `tests`).
- **Plan de pruebas:** `test_AC_PLT_02_readyz_200_when_db_and_redis_up` (integration),
  `test_AC_PLT_02_readyz_503_when_redis_down_without_internal_details`, `test_AC_PLT_02_readyz_503_when_db_down`,
  `test_AC_PLT_02_healthz_200_with_short_sha_while_redis_down`, `test_AC_PLT_02_health_is_no_store_and_unauthenticated`.
- **Notas de implementación:** `/readyz` toma Redis de `CACHES["default"]` (`RedisCache` → `REDIS_URL` en dev/prod;
  si la caché no es Redis, falla cerrado) con un cliente propio de 1 s y **sin reintentos** (redis-py reintenta 3
  veces con backoff por defecto). `health.not_ready` lleva solo `check` y `error_type` (clase de la excepción): el
  mensaje de un driver puede traer host/usuario/DSN (C-06). Los tres tests de `/readyz` son `integration` (cada uno
  necesita la *otra* dependencia arriba para que el log pruebe cuál falló); los de `/healthz` y `no-store` corren sin
  servicios (`pytest -m "not integration"`). Tests agregados a los del plan (pruebas de mutación):
  `test_AC_PLT_02_readyz_503_when_cache_is_not_redis` (integration, falla cerrado) y
  `test_C_06_not_ready_log_has_no_exception_message` (sin servicios: en Windows un puerto cerrado da timeouts sin host
  en el mensaje, así que solo un error sintético prueba que el mensaje nunca llega al log).

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
- **Pendiente de la revisión de T-PLT-08:** la redacción de logs/página de debug debe cubrir
  `CACHES['default']['LOCATION']` con contraseña de Redis (N-9). **Resuelto en esta tarea** para lo que vuelca
  settings: `DEFAULT_EXCEPTION_REPORTER_FILTER` propio (`apps/common/logging/report_filter.py`) oculta además
  `LOCATION`, `DSN` y toda clave que termine en `URL` en settings y en `request.META` (página de debug y reporte de
  error), y el logger `django` pierde `mail_admins` (su mail embebe ese reporte). Tests:
  `test_C_06_error_report_never_shows_the_redis_password`, `test_C_06_error_log_never_carries_the_settings`.
  **Queda para T-PLT-14:** la redacción por clave de los *eventos* de log (§3.2.3) no incluye `location` ni enmascara
  URLs con `user:password`; T-PLT-14 debe cubrirlo (y revisar `django.db.backends` en `DEBUG`, que loguea SQL con
  parámetros).
- **Normalización:** el `X-Request-ID` válido se devuelve y se loguea **en minúsculas**, igual que el BFF
  (T-PLT-33/34): un UUIDv4 en mayúsculas se acepta y sale en minúsculas.
- **Plan de pruebas:** `test_AC_PLT_09_valid_uuid4_is_kept_in_log_and_response`,
  `test_AC_PLT_09_non_uuid_is_replaced_by_new_uuid4`, `test_AC_PLT_09_trailing_newline_is_replaced`,
  `test_AC_PLT_09_oversized_header_is_replaced`; en `backend/tests/logging/test_RN_PLT_05_json_renderer.py`:
  `test_RN_PLT_05_one_json_event_per_line_on_stdout`, `test_RN_PLT_05_stdlib_logger_goes_through_same_renderer`.
- **Notas de implementación:** `LOGGING_CONFIG = "apps.common.logging.setup.configure_logging"` (aplica el
  `dictConfig` y configura structlog en un solo lugar, reutilizable por gunicorn/Celery). Único handler
  `StdoutHandler` en root, que escribe en el `sys.stdout` *actual* en cada emit (los tests lo capturan con `capsys`).
  Los `extra=` de loggers stdlib se vuelcan como campos solo si son escalares JSON (Django adjunta el `request`, cuyo
  `repr` trae el path crudo). Los `warnings` de Python no se redirigen al log (sin `captureWarnings`; **cambia en T-PLT-14**: ahora sí, como eventos `py.warnings`). Tests
  agregados a los del plan: header ausente, header en respuesta 500, contexto limpio tras la request, middleware
  primero, parser puro, `organization_id` solo ligado, ningún handler a archivo/`mail_admins`, `LOG_LEVEL` filtra y
  se valida.
- **Desvío de alcance (registrado):** además de los archivos listados se tocaron `config/settings/{dev,test,prod}.py`
  (dos líneas cada uno: el import y `LOGGING = logging_config(_env.LOG_LEVEL)`; el nivel validado solo existe donde
  se carga el entorno y `base.py` no lo lee) y se creó `apps/common/logging/report_filter.py` (N-9; separado de
  `setup.py` para no importar `django.views.debug` en cada proceso que configura logging).
- **Para T-PLT-13:** `django.server` conserva el handler de texto de `DEFAULT_LOGGING` (solo `runserver`) y
  `django.request` loguea `"Internal Server Error: <path crudo>"` por el renderer JSON; T-PLT-13 los silencia.

### T-PLT-13 — Log de acceso
- **AC:** AC-PLT-07. RN-PLT-06 (plantilla de ruta), RNF-PLT-03. **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/apps/common/middleware/access_log.py`, `backend/config/settings/base.py` (middleware;
  `django.server` y `django.request` silenciados), `backend/tests/api/urls_test.py` (ruta con parámetro),
  `backend/tests/logging/test_AC_PLT_07_access_log_json.py`.
- **Plan de pruebas:** `test_AC_PLT_07_line_is_valid_json_with_required_fields_and_utc_timestamp`,
  `test_AC_PLT_07_access_log_has_method_route_status_duration_ms`,
  `test_AC_PLT_07_request_id_equals_response_header`, `test_AC_PLT_07_unmatched_route_logs_placeholder`,
  `test_AC_PLT_07_health_requests_logged_at_debug`, `test_AC_PLT_07_5xx_logged_at_error`.
- **Ampliado tras revisión de T-PLT-12:**
  - **N-1 (fuga introducida por T-PLT-12):** con `django` propagando al root, cada 4xx/5xx escribía
    `"Not Found: /path/crudo"` (`django.request`). Se silencian `django.request`, `django.security.csrf` (loguea
    `"Forbidden (...): <path>"`) y `django.server` con un `NullHandler` y `propagate=False` (sin handler, el
    `lastResort` de `logging` igual escribiría WARNING+ a stderr). El silenciamiento vive en `logging_config()`
    de `apps/common/logging/setup.py`, no en `base.py`: `dev`/`test`/`prod` reconstruyen `LOGGING` desde ahí.
    Como `django.request` ya no muestra la traza de un 500, el access log la lleva cuando la causa
    es una excepción (ver O-1/O-2 más abajo: tipo y frames, sin mensaje). Se rehicieron
    `test_AC_PLT_09_header_is_returned_on_an_error_response` y `test_C_06_error_log_never_carries_the_settings`
    sobre el evento `http.request`. Tests nuevos: `test_RN_PLT_06_no_raw_path_for_404_400_403_500` (404 resuelto y
    sin resolver, 400, 403 por permiso y por CSRF, 500; ningún segmento ni query en stdout/stderr) y
    `test_RN_PLT_06_silenced_loggers_write_nothing_outside_pytest` (subproceso: pytest cuelga sus handlers de
    captura de cada logger y oculta el `lastResort`).
  - **N-7 (streaming):** con `StreamingHttpResponse`, `duration_ms` mide hasta que la vista devuelve la respuesta
    (headers), no hasta enviar el cuerpo, y lo que se loguee mientras el servidor WSGI itera el cuerpo ya no tiene
    `request_id` (el middleware limpió el contexto). No hay endpoints con streaming en 00: queda documentado en
    `access_log.py`; cuando exista uno, medir con un *closer* de la respuesta.
- **Ampliado tras revisión de T-PLT-13 (commit `fix(platform): access log follow-ups from T-PLT-13 review`):**
  - **O-1:** la excepción se toma de la señal `got_request_exception` (Django la emite dentro del `except`) y no de
    `process_exception`: así también llegan al evento los 500 lanzados por un middleware interno, `process_view`,
    el URLconf o `process_template_response`. Test:
    `test_AC_PLT_07_5xx_raised_outside_the_view_is_logged_with_its_type`.
  - **O-2 (opción a):** el evento ya no lleva `exception` (traza con mensaje) sino `exception_type`,
    `exception_chain` (tipos de `__cause__`/`__context__`) y `exception_frames` (`archivo:línea in función`, hasta
    30), nunca el mensaje ni los args: mismo criterio que `health.not_ready`. Test:
    `test_AC_PLT_07_exception_message_never_logged` (token en query, `redis://:<centinela>@`, path y
    `input_value` encadenados).
  - **N-b / N-c:** documentado en `access_log.py` que los redirects de `SecurityMiddleware` (antes del access log)
    no aparecen, y que `route=<unmatched>` también cuando un middleware corta o falla antes de resolver la URL.
- **Notas de implementación:** evento `http.request`; `route` es `resolver_match.route` o `<unmatched>`; `/healthz`
  y `/readyz` siempre en DEBUG (un `/readyz` 503 ya deja `WARNING health.not_ready`), ERROR desde 500, INFO el
  resto. `duration_ms` redondeado a 2 decimales. Test agregado: `test_AC_PLT_07_health_requests_shown_at_debug_level`.
- **Desvío de alcance:** además de lo listado se tocaron `apps/common/logging/setup.py` (silenciamiento, ver N-1) y
  los dos tests de T-PLT-12 de arriba.

### T-PLT-14 — Redacción de secretos en logs
- **AC:** AC-PLT-08. RN-PLT-06 (C-06). **Zona roja:** no (reviewer recomendado).
- **Archivos:** `backend/apps/common/domain/redaction.py` (recursiva, claves de §3.2.3),
  `backend/apps/common/logging/processors.py` (procesador de redacción), `backend/tests/logging/test_AC_PLT_08_redaction.py`.
- **Plan de pruebas:** `test_AC_PLT_08_bearer_cookie_and_query_never_logged` (request con `Authorization: Bearer
  <centinela>`, `Cookie`, query string a ruta con parámetro; ningún centinela en stdout),
  `test_AC_PLT_08_access_log_shows_route_template_not_raw_path`, `test_AC_PLT_08_redacts_nested_secret_like_keys`.
- **Pendientes de la revisión de T-PLT-12 (entran en esta tarea):**
  - **N-2:** `StdoutHandler.handleError` propio que emita una línea JSON fija (sin `record.msg` ni args) en vez de
    la traza de texto de `logging` a stderr; test con un dict circular en un evento.
  - **N-3:** redacción por clave en **ambos** caminos: `extra=` de loggers stdlib y kwargs de structlog, incluidos
    objetos (p. ej. un `request` pasado como kwarg, cuyo `repr` trae el path crudo).
  - **N-4:** `JSONRenderer` con `allow_nan=False` (o normalizar floats no finitos): `NaN`/`Infinity` no son JSON
    válido.
  - **N-5:** `CredentialSafeReporterFilter` también para claves `*URI` (además de `*URL`, `LOCATION`, `DSN`).
  - (de T-PLT-12) la redacción de eventos debe cubrir `location` y URLs con `user:password`, y revisar
    `django.db.backends` en `DEBUG` (SQL con parámetros).
- **Pendiente de la re-revisión de T-PLT-13 (N-3):** `describe_exception` lista los frames solo de la excepción
  externa; los de `__cause__`/`__context__` (solo sus tipos van en `exception_chain`) quedan para esta tarea.
- **Hecho (commits `feat(platform): redact secrets in every log event` y `fix(platform): log safety follow-ups
  from T-PLT-12/13 reviews`):**
  - **AC-PLT-08:** `domain/redaction.py` (puro, mypy strict) redacta por clave las de §3.2.3 más `location` y
    `proxy-authorization`, comparadas sin mayúsculas, `-` ni `_` y también en forma WSGI (`HTTP_AUTHORIZATION`);
    en todo string (mensaje y traza incluidos) quita `user:password@`, query string y fragmento de las URLs, el
    valor de `<clave secreta>=valor` y la credencial de `Bearer`. Lo que no es JSON se vuelve JSON sin `repr`:
    `UUID`/`Decimal` como texto, fechas ISO, `NaN`/`Infinity` como strings, el resto `"<Tipo>"` (un `request`
    pasado como kwarg sale `"<WSGIRequest>"`); ciclos → `"[CIRCULAR]"`, más de 10 niveles → `"[TRUNCATED]"`.
    `processors.redact_event` corre para structlog y stdlib (N-3: los `extra=` escalares también). Tests:
    `test_AC_PLT_08_bearer_cookie_and_query_never_logged` (vista "descuidada" que loguea el request, sus headers
    y el token por los dos caminos), `test_AC_PLT_08_access_log_shows_route_template_not_raw_path`,
    `test_AC_PLT_08_redacts_nested_secret_like_keys`, `test_AC_PLT_08_location_and_url_credentials_are_redacted`,
    `test_AC_PLT_08_traceback_text_is_redacted_too` y los unitarios de `test_AC_PLT_08_redaction_domain.py`.
  - **N-2:** `StdoutHandler.handleError` escribe una línea JSON fija `log.render_failed` (`failed_component`,
    `failed_level`, `error_type`, `request_id` si hay) sin `msg`, args ni mensaje del error. Tests en
    `test_RN_PLT_05_render_failures.py` (args `%d` mal pasados, formatter que falla con un secreto en el mensaje,
    dict circular, y un subproceso sin pytest: nada en stderr y el log sigue).
  - **N-4:** normalización en la redacción + `JSONRenderer(allow_nan=False)` de respaldo. Tests:
    `test_RN_PLT_05_non_finite_floats_render_as_strict_json`, `…_renderer_rejects_non_finite_floats_as_a_backstop`.
  - **N-5:** `CredentialSafeReporterFilter` oculta también `…URI`. Test: `test_C_06_error_report_hides_uri_settings_and_meta`.
  - **`django.db.backends`:** fijado en INFO en `logging_config()` (con `DEBUG` loguea cada SQL con sus parámetros
    en mensaje y `extra`); sus ERROR siguen saliendo. Tests: `test_AC_PLT_08_sql_debug_log_is_never_emitted` y
    `test_AC_PLT_08_real_query_parameters_never_logged` (integration, Postgres real con `force_debug_cursor`).
  - **N-3 de T-PLT-13:** nuevo campo `exception_chain_frames` (una lista de frames por causa, paralela a
    `exception_chain`, hasta `MAX_FRAMES` cada una). Tests: `test_AC_PLT_07_frames_of_each_cause_are_logged`,
    `test_AC_PLT_07_chain_frames_follow_the_capped_chain`.
  - **Revisión de `41651f0` (pedido del coordinador):** `_short_path` no lanza sin settings de Django (script,
    Celery antes de `setup`): devuelve solo el nombre del archivo; los frames de la stdlib se recortan contra
    `sysconfig.get_paths()["stdlib"]` (`logging/__init__.py`, no `__init__.py`). Tests:
    `test_AC_PLT_07_frames_outside_django_settings_are_file_names`, `test_AC_PLT_07_stdlib_frames_keep_their_package`.
- **Ampliado tras la revisión de T-PLT-14 (sobre `e127f6e`):**
  - **B-1 (ReDoS):** `_SECRET_PAIR` y `_URL` eran cuadráticas (`"a"*10_000` 3,6 s; un `Host` de 8000 letras 9,5 s
    dentro de `Handler.emit`, con el lock tomado). Ahora toda regex arranca con lookbehind y acota sus repeticiones
    salvo la última (greedy, sin backtracking), y cada string se corta a 8192 caracteres antes de las regex (la
    tira sin blancos que cruza el corte se descarta entera, sufijo `[TRUNCATED]`). Tests en
    `test_AC_PLT_08_redaction_performance.py`: 100k caracteres hostiles, las mismas regex sobre strings justo
    debajo del corte (el corte solo taparía una regex cuadrática) y una request con `Host` enorme de punta a
    punta; presupuesto 250 ms (mejor de 3) contra < 30 ms medidos, holgado para CI. Mutación: volver a las regex
    sin acotar hace fallar `…_patterns_are_linear_even_without_the_cut`.
  - **N-2 (falsos negativos):** separador `:` o `=` con espacios y comillas (`{"access_token": "x"}`,
    `{'password': 'x'}`, `token: x`, `X-Api-Key: v`, `password = x`), conservando el esquema
    (`Authorization: Bearer/Basic/Token x`); `Basic <cred>` como `Bearer`; claves `private_key`, `session`
    (`sessionid`), `jwt` y `auth` exacta (en campos y en texto; en texto también `authorization` y `cookie`
    enteras). Test: `test_AC_PLT_08_text_loses_quoted_and_colon_separated_secrets` y casos de claves.
    **No** se agregaron los patrones de tokens de Mercado Pago (`APP_USR-…`, `TEST-…`, `TG-…`): un patrón
    específico de un proveedor en `apps/common` viola C-09. Pregunta abierta para el planner: un registro
    genérico de patrones en `domain/redaction.py` que el adaptador de MP complete desde
    `integrations/providers/mercadopago/` cuando exista (módulo de integraciones). El repo solo confirma los
    prefijos `APP_USR-`/`TEST-` (`context/09`, `context/03`); la forma completa no está documentada.
  - **N-1:** `logging.captureWarnings(True)` en `configure_logging`. Test en subproceso:
    `test_AC_PLT_08_python_warnings_are_json_and_redacted`.
  - **N-3:** comentario en `SQL_LOGGERS`: el nivel INFO también corta `django.db.backends.schema` (DDL en DEBUG).
  - **B-2:** `design.md §3.2.3` reescrito con el orden, las claves, las reglas de texto, el corte y
    `captureWarnings`; spec 1.0.3 (sin cambios en RN/RF/AC).
- **Orden de procesadores:** la redacción corre **después** de `format_exc_info`: así la traza renderizada
  (`exception`) también se limpia, y `exc_info` (una tupla de excepción) no pasa por la redacción. Reflejado en
  `design.md §3.2.3` (spec 1.0.3).
- **Desvío de alcance (registrado):** además de los tres archivos listados se tocaron `apps/common/logging/setup.py`
  (procesador en la cadena, N-2, N-4, `django.db.backends`), `apps/common/logging/report_filter.py` (N-5),
  `apps/common/middleware/access_log.py` (N-3 de T-PLT-13 y los dos puntos de la revisión de `41651f0`),
  `backend/tests/logging/test_AC_PLT_07_access_log_json.py` (sus tests) y se crearon
  `test_AC_PLT_08_redaction_domain.py`, `test_AC_PLT_08_sql_and_reports.py` y `test_RN_PLT_05_render_failures.py`
  (separados por tema para no pasar de ~400 líneas); tras la revisión, `test_AC_PLT_08_redaction_performance.py`,
  `design.md` y `spec.sdd.md` (B-2). Todos son pendientes que esta sección asigna a T-PLT-14 o que pidió la revisión.
- **Re-revisión de `6d1c03a`: APROBADO.** No bloqueantes que quedan para una tarea posterior de endurecimiento de la
  redacción (no entran en este PR):
  1. Valor entre comillas con blancos: `{"password": "abc SEKRIT"}` → `"[REDACTED] SEKRIT"`; si se abrió comilla,
     redactar hasta la comilla de cierre.
  2. Huecos de las cotas lineales: prefijo de más de 64 caracteres antes de la parte de clave
     (`"a"*65+"_token=x"`), más de 8 blancos alrededor del separador o más de 16 tras `Bearer`/`Basic`. Documentar
     como límite en `design.md §3.2.3` o con un test.
  3. Línea de header con varios segmentos: `Cookie: a=1; mp_auth=x` y `Authorization: Digest … response="x"`
     dejan en claro lo que sigue al primer segmento.
  4. JSON escapado (`{\"token\": \"x\"}`) y XML (`<token>x</token>`) no se reconocen.
  5. Cosmético: `basic setup failed` → `basic [REDACTED] failed`; `(token=x)` pierde el `)`. Los warnings emitidos
     antes de `configure_logging` siguen yendo a stderr.

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
- **Pendiente de la re-revisión de T-PLT-13 (N-5):** el access log toma la excepción de `got_request_exception`.
  Si el `EXCEPTION_HANDLER` de DRF (o `handler500`) convierte una excepción genérica en un 500 `problem+json` sin
  que Django la vea como no manejada, tiene que emitir `got_request_exception` dentro del `except` o loguear con
  `apps.common.middleware.access_log.describe_exception`; si no, el evento `http.request` del 500 queda sin
  `exception_*`.
- **Hecho (commits `feat(api)` ×2 y `test(api)`):** `problems.py` puro (`build_problem`,
  `validation_errors`, títulos fijos por `code`; `detail` se descarta en todo 5xx). `exceptions.py`: el
  `EXCEPTION_HANDLER` nunca devuelve `None`; excepción no DRF → `500 internal_error` también con `DEBUG`, y emite
  `got_request_exception` dentro del `except` de DRF (N-5: el access log lleva `exception_*`; mutación verificada).
  `Http404`/`PermissionDenied` de Django pierden su mensaje. `handler404`/`handler500` solo bajo `/api/`.
  Tests extra: `…_drf_errors_have_stable_codes_and_no_exception_message` (403/404/405/406/400/415) y, en
  `test_AC_PLT_34_problems_domain.py` (unitarios del módulo puro),
  `…_validation_errors_flatten_nested_and_non_field_details` y
  `…_any_5xx_drops_detail_and_unknown_codes_get_the_http_phrase`.
- **Desvío de alcance:** `backend/config/urls_dev.py` (ROOT_URLCONF de dev/test) reexporta `handler404`/`handler500`
  (sin eso dev y test no usan los handlers) y se creó `backend/tests/api/test_AC_PLT_34_problems_domain.py` (para
  partir el diff en commits chicos).
- **Preguntas para el planner (decisión conservadora aplicada):** (a) `SuspiciousOperation` dentro de una vista
  DRF sale `500 internal_error` (no hay `code` 400 genérico en §6.2); (b) el 400 de `DisallowedHost` u otro error
  de middleware bajo `/api/` sigue en HTML (sin `handler400`/`handler403`); (c) `validation_error` sin `detail` y
  errores sin campo bajo `non_field_errors`; (d) títulos en español elegidos acá salvo "Datos inválidos" (§6.2);
  código desconocido → frase HTTP en inglés; (e) un cliente que manda solo `Accept: application/problem+json`
  recibe 406 (el renderer es `application/json`).
- **Revisión de `728bce8`: APROBADO.** Las preguntas (a)–(e) se aceptan como están (no contradicen el design: §3.2.4
  pide problem+json "aunque `Accept` no lo pida" y solo nombra `handler404`/`handler500`). No bloqueantes para
  después (no entran en este PR):
  1. Dev con `DEBUG=True`: una ruta desconocida bajo `/api/` muestra la página 404 técnica de Django (HTML, con los
     patrones de URL) y una vista Django pura que falla muestra el 500 con traza, porque Django solo usa
     `handler404`/`handler500` con `DEBUG=False`. Prod no se ve afectado. Opción: `re_path(r"^api/")` comodín al
     final que llame a `not_found`.
  2. mypy: `tests/api/test_AC_PLT_34_problem_json.py:40` tipa el helper con `HttpResponse` y el cliente devuelve
     `_MonkeyPatchedWSGIResponse` (6 errores). Corregir en T-PLT-10 al activar mypy en CI.
  3. `detail` (p. ej. el 415 con el `Content-Type` recibido) y `errors[].message` (valor inválido de un
     `ChoiceField`) reflejan lo que mandó el cliente: el componente `Problem` (T-PLT-18/35) nunca lo renderiza
     como HTML.
  4. `handler400`/`handler403` con la misma lógica `_is_api`, para que `PermissionDenied`, `SuspiciousOperation` y
     `DisallowedHost` bajo `/api/` también salgan en problem+json.
  5. Menores: título de respaldo en inglés (pasarlo a español o exigir título por cada `code` publicado);
     `JsonResponse` y DRF serializan con distinto espaciado. Además: (a) abrir una Q para un código `bad_request`
     400 en §6.2 antes de la spec 01; (c) el ejemplo de §6.2 trae `"detail"` en `validation_error`: alinear
     ejemplo o implementación con entrada en el Historial.

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
- **Hecho (commit `feat(api)`):** `throttling.py`: `HubAnonRateThrottle(AnonRateThrottle)`, `get_rate()` lee
  `settings.API_THROTTLE_ANON_RATE` en cada request; `allow_request` atrapa `RedisError`/`OSError` → deja pasar y
  loguea `WARNING throttle.cache_unavailable` con `scope` y `error_type` (nunca el mensaje, C-06). `Request`/`APIView`
  solo bajo `TYPE_CHECKING`: `rest_framework.views` importa `DEFAULT_THROTTLE_CLASSES` (este módulo) al cargarse.
  `base.py`: `DEFAULT_THROTTLE_CLASSES` y `NUM_PROXIES=0` (el `None` de DRF confiaría en cualquier
  `X-Forwarded-For`); sin `DEFAULT_THROTTLE_RATES` (la tasa se lee en runtime). `env.py`: `API_THROTTLE_ANON_RATE`
  (default `300/min`, `<n≥1>/<s|sec|m|min|h|hour|d|day>`, error `throttle_rate_format`) y `TRUSTED_PROXY_COUNT`
  (int ≥ 0, default 0). `CACHES` ya existía (T-PLT-08: `RedisCache` en dev/prod con `CACHE_KEY_PREFIX="hub"`,
  `LocMemCache` en test): se reusa sin cambios. Tests extra: throttle por defecto de DRF, `X-Forwarded-For`
  falsificado no reinicia la cuenta, default `300/min`, variables inválidas no arrancan. El contrato OpenAPI no
  cambia (`paths: {}`; `--check` en verde). **Scope drift (menor, reportado):** `dev.py` y `prod.py` no estaban en
  la lista pero son los únicos que pueden pasar el entorno validado a settings (base no lee el entorno): +2 líneas
  cada uno (`API_THROTTLE_ANON_RATE`, `REST_FRAMEWORK["NUM_PROXIES"]`), idénticas a `test.py`.
  **Para después:** (1) `.env.example` debe sumar `API_THROTTLE_ANON_RATE` y `TRUSTED_PROXY_COUNT` (T-PLT-39,
  bloqueada por Q-048). (2) `CACHES` de dev/prod no fija `socket_timeout`/`socket_connect_timeout`: con un Redis
  que no rechaza la conexión (host caído sin RST) el fail-open espera el timeout del sistema; conviene acotarlo
  en `OPTIONS` (tarea de settings, fuera de esta lista).
- **Revisión (aprobada, sin bloqueantes). Para después:** N1 = el (2) de arriba, pero como tarea con nombre antes de
  producción, no solo una nota (si no, el fail-open se vuelve "fail-slow"). N2: con Redis caído hay un WARNING por
  request; limitarlo si inunda el log. N3: falta un test con `TRUSTED_PROXY_COUNT>0` (N=1 toma la última IP de
  `X-Forwarded-For`, no la primera); sumarlo cuando 01 defina la clave (§3.2.4). N4: con N>0 el backend no puede
  tener ingreso directo sin pasar por el proxy (si no, el cliente controla `X-Forwarded-For`): documentarlo con el
  hosting (Q-020). N5 (preexistente, T-PLT-15): `Retry-After` redondea `wait` hacia abajo y puede salir `0`;
  redondear hacia arriba.

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
- **Pendiente de la revisión de T-PLT-14:** Celery loguea `Task x[id] raised unexpected: <repr(exc)>` (el mensaje de
  la excepción, que puede traer cualquier cosa) y en algunos caminos args/kwargs dentro del mensaje (logger
  `celery.app.trace`), donde la redacción por clave no llega. Verificar con un test de centinela (excepción y args
  con un secreto, `start_worker`) que `task_failure`/`task_postrun` y `worker_hijack_root_logger=False` dejan solo
  los campos de `celery.task`; si no, silenciar o bajar de nivel esos loggers como `django.request` en T-PLT-13.
- **Hecho (commits `feat(platform)` ×3):** `config/celery.py` (`config_from_object` con `namespace="CELERY"`,
  `autodiscover_tasks`, `setdefault` a `prod` como `wsgi.py`) conecta `setup_logging`: worker y beat aplican
  `settings.LOGGING` y Celery no toca el root, su nivel (`-l`) ni stdout. `base.py`: `CELERY_WORKER_HIJACK_ROOT_LOGGER
  =False`, `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True`, `CELERY_BROKER_CONNECTION_MAX_RETRIES=None`.
  `celery_signals.py`: `before_task_publish` → header `request_id` (solo si hay uno ligado); `task_prerun` lo lee
  (atributo o `headers`), lo valida con `resolve_request_id` y liga `request_id`, `task_id`, `task_name`;
  `task_failure` guarda `describe_exception` (tipos y frames, de `access_log.py`); `task_postrun` emite **un**
  evento `celery.task` con `result` (estado) y `duration_ms` (ERROR si `FAILURE`) y limpia el contexto.
  **Pendiente de T-PLT-14 resuelto:** con el test de centinela el `celery.app.trace` sí filtraba (`raised
  unexpected: RuntimeError('<mensaje>')`, y el valor de retorno en `succeeded in`); va a `SILENCED_LOGGERS` en
  `logging/setup.py` (archivo fuera de la lista, cambio de una línea que pedía este pendiente). Mutación
  verificada: sin silenciarlo fallan el test en proceso y el de `start_worker` (el centinela va en texto plano:
  con forma `secret=` la redacción lo tapaba y el test no probaba el silenciado). `/api/dev/diagnostic-task/`
  (`POST`, 202 `{task_id, request_id}`) solo en `config.urls_dev`. Smoke manual con `celery -A config -q worker
  -P solo`: salida 100 % JSON. Broker caído al encolar: `OperationalError` a los ~4 s (500 problem+json), no
  cuelga.
- **Scope drift resuelto en este PR** (autorizado por el coordinador; commit `fix(platform)`):
  `CELERY_BROKER_URL = str(_env.REDIS_URL.get_secret_value())` en `dev.py`/`test.py`/`prod.py`, con el mismo
  patrón que `CACHES` (`base.py` no tiene `_env`). El design no prevé un broker ni una base de Redis aparte
  (§3.2.2: `REDIS_URL` es "broker de Celery y caché"), así que se usa `REDIS_URL` tal cual. Celery ya no lee
  `CELERY_BROKER_URL` del entorno por su cuenta (AC-PLT-06). **Hallazgo al verificarlo:** con
  `config_from_object("django.conf:settings")` Celery veía **todos** los settings, y su config imprimible
  (`celery report`, `celery inspect conf`) solo enmascara claves tipo `KEY`/`PASS`/`broker_url`: mostraba
  `CACHES["default"]["LOCATION"]` (`REDIS_URL` con contraseña) en claro en dev/prod. Ahora `config/celery.py`
  le pasa un `Mapping` con solo los `CELERY_*` (`CelerySettings`). Test `test_C_06_broker_url_comes_from_redis_url
  _and_never_shows_its_password` (dev/test/prod, en subproceso, centinela en la contraseña): el reporte de error
  (`CredentialSafeReporterFilter`, sección de settings), `repr(settings)`, `conf.humanize()` y `as_uri()` no la
  muestran. El fixture de integración ya no apunta el app a Redis a mano (usa el broker de settings); el de
  `memory://` sigue cambiando el broker.
- **Revisión de `8cd05cb`: CAMBIOS REQUERIDOS, aplicados en el commit `fix(logging)`.** B-1 (C-06): con un
  mensaje que el worker no ejecuta, `celery.worker.consumer.consumer` logueaba el cuerpo entero (args y kwargs,
  `dump_body`): `UNKNOWN_TASK_ERROR`, `INVALID_TASK_ERROR`, `UNKNOWN_FORMAT` y `MESSAGE_DECODE_ERROR`, y
  `celery.worker.strategy` el `req.info(safe=True)` del ETA inconvertible. `logging/celery_filters.py`
  (`CeleryMessageBodyFilter`, en esos dos loggers vía `setup.py`) descarta los tres primeros, comparando con las
  constantes de Celery, y `celery_signals.py` emite `celery.task.rejected` (`reason`, `task_name`, `task_id`;
  `error_type` si es inválido) desde `task_unknown`/`task_rejected`. Los dos que no mandan señal (decode, ETA) se
  reescriben en el mismo evento, sin args ni traza. El resto de esos loggers (`Cannot connect`) pasa. Tests
  con centinela en un arg posicional y en un kwarg de clave inocua: unknown, invalid (ETA mal formado) y unknown
  format con `start_worker`; decode y ETA inconvertible, record a record. Mutación: con el filtro apagado
  fallan 8 tests. NB1: los fixtures sueltan solo el pool (sin `close()`, que desregistraba el app); NB5: test
  que fija que `conf.table()` no ve `CACHES`, `DATABASES` ni `SECRET_KEY`.
- **Verificación de `e54c266`: APROBADA.** Ajuste en el commit `fix(logging)` siguiente: el match del ETA por
  prefijo era frágil (si Celery cambia el texto, vuelven args y kwargs). El filtro pasa a **allowlist**: se
  descartan los tres mensajes con señal; pasan intactas solo `CONNECTION_ERROR` (`Cannot connect`),
  `CONNECTION_RETRY` y `LOG_RECEIVED`; todo lo demás de esos dos loggers pierde args y traza (queda
  `error_type`), y si traía un dict de tarea (`args`/`kwargs`/`argsrepr`/`kwargsrepr`/`body`), `bytes` o es el
  de decode, sale como `celery.task.rejected` con nombre e id. Una constante que falta en Celery se saltea
  (sus records toman el camino seguro) y el filtro nunca lanza (si falla, deja el record sin args). Tests: ETA
  real con `start_worker` (`eta` en overflow `9999-12-31T23:59:59-12:00`, centinela en arg posicional y kwarg
  inocuo), plantilla desconocida con dict de tarea, con `bytes` y con un string, `received` intacto,
  constantes ausentes y falla del filtro.
- **Regresión detectada en la verificación de `624dd7a`, arreglada en `test(logging)`:** desde `8cd05cb` el
  fixture `memory_broker` no cambiaba el broker (Celery lee `CELERY_BROKER_URL` antes que `broker_url` por el
  `namespace`): con Redis levantado publicaba en Redis y sin Redis fallaba. Ahora cambia el setting de Django
  (`settings.CELERY_BROKER_URL`) y fija que el transport del producer sea `memory`. Verificado sin servicios
  (`-m "not integration"`), con servicios y en otros órdenes (archivo solo, integración antes que memoria).
- **Para después:** (1) `describe_exception` vive en `middleware/access_log.py` y ahora lo usa Celery: moverlo a
  `logging/` cuando se toque. (2) `celery.worker.request` (WorkerLost, time limits) y
  `celery.utils.dispatch.signal` (si un receptor falla) loguean el `repr` de excepciones y **sí** pueden aparecer
  (no se probaron con un worker que muere ni con un receptor que falla); no están silenciados ni filtrados.
  (3) Una tarea `apply()` anidada dentro de otra limpia el contexto de la exterior (no hay tareas anidadas en 00).
  (4) Sin result backend: `ignore_result=True` en `diagnostic_ping`; ningún `CELERY_RESULT_BACKEND` en 00. Sin
  throttle en la ruta dev hasta T-PLT-16. (5) Para cambiar de broker los tests vacían `_pool` y el `amqp`
  cacheado del app (lo que hace el reset de Celery tras un fork): frágil si Celery cambia; no hay API pública.
  (6) NB2: silenciar `celery.app.trace` entero también oculta `Process cleanup failed` y `Failed to dispatch
  chain/callbacks`; pasarlo a un filtro como el de B-1. (7) NB3: con WorkerLost o un hard time limit,
  `task_failure` sale en el proceso padre sin `prerun`/`postrun`: la entrada de `_failures` no se borra y no se
  emite `celery.task`. (8) NB4: con `LOG_LEVEL=DEBUG`, `celery.utils.functional` y `celery.bootsteps` meten
  ruido.

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
- **Nota:** ADR-0005 Aceptado (2026-11-02).
- **Hecho (commits `feat(api)` ×3 y `ci(platform)`):** `schema.py` fija todo lo que da forma al contrato
  (`API_VERSION="0.1.0"`, `OAS_VERSION="3.0.3"` explícito, `PUBLIC_URLCONF="config.urls"`, `Problem` y
  `ProblemFieldError` en `APPEND_COMPONENTS`, hook `add_problem_responses` después de `postprocess_schema_enums`:
  `4XX`/`5XX` → `application/problem+json` solo donde la operación no declara ese rango). `detail` y
  `errors[].message` se documentan como texto plano, nunca HTML (pendiente 3 de la revisión de T-PLT-15).
  `export_openapi` envuelve `spectacular` (`--validate --fail-on-warn`, YAML, `lang=LANGUAGE_CODE`) en un temporal;
  `--check` compara bytes, imprime el diff unificado con rutas relativas y sale con 1 sin escribir (también si el
  archivo falta). En 00 `paths: {}`. Determinismo: dos generaciones iguales, LF, sin rutas locales (test); mismo
  SHA-256 en Windows (Python 3.12.0) y en `python:3.12-slim` (`uv sync --frozen`, `TZ=Europe/Madrid`, `LANG=C`) y
  con el dumper YAML en Python puro. `/api/dev/schema/` y `/api/dev/docs/` solo en `urls_dev`; el esquema servido
  sale de `SERVE_URLCONF=config.urls`, o sea es el contrato commiteado (test). Tests extra:
  `test_AC_PLT_23_export_is_deterministic_lf_and_free_of_local_paths`,
  `test_AC_PLT_23_generation_warning_fails_the_export`, `test_Q056_dev_schema_is_the_committed_contract`,
  `test_Q056_dev_docs_render_swagger_ui_on_the_dev_schema`. Mutación: con `PUBLIC_URLCONF="config.urls_dev"`
  fallan 4 tests; sin el hook falla `…_problem_component_on_4xx_5xx`.
- **Desvío de alcance:** `TEMPLATES` (`DjangoTemplates`, `APP_DIRS`) en `base.py` (archivo listado): sin eso
  `/api/dev/docs/` da `TemplateDoesNotExist`. Afecta también a `prod`, que no tiene ninguna vista que renderice
  templates.
- **Preguntas (decisión conservadora aplicada):** (a) `request_id` es requerido pero `nullable` en `Problem`,
  porque `current_request_id()` puede devolver `None` fuera de una request; si se garantiza siempre, se quita el
  `nullable` (cambio menor de contrato). (b) OAS 3.0.3 y no 3.1 (el ADR admite ambas). (c) El `--check` compara
  bytes: un checkout con CRLF fallaría, cosa que `.gitattributes` (`eol=lf`) evita.
- **Para después:** (1) Swagger UI carga `swagger-ui-dist@latest` del CDN (default de drf-spectacular; solo dev):
  fijar versión con `SWAGGER_UI_DIST`. (2) La fila de ADR-0005 en `context/decisions/README.md` no muestra el
  estado. (3) `schema.py`: el `continue` de claves que no son operación (`parameters` de un path) no se ejercita
  hasta que haya paths.
- **Revisión de `fd179d2`: APROBADO.** Preguntas: (a) `request_id` requerido y `nullable` se mantiene (refleja
  `build_problem(request_id: str | None)`); (b) OAS 3.0.3 explícito se mantiene; (c) comparación por bytes se
  mantiene (`eol=lf` ya evita CRLF). Para después:
  1. Swagger UI de dev carga `swagger-ui-dist@latest` y el favicon desde jsDelivr: fijar versión exacta en
     `SWAGGER_UI_DIST`/`SWAGGER_UI_FAVICON_HREF` (`apps/common/api/schema.py:96`, C-13) o usar sidecar.
  2. `TEMPLATES` (`config/settings/base.py:57-59`) también llega a prod sin necesidad: moverlo a `dev.py`/`test.py` o
     testear que prod no tiene rutas que rendericen HTML.
  3. CI genera el contrato con `config.settings.test`: sumar un test que corra `export_openapi --check` con prod
     (`run_django`), por si algo de `config.urls` llega a depender de settings.
  4. `test_AC_PLT_23_check_mode_fails_and_prints_diff_when_outdated` simula "desactualizado" editando el yaml: sumar
     el caso de una vista pública nueva en memoria (como pide el AC).

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
- **Hecho (commits `test(architecture)` ×2 y `ci(platform)`):** `ast_rules.py` analiza por AST `apps/` y `config/`
  (`SourceTree(root, package)`: el árbol `synthetic/` hace de `apps/`). C-09 resuelve `import`/`from` (relativos;
  uno que sube por encima de `apps` es violación), `import_module`/`__import__` (`fromlist`)/`import_string` con
  literales y cadenas de atributos desde un paquete ancestro importado (`from apps.integrations import providers;
  providers.mercadopago`). C-01 marca `.objects`/`._default_manager`/`._base_manager` con cualquier receptor (alias,
  `self.model`), `getattr`/`attrgetter` con literal y `_meta.{default_manager,base_manager,managers,managers_map}`, en
  `apps/<app>/services/**` **y** `apps/<app>/services.py`. `AllowEntry(path, symbol, reason)` ya nace acá (T-PLT-20 la
  reusa): entrada sin motivo o muerta = violación. Job `architecture` (`needs: typecheck`); `tests` pasa a `needs:
  architecture`. Mutación verificada: un import de proveedor en `apps/common/health/checks.py` y un `Thing.objects` en
  `apps/common/services/` rompen los `real_code_has_no_violations`. Tests extra: evasiones parametrizadas,
  `non_provider_imports_pass`, allowlist (válida, sin motivo, muerta) y
  `test_RN_PLT_09_architecture_job_runs_architecture_tests`.
- **Residual (no barato por AST):** imports dinámicos con nombre calculado, `__import__` con `level`, nombres armados
  en runtime (`getattr(M, "obj" + "ects")`, `vars(M)`, `M.__dict__`), alias de un paquete reasignado (`p = providers;
  p.mercadopago`), acceso crudo escondido en un helper fuera de `services/` y `.pyi`.
- **Preguntas para el planner, respondidas en la revisión:** (a) `services/` anidados: sí, cubiertos (NB1). (b) La
  forma `AllowEntry(path, symbol)` de `ALLOWED_TENANT_MANAGERS` queda hasta SPEC-02, que abre una Q en su design.
  (c) `tests/typing/synthetic/` en `norecursedirs`: no hace falta.
- **Revisión de `9e3c937`: APROBADO.** Aplicado en el mismo PR (commit `fix(architecture)`): NB1, C-01 cubre todo
  `services/`/`services.py` debajo de `apps/<app>/` (`"services" in parts[2:]`), salvo rutas con un segmento `tests`
  (`apps/integrations/core/services/a.py` falla, `apps/charges/tests/services/` no); NB3,
  `import_module(".x", __package__)` y `package=__name__` se resuelven desde el nombre del módulo (antes daban
  "relative import that cannot be resolved", falso positivo); NB5, docstring de `ast_rules.py` alineado con los
  residuales. Para después:
  1. NB2: `get_object_or_404`, `get_list_or_404` y `QuerySet(model=…)` en `services/` pasan sin detectarse.
  2. NB4: un módulo compartido bajo `providers/` cuenta como proveedor; por eso el contrato común va en
     `integrations/core/`. Anotarlo para SPEC-03.
  3. Para SPEC-02: `selectors/` puede usar `.objects`. El filtro por organización lo controla el test cross-tenant
     por endpoint, no esta regla.

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
- **Hecho (commit `test(architecture)`):** la regla vive en `backend/tests/architecture/money_rules.py` y no en
  `ast_rules.py` (C-14: este ya tiene 273 líneas). Reusa `iter_sources`, `Violation` y `apply_allowlist` de T-PLT-19.
  `FLOAT_ALLOWLIST` arranca vacía y el símbolo de cada entrada es la expresión (`float(amount)`). Nada bajo
  `apps/integrations/providers/` se chequea.
  - `FloatField` se busca en `models.py` y en `models/`. Cubre `models.FloatField`, un alias (`m.`),
    `django.db.models.FloatField`, la clase base de una subclase y `from django.db.models import FloatField [as F]`.
  - `float` se busca en `domain`, `services`, `selectors` y `api`, sea paquete o módulo suelto y aunque esté anidado.
    Cubre `float(...)`, `builtins.float(...)` (también con `builtins` aliasado), `from builtins import float as f`, y
    `float` pasado o asignado como valor (`map(float, xs)`, `defaultdict(float)`, `to_number = float`).
  - No se marca `float` cuando es un tipo: `isinstance`/`issubclass`, anotaciones, uniones, genéricos y `type`.
    Sin esto, `JsonValue = str | int | float | …` de `apps/common/domain/redaction.py` daba un falso positivo.
  - Mutación verificada: un `FloatField` en `apps/common/models.py` y un `float(x)` en `redaction.py` rompen
    `real_code_has_no_violations`.
  - Tests extra: `floatfield_evasions_detected`, `float_evasions_detected` y `decimal_and_type_checks_pass`.
- **Residual:** literales float y `/` entre enteros, anotaciones `-> float`, un campo float definido en otro módulo y
  usado en un modelo, `serializers.FloatField` en `api/`, JSON parseado a `float` y nombres armados en runtime
  (`getattr(builtins, "float")`).
- **Desvío de alcance:** `money_rules.py` no figura en "Archivos"; se agregó por C-14, a pedido del coordinador.
  El comentario del job `architecture` en `ci.yml` todavía dice "C-02 joins with T-PLT-20". El job corre
  `pytest tests/architecture`, así que ya incluye esta regla; no se tocó porque `ci.yml` no está en la lista.
- **Preguntas para el planner (decisión conservadora aplicada):**
  - (a) ¿También se marcan los literales float y las anotaciones `float`? El design no lo pide y no se agregaron.
  - (b) ¿`serializers.FloatField` en `api/`? No se agregó por la misma razón.
  - (c) La exención es solo `apps/integrations/providers/`, no cualquier carpeta `providers/`; ¿alcanza?
  - (d) Los tests de las apps (`apps/<app>/tests/domain/…`) no se excluyen, a diferencia de C-01; ¿se excluyen?
  - (e) ¿Las migraciones con `FloatField` quedan fuera del chequeo? Hoy sí; el modelo que las origina ya falla.
- **Respuestas de la revisión:**
  - (a) Literales y anotaciones no se marcan: `Decimal(0.21)` ya lo marca ruff `RUF032`.
  - (b) Sí: se aplicó en este PR.
  - (c) Alcanza con exceptuar `apps/integrations/providers/`.
  - (d) Se excluyen, como en C-01: se aplicó en este PR.
  - (e) Las migraciones quedan afuera porque las cubre `makemigrations --check` (T-PLT-22); quedó dicho en el
    docstring de `money_rules.py`.
- **Revisión de `97921fd`: APROBADO.** Aplicado en el mismo PR (commit `fix(architecture)`), cada punto con su test:
  - (b) `FloatField` también en las capas de dinero: `serializers.FloatField` y `forms.FloatField` en `api/`, y
    `from rest_framework.serializers import FloatField`.
  - (d) Las rutas con un segmento `tests` no se chequean (`apps/charges/tests/domain/test_x.py` con `float('1.1')`).
  - NB1: `<alias de builtins>.float` se marca aunque no se llame (`f = builtins.float; f(x)`).
  - NB2: no se marcan `type(x) is float`, `!=`, `==` y `float in kinds` (solo el operando suelto:
    `sum(map(float, xs)) == 0` sigue fallando) ni `case float():`.
  - Docstring de `money_rules.py` alineado: alcance, `tests`, migraciones y residuales.
- **Para después:**
  1. Otros usos como tipo que todavía se marcan: `cast(float, …)`, `NewType`/`TypeVar`, `@register(float)` y las
     tuplas de tipos como la de `apps/common/logging/processors.py:21`. Por ahora alcanza con la allowlist.
  2. El comentario de `ci.yml:89-90` ("C-02 joins with T-PLT-20") quedó desactualizado.
  3. Para SPEC-04: con `COERCE_DECIMAL_TO_STRING=False` o `coerce_to_string=False`, DRF emite floats en el JSON, y
     esta regla no lo detecta.
  4. Uniones (`|`) y subíndices exceptúan todo su subárbol, no solo el operando suelto como `Compare`: un
     `defaultdict(float) | other` pasaría. Es raro, pero se puede alinear con NB2.

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
- **Revisión de `0f9a24a`: APROBADO.** No bloqueantes para una tarea posterior (no entran en este PR):
  1. Fijar con test `[tool.coverage.run]` (`source`, `branch`) de `backend/pyproject.toml`, la ausencia de
     `omit`/`exclude_lines`/`exclude_also`, y `include`/`report` de cada gate: hoy un PR podría achicar lo medido
     sin que falle un test (solo lo frena la revisión).
  2. Test que compare los `.py` versionados de `apps/` y `config/` con las claves del reporte (un directorio sin
     `__init__.py` que nunca se importa quedaría fuera en silencio).
  3. Controlar la aparición de `# pragma: no cover` (hoy hay cero): contarlos o regla de lint.
  4. `scripts/check_coverage.py:144`: dos claves que normalizan igual (`apps\x.py` / `apps/x.py`) se pisan sin
     aviso; lanzar `ReportError` ante duplicados.
  5. El job `coverage` corre `setup` con `uv sync` completo aunque el script es solo stdlib (tiempo de CI).

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
- **Pendiente de la revisión de T-PLT-08:** la imagen `runtime` fija `ENV DJANGO_SETTINGS_MODULE=config.settings.prod`
  para que `manage.py` dentro del contenedor no use dev (N-5).
- **Pendiente de la revisión de T-PLT-14:** el error log de gunicorn (`gunicorn.error`: arranque, workers caídos,
  tracebacks fuera de Django) tiene que usar el mismo `logconfig_dict` (`logging_config()`), para que pase por
  `StdoutHandler`, la redacción y `captureWarnings`; test de centinela con un worker que falla.

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
- **Digests (seguimiento de la revisión de T-PLT-11):** `db` y `redis` usan **el mismo `tag@sha256` que los servicios
  del job `tests` de `ci.yml`** (digest del *index* multi-arquitectura, `docker buildx imagetools inspect <tag>`):
  hoy `postgres:17.11-trixie@sha256:3b0cda93be7c8dba2ed484d19393d93845dc3dafb88973e248ba8e6d99d784e1` (verificado
  2026-11-01; el anterior `31ba9c94…` ya no es el index del tag) y
  `redis:7.4.12-bookworm@sha256:b6b6e3dc0c0952737748e55d5d885272840c7e42ba41ab1d5489f693419882f5`. Si se
  actualiza uno, se actualizan los dos archivos en el mismo commit.
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
  `frontend/pnpm-workspace.yaml` (sumado: pnpm ≥11 lee la política de builds desde ahí; aprobado por el orquestador;
  `allowBuilds: { unrs-resolver: false }`),
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
- **Archivos:** `scripts/audit_deps.py` (pip-audit sobre `uv export --frozen --all-groups` + `pnpm audit`
  aislado; severidad vía OSV; desconocida = alta; excepciones con vencimiento), `scripts/pnpm_isolation.py`
  (argv, directorio y entorno de la corrida aislada de pnpm), `scripts/audit_exceptions.toml` (vacío, formato
  comentado), `scripts/tests/test_AC_PLT_26_audit_deps.py` y `scripts/tests/test_AC_PLT_26_pnpm_audit_isolation.py`
  (OSV y subprocesos mockeados, reloj fijo; fakes en `scripts/tests/audit_deps_fakes.py`),
  `scripts/tests/test_RN_PLT_14_dependabot_and_setup.py`, `.github/actions/setup/action.yml` (inputs
  `frontend-deps` y `backend-deps`; install con `--ignore-scripts --ignore-pnpmfile`; `uv sync --no-config
  --frozen --no-build`), `scripts/audit_tool_requirements.txt` (pip-audit 2.10.1 y su cadena, con hashes; B-3),
  `.github/dependabot.yml` (semanal: `uv` `/backend`, `npm` `/frontend`, `docker` `/backend`, `github-actions`;
  parches agrupados), `.github/workflows/ci.yml` (job `deps-audit`, `needs: file-size`; `typecheck` pasa a `needs:
  [secrets, deps-audit]`).
- **Plan de pruebas:** `test_AC_PLT_26_high_vuln_without_exception_fails`, `test_AC_PLT_26_critical_vuln_fails`,
  `test_AC_PLT_26_expired_exception_fails`, `test_AC_PLT_26_valid_exception_passes`,
  `test_AC_PLT_26_unknown_severity_counts_as_high`, `test_AC_PLT_26_pnpm_high_vuln_fails`,
  `test_RN_PLT_14_dependabot_weekly_for_all_ecosystems`. Tras el review (aislamiento de pnpm, B-1):
  `test_AC_PLT_26_pnpm_audit_sees_only_lockfile_and_reduced_manifest`,
  `test_AC_PLT_26_pnpm_audit_argv_ignores_pnpmfile_and_pins_registry`, `test_AC_PLT_26_pnpm_audit_env_is_allowlisted`,
  `test_AC_PLT_26_pnpm_audit_home_and_xdg_are_empty_dirs_in_the_temp`, `test_AC_PLT_26_pnpm_temp_dir_is_removed`,
  `test_AC_PLT_26_unreadable_frontend_manifest_or_lockfile_exits_2`,
  `test_AC_PLT_26_isolated_pnpm_must_be_the_package_manager_version`,
  `test_AC_PLT_26_pnpm_version_is_checked_with_the_isolated_env`, `test_AC_PLT_26_isolated_env_is_pure`,
  `test_AC_PLT_26_temp_cleanup_errors_do_not_break_the_gate`; sin código del PR antes del gate (B-2):
  `test_AC_PLT_26_deps_audit_job_runs_audit_deps`, `test_AC_PLT_26_frontend_deps_input_gates_only_node_and_install`,
  `test_AC_PLT_26_shared_install_runs_no_scripts_nor_pnpmfile`; sin venv del backend en el gate (B-3):
  `test_AC_PLT_26_backend_deps_input_gates_only_sync_and_path`, `test_AC_PLT_26_shared_backend_sync_builds_nothing`,
  `test_AC_PLT_26_deps_audit_tools_come_pinned_and_hashed_not_from_the_lock`,
  `test_AC_PLT_26_audit_tool_requirements_pin_pip_audit_with_hashes` (y el argv `python -m pip_audit` en
  `test_AC_PLT_26_audits_frozen_lockfiles_of_both_ecosystems`); pip-audit y uv aislados de la config del repo
  (review final, B-4/B-5, N-1..N-3): `test_AC_PLT_26_pip_audit_is_isolated_from_planted_modules`,
  `test_AC_PLT_26_python_install_reads_no_repo_config`, `test_AC_PLT_26_every_uv_call_reads_no_repo_config` (y
  `-I`, el cwd temporal y `uv export --no-config` en `test_AC_PLT_26_audits_frozen_lockfiles_of_both_ecosystems`,
  `--no-cache` en `test_AC_PLT_26_deps_audit_tools_come_pinned_and_hashed_not_from_the_lock`, el cwd de
  `pnpm --version` en `test_RN_PLT_14_setup_checks_pnpm_version_and_skips_cache_on_tags`); y
  `test_AC_PLT_26_pip_audit_skipped_dependency_exits_2`, `test_AC_PLT_26_osv_failure_exits_2_without_traceback`,
  `test_AC_PLT_26_unused_exception_warns`, `test_AC_PLT_26_exception_beyond_90_days_exits_2`.
- **Notas de implementación:**
  - **Cadena:** `secrets` todavía no existe (T-PLT-04), así que `typecheck` queda en `needs: deps-audit`, con el
    comentario de que pasa a `[secrets, deps-audit]` cuando llegue T-PLT-04 (lo verifica
    `test_AC_PLT_20_pipeline_chain.py`).
  - **Reglas de `audit_deps.py`:** pip-audit con `--disable-pip --require-hashes --vulnerability-service osv`
    sobre el export (hasheado) de `uv.lock`; severidad = primer `database_specific.severity` reconocido en OSV
    entre el ID y sus alias (GHSA primero); sin severidad (PYSEC), sin registro (404) o valor no reconocido = alta;
    OSV inalcanzable o con respuesta inválida = error (exit 2). Una dependencia que pip-audit saltea (`skip_reason`)
    = error (exit 2); residual: con `--disable-pip` no se auditan los requisitos cuyo marker no aplica al runner
    Linux. Bloquea `high`/`critical`; `moderate`/`low`/`info` se informan sin fallar (hoy: 1 moderada de
    `minimatch`, dev). Una excepción vale hasta su fecha inclusive (UTC), como máximo a 90 días (si no, exit 2), y
    matchea por ID o alias (en npm solo el GHSA: pnpm 12 no emite `cves`); una vigente que no matchea nada da
    warning; una **vencida** falla aunque la vulnerabilidad ya no esté (design §3.5: "excepción vencida" es causa de
    fallo propia). Salida: 0 ok, 1 hallazgos bloqueantes, 2 error de herramienta, de OSV o de
    `audit_exceptions.toml`.
  - **pnpm aislado (review, B-1):** pnpm 12.16.1 oculta advisories por muchos canales que controla el proyecto:
    `auditConfig`/`auditLevel` en `pnpm-workspace.yaml` (en formas de YAML que un parser de líneas no ve: BOM,
    indentado, `? key`, escapes, `--- {…}`, flujo multilínea), hooks `updateConfig` de `.pnpmfile.cjs`/`.mjs` o
    `pnpmfile:`, `registry` propio (`.npmrc` o workspace), `config.yaml` global y variables `PNPM_*`/`NPM_*`. En vez
    de leer esa config (un primer guard por parser se evadía de 9 formas), la corrida no la ve: un
    `TemporaryDirectory` con solo `pnpm-lock.yaml` tal cual y un `package.json` reducido a `name`, `version`,
    `private` y las cuatro claves de dependencias (sin `pnpm` ni `packageManager`); argv `pnpm audit --json
    --audit-level low --ignore-pnpmfile --registry=https://registry.npmjs.org/`; entorno con allowlist (`PATH`,
    `PATHEXT`, `SYSTEMROOT`, `SYSTEMDRIVE`, `WINDIR`, `COMSPEC`: sin `PNPM_*`/`NPM_*`, `NODE_OPTIONS` ni proxies) y
    `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_{CONFIG,DATA,CACHE}_HOME` y `TMP*` en directorios vacíos
    del temp. Verificado en Docker: pnpm 12 no lee `package.json#pnpm`; con el manifest reducido y el lock original
    no se queja del lockfile; un `pnpm-workspace.yaml` en un directorio padre del temp da
    `ERR_PNPM_AUDIT_NO_LOCKFILE` (exit 2, falla cerrado). Los archivos de config de pnpm son ruta roja (T-PLT-06).
    Dentro de la corrida, `pnpm --version` (mismo cwd y env) tiene que ser exactamente la versión de
    `packageManager` sin `+sha512` (si no, exit 2: shim en `PATH`, corepack eligiendo otra). Los dos
    `TemporaryDirectory` usan `ignore_cleanup_errors=True` (un handle abierto en Windows no rompe el gate).
  - **Sin código del PR antes del gate (review, B-2):** el install compartido de la acción de setup corría
    `postinstall`, el código de nivel superior de `.pnpmfile.cjs` y `readPackage`, que pueden escribir
    `$GITHUB_PATH` o reescribir `scripts/audit_deps.py`. `deps-audit` pasa `frontend-deps: "false"`: solo
    `pnpm/action-setup` (pnpm 12 es un ejecutable nativo, no necesita Node; verificado en Docker sin Node y sin
    `node_modules`) y su chequeo de versión; sin `setup-node` ni `pnpm install`. Además el install compartido
    (resto de los jobs) es `pnpm install --frozen-lockfile --ignore-scripts --ignore-pnpmfile` (ninguna dependencia
    necesita build script: `allowBuilds`).
  - **Sin venv del backend en el gate (review, B-3):** la nota "residual" anterior (que `uv sync --frozen` solo
    construía con `package = true`) estaba mal. Sin tocar `backend/pyproject.toml`, un PR puede sumar 6 líneas a
    `backend/uv.lock` (el paquete raíz depende de `evil`, `source = { directory = "evil" }`) y un `backend/evil/`
    con build backend propio: `uv sync --frozen` lo **ejecuta** (reproducido en Docker por el reviewer), y desde
    ahí escribe `$GITHUB_PATH` o instala un `.pth` que corre en cada arranque del Python del venv, el mismo que
    corría `audit_deps.py` y `pip-audit`: el gate entero se evade. Arreglo: (1) input `backend-deps` de la acción
    (default `"true"`) que condiciona `uv sync` y el paso que pone el venv en `PATH`; `deps-audit` pasa `"false"`
    (setup-uv y `uv python install` siguen). (2) El gate corre en un venv propio (`$RUNNER_TEMP/audit-tools`):
    `uv venv --no-config --no-project --python 3.12.16` + `uv pip install --no-config --require-hashes --no-build
    -r scripts/audit_tool_requirements.txt` (pip-audit 2.10.1 y sus 28 dependencias, cada archivo con hash, las
    mismas versiones que fijaba `uv.lock`; cómo regenerarlo está en su cabecera). Su Python ejecuta
    `audit_deps.py`, que llama a pip-audit como `sys.executable -m pip_audit` (no el primero del `PATH`).
    Elegida la opción (b) y no `uvx --from pip-audit==2.10.1`, porque esta última resuelve las ~28 dependencias
    transitivas en cada corrida sin hashes: una release nueva comprometida de cualquiera de ellas entraría al
    gate sin pasar por un PR. `--no-config` evita que un `uv.toml`/`[tool.uv]` del PR cambie índices o fuentes.
    `uv export --frozen` no construye nada (verificado en Docker con el lock alterado: emite `./evil` sin
    ejecutar el backend); pip-audit rechaza ese requisito ("does not contain a hash") y el gate falla cerrado
    con exit 2. (3) Defensa en profundidad para el resto de los jobs: `uv sync --frozen --no-build` (con el
    lock real instala 84 paquetes, exit 0; con el alterado, exit 2 sin ejecutar nada). Ruta roja sugerida para
    T-PLT-06: `backend/uv.lock` y los directorios y archivos nuevos bajo `backend/`. La caché de uv que
    restaura setup-uv **no** quedaba mitigada por "un PR solo escribe la caché de su propia rama": el gate
    corre justamente en esa rama, y otros jobs del mismo run (que sí ejecutan código del PR) pueden haberla
    escrito; un archivo de la caché adulterado se instalaba sin volver a chequear el hash (reproducido por el
    reviewer). Resuelto en el review final (N-1): el install de herramientas va con `--no-cache`.
  - **pip-audit y uv aislados de la config del repo (review final, B-4/B-5):** (B-4) `python -m pip_audit` con
    cwd `backend/` ponía el cwd primero en `sys.path`: un `backend/pip_audit.py` (o `backend/rich.py`, una
    dependencia de pip-audit) plantado imprimía un reporte vacío y el gate pasaba de exit 1 a exit 0. Arreglo:
    `PIP_AUDIT = (sys.executable, "-I", "-m", "pip_audit")` (`-I`: ni el cwd ni `PYTHON*` entran a `sys.path`)
    y pip-audit corre con cwd en el `TemporaryDirectory` del export (ruta absoluta), no en `backend/`.
    (B-5) `uv python install 3.12.16` en la raíz leía un `/uv.toml` o `[tool.uv]` de `/pyproject.toml` del PR:
    con `python-downloads-json-url` instalaba un CPython alterado (un `sitecustomize.py` que corría en cada
    arranque), base del venv de herramientas que corre el gate. Arreglo: `uv python install --no-config`; además
    todas las llamadas a `uv` de `action.yml` y `ci.yml` llevan `--no-config` (las fija un test) y el job
    `deps-audit` define `UV_NO_CONFIG: "1"`, que cubre también las llamadas propias de setup-uv (el `uv cache
    prune` del post-step). El `uv sync` de los demás jobs también lleva `--no-config`: verificado en Docker que
    `package = false` de `backend/pyproject.toml` se sigue respetando (es metadata del proyecto, no un
    setting): con un `[build-system]` agregado y `--no-build`, `uv sync --no-config` no intenta construir el
    proyecto; con el lock real instala 84 paquetes, exit 0, sin el proyecto. Defensas en profundidad del
    review final: (N-1) `--no-cache` en el install de herramientas (arriba); (N-2) `uv export --no-config`
    (con el lock real el export es idéntico salvo la línea de comando del encabezado: 85 pines, DRF 3.16.1);
    (N-3) `pnpm --version` del chequeo de `packageManager` corre en `$RUNNER_TEMP`, no en la raíz (con un
    `/package.json` `pnpm@10.0.0`, en la raíz responde 10.0.0 y en `$RUNNER_TEMP` 12.16.1). Verificado en
    Docker (uv 0.13.6, pnpm 12.16.1, OSV real, 2026-11-02): el job con `backend/pip_audit.py` o
    `backend/rich.py` plantado sigue dando exit 1 por las 3 altas de DRF; con `/uv.toml` o `/pyproject.toml`
    apuntando a un CPython alterado se instala el oficial, el `sitecustomize` no corre y el gate da exit 1 (el
    paso viejo sin `--no-config` sí instalaba el alterado); con la caché de uv adulterada, el install sin
    `--no-cache` copiaba el `_cli.py` modificado y con `--no-cache` el original.
  - **No bloqueantes del review (anotados, sin implementar):** N-2: el test de limpieza del temp depende de la
    firma `onexc` de `shutil.rmtree`, que existe desde Python 3.12 (el proyecto fija 3.12). N-3:
    `check_pnpm_version` muestra en el log hasta 40 caracteres del stdout del binario de pnpm.
  - **Dependabot:** `docker` cubre `/backend` y `/frontend` (design §3.5 dice "ambos Dockerfiles"; llegan con
    T-PLT-25 y T-PLT-36), `github-actions` cubre `/` y `/.github/actions/*` (la acción compuesta). Grupos solo de
    parches; menores y mayores en PRs separados.
  - **Follow-ups del review de T-PLT-27** (resueltos acá, `.github/actions/setup/action.yml` y
    `.github/dependabot.yml`): (a) paso `Check pnpm matches packageManager`: `pnpm --version` tiene que ser
    exactamente la versión de `packageManager` (12.16.1), porque `pnpm/action-setup` descarta el `+sha512`;
    (b) sin caché de pnpm en pushes de tags `v*` (como `enable-cache: auto` de setup-uv) con
    `cache: ${{ !startsWith(github.ref, 'refs/tags/') && 'pnpm' || '' }}` — la forma sugerida
    `startsWith(...) && '' || 'pnpm'` siempre da `'pnpm'` porque `''` es falsy; actionlint 1.7.7 tipa la
    expresión en un workflow de prueba con `setup-node`; (c) `dependabot.yml` ignora la mayor 10 de `eslint`
    (9.x en *maintenance*/deprecado; `eslint-plugin-import` 2.32.0, `eslint-plugin-jsx-a11y` 6.10.2 y
    `eslint-plugin-react` 7.37.5 limitan el peer a `^9`).
  - **Corrida real (2026-11-01, Docker, uv 0.13.6 + pip-audit 2.10.1 + OSV real):** el gate **falla** hoy:
    `djangorestframework` 3.16.1 tiene 3 vulnerabilidades **altas** (GHSA-33wh-fxxf-88vv, GHSA-3547-9m27-7rxg,
    GHSA-xw6w-gcfp-cf8m; arregladas en 3.18.2) y 2 moderadas (arregladas en 3.17.2). Subir DRF choca con Q-059
    (según Q-059, los stubs de DRF 3.18 exigen `django-stubs` ≥ 6.1, pensado para Django 6.1). **Decidido:** DRF
    3.16.1 → 3.18.2 en la rama de T-PLT-13 (Q-059, revisión 2026-11-01), sin excepciones en
    `audit_exceptions.toml`; ese cambio tiene que llegar a `main` **antes** que T-PLT-28 (en esta rama el gate da
    exit 1, a propósito).
- **Verificación de `9dc4c25`: APROBADO** (B-1 a B-5 cerrados, sin regresiones; reproducido en Docker con todo lo
  plantado a la vez). No bloqueantes para después:
  1. El exit 2 con un requisito sin hash (`./evil`) arranca con "pip-audit gave no JSON report: WARNING…": que
     nombre el requisito rechazado.
  2. El comentario de `.github/actions/setup/action.yml` sobre `package = false` ("checked in Docker"): aclarar que
     con `--frozen` lo que decide es la fuente `virtual` del lock (`source = { virtual = "." }`), no la setting.
  3. Dependabot no mantiene `scripts/audit_tool_requirements.txt`: sumar el ecosistema `pip` en `/scripts` (o
     regenerarlo a mano con el comando de su cabecera).

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
  Importar `AppRouterCacheProvider` desde `@mui/material-nextjs/v16-appRouter` (el paquete 9.5.0 exporta subpaths
  explícitos, no `./*`; corrige design §3.3.1).
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
- **AC:** AC-PLT-10 (robustez del reenvío). RN-PLT-16, RF-PLT-06 (Q-061). **Zona roja:** no (reviewer recomendado).
- **Archivos:** `frontend/src/lib/server/backend-proxy.ts` (rechaza `..`, `\`, `%2f`, `%5c` → `400 bff.bad_path`;
  mismo origen; timeout 30 s → `504 bff.upstream_timeout`; caído → `502 bff.upstream_unavailable`; siempre
  `problem+json` con `X-Request-ID`), `frontend/src/lib/server/backend-proxy.errors.test.ts`.
- **Ampliado tras revisión de T-PLT-33** (hallazgos del reviewer, decididos por el orquestador):
  - Rutas: además de la lista negra, se valida la **URL ya resuelta** (`target.origin === base.origin` y
    `target.pathname.startsWith("/api/")`); se rechazan segmentos vacíos, `.`/`..` también codificados (`%2e`,
    `.%2E`, `%2E%2E`) y con doble encoding (`%252e`, `%252f`, `%255c`), backslash, `%2f`/`%5c`, caracteres de
    control y percent-encoding mal formado; cada segmento pasa por `encodeURIComponent` (un `#`/`?` decodificado no
    recorta el path). Todo rechazo → `400 bff.bad_path`.
  - Body: `content-length` se reenvía **solo si son dígitos** (sin él undici manda `Transfer-Encoding: chunked` y
    Django/gunicorn leen el body vacío).
  - Barra final (Q-061): el BFF conserva la del request original y `frontend/next.config.ts` pone
    `skipTrailingSlashRedirect: true` (archivo adicional de esta tarea).
  - `X-Request-ID` válido se normaliza a minúsculas (`request-id.ts`; nota en T-PLT-12).
  - Errores: falta/invalidez de `BACKEND_INTERNAL_URL` → `502 bff.upstream_unavailable` sin revelar el valor;
    `signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)])`; la línea de log JSON se escribe
    también en errores (con `code`); `log.ts` documenta que `duration_ms` mide hasta los headers de la respuesta.
  - Archivos tocados además: `frontend/src/lib/server/{request-id,log}.ts`,
    `frontend/src/lib/server/{backend-proxy,request-id}.test.ts` (allowlist con `content-length`, `duplex: "half"`,
    `cache: "no-store"`, id en minúsculas), `specs/00-platform/{design,clarifications}.md`.
- **Plan de pruebas:** `test_RN_PLT_16_bff_rejects_dotdot_and_encoded_separators`,
  `test_RN_PLT_16_bff_rejects_cross_origin_target`, `test_RF_PLT_06_bff_upstream_down_returns_502_problem`,
  `test_RF_PLT_06_bff_timeout_returns_504_problem`; agregados tras la revisión de T-PLT-33:
  `test_RN_PLT_16_bff_encodes_each_segment_and_keeps_backend_origin`, `test_RN_PLT_16_bff_keeps_trailing_slash`,
  `test_RN_PLT_16_bff_forwards_content_length_and_body_intact` (backend HTTP real en `127.0.0.1`),
  `test_RF_PLT_06_bff_aborts_upstream_when_browser_disconnects`.
- **Ajustes tras revisión de T-PLT-34** (reviewer: aprobado con observaciones): `%` literal aceptado (solo el path
  crudo mal codificado es `bad_path`), body chunked o con `content-length` no numérico → `411 bff.length_required`
  (sin `content-length` ni `transfer-encoding` no hay body: un DELETE sin cuerpo pasa), `reason`
  del 502 solo en el log (`client_abort` como `info`), surrogate suelto → `400`, comentario del test de query
  (se conserva la semántica, no los bytes). `spec.sdd.md` → 1.0.7 (historial; era 1.0.2, renumerada al mergear después de la línea backend). Tests nuevos:
  `test_RN_PLT_16_bff_rejects_malformed_encoding_in_the_raw_path`,
  `test_RN_PLT_16_bff_body_without_content_length_returns_411_problem`. Por `C-14` (el archivo de errores llegaba a
  399 líneas) los tests se parten por AC: `backend-proxy.paths.test.ts` (RN-PLT-16, rutas),
  `backend-proxy.errors.test.ts` (body/411 y RF-PLT-06) y `backend-proxy.test-helpers.ts` (setup compartido).

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
  `WATCHPACK_POLLING`), `scripts/tests/test_AC_PLT_25_dockerfiles.py`,
  `scripts/tests/test_RF_PLT_02_compose_dev.py`. Nota: pnpm 12 usa `pnpm_config_store_dir` (ignora
  `npm_config_store_dir`); sin eso crea `.pnpm-store/` en el bind mount. El `docker` `/frontend` de
  `.github/dependabot.yml` ya lo agregó T-PLT-28. El `pnpm install` del Dockerfile usa las mismas flags que el
  install de CI: `--frozen-lockfile --ignore-scripts --ignore-pnpmfile` (review de T-PLT-28, B-2).
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
