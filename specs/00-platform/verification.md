---
spec: SPEC-00
fecha: 2026-11-06
resultado: Con hallazgos     # Aprobada | Con hallazgos | Rechazada
verificado_por: project-steward (cobertura) + qa-verifier (ejecución pendiente)
version_spec: 1.0.11
---

# Verificación — Módulo de Plataforma (SPEC-00)

## 0. Alcance y método

- Spec verificada: `specs/00-platform/spec.sdd.md` v1.0.11 (`Approved`), la de `main` en `1cc858e`. Las versiones
  siguientes no cambian AC: 1.0.12 solo suma una nota de diseño y
  corrige citas.
- Tareas: `specs/00-platform/tasks.md` (estado conciliado con git el 2026-11-06).
- Método: matriz AC→test sobre el árbol real, revisión de la cadena de CI y checklist manual.
- **Leyenda de la columna “Cobertura”:** `✔` el AC tiene al menos un test con su ID y cubre el criterio completo;
  `⚠` cobertura parcial (el test existe pero no prueba todo el AC); `✘` sin test o tarea pendiente.
- **Este documento no declara tests en verde sin ejecutarlos.** Que un archivo exista no basta para `Verified`:
  la ejecución real se registra en §2 y la firma final la da el dueño.

## 1. Matriz AC → test

| AC | Test(s) | Cobertura |
|---|---|---|
| AC-PLT-01 | `scripts/tests/test_RF_PLT_02_compose_dev.py` (estático, con el servicio `frontend`), `backend/tests/config/test_AC_PLT_05_env_example_parity.py` (`test_AC_PLT_01_every_compose_variable_is_in_env_example`, `test_AC_PLT_01_allowed_hosts_keep_localhost_and_backend`, estáticos) | ⚠ parcial: falta el smoke con `up --wait` real (T-PLT-38) y la verificación manual de §4 |
| AC-PLT-02 | `backend/tests/health/test_AC_PLT_02_readyz.py` | ✔ |
| AC-PLT-03 | `backend/tests/config/test_AC_PLT_03_missing_required_var.py` | ✔ |
| AC-PLT-04 | `backend/tests/config/test_AC_PLT_04_check_deploy.py` | ✔ |
| AC-PLT-05 | `backend/tests/config/test_AC_PLT_05_env_example_parity.py` | ✔ (paridad en los dos sentidos) |
| AC-PLT-06 | `backend/tests/config/test_AC_PLT_06_no_provider_env.py`, `backend/tests/config/test_C_06_celery_broker_url.py` | ✔ (`test_AC_PLT_06_no_setting_matches_spike_keys` cubre las claves de `spikes/env.example`) |
| AC-PLT-07 | `backend/tests/logging/test_AC_PLT_07_access_log_json.py` | ✔ |
| AC-PLT-08 | `backend/tests/logging/test_AC_PLT_08_redaction.py`, `…_redaction_domain.py`, `…_redaction_performance.py`, `…_sql_and_reports.py` | ✔ |
| AC-PLT-09 | `backend/tests/logging/test_AC_PLT_09_request_id.py`, `frontend/src/lib/server/request-id.test.ts`, `frontend/src/lib/server/backend-proxy.test.ts` | ✔ |
| AC-PLT-10 | `frontend/src/lib/server/backend-proxy.test.ts`, `backend-proxy.errors.test.ts`, `backend-proxy.paths.test.ts` | ✔ |
| AC-PLT-11 | `backend/tests/logging/test_AC_PLT_11_celery_task_log.py`, `…_celery_rejected_messages.py` | ✔ |
| AC-PLT-12 | `scripts/tests/test_AC_PLT_12_ruff_print.py` | ✔ |
| AC-PLT-13 | `scripts/tests/test_AC_PLT_13_check_file_size.py`, `test_AC_PLT_20_pipeline_chain.py`, `test_AC_PLT_27_line_endings.py` | ✔ |
| AC-PLT-14 | `backend/tests/architecture/test_AC_PLT_14_adapter_boundary.py` | ✔ |
| AC-PLT-15 | `backend/tests/architecture/test_AC_PLT_15_no_raw_objects_in_services.py` | ✔ |
| AC-PLT-16 | `backend/tests/migrations/test_AC_PLT_16_missing_migration.py` | ✔ |
| AC-PLT-17 | `backend/tests/migrations/test_AC_PLT_17_reversibility.py`, `scripts/tests/test_AC_PLT_20_pipeline_chain.py` (`test_AC_PLT_17_migrations_job_runs_roundtrip_last`) | ✔ (reglas de `RunPython`/`RunSQL`, ida y vuelta en BD descartable y paso `check_migrations_roundtrip` del job `migrations`) |
| AC-PLT-18 | `backend/tests/migrations/test_AC_PLT_18_names_and_mixing.py` | ✔ |
| AC-PLT-19 | `scripts/tests/test_AC_PLT_19_gitleaks.py`, `…_gitleaks_evasions.py`, `…_secrets_job.py` | ✔ |
| AC-PLT-20 | `scripts/tests/test_AC_PLT_20_pipeline_chain.py` | ⚠ (cadena; la completan T-PLT-37 y T-PLT-40) |
| AC-PLT-21 | `backend/tests/typing/test_AC_PLT_21_mypy_strict.py`, `scripts/tests/test_AC_PLT_21_tsconfig_strict.py` | ✔ |
| AC-PLT-22 | `scripts/tests/test_AC_PLT_22_check_coverage.py` | ✔ |
| AC-PLT-23 | `backend/tests/contract/test_AC_PLT_23_openapi_up_to_date.py`, `frontend/src/lib/problem.test.ts` | ✔ |
| AC-PLT-24 | — | ✘ sin test: falta el ruleset (T-PLT-40) |
| AC-PLT-25 | `scripts/tests/test_AC_PLT_25_dockerfiles.py` | ⚠ parcial: chequeo estático de las dos imágenes; falta el build real con etiqueta por SHA (T-PLT-37) |
| AC-PLT-26 | `scripts/tests/test_AC_PLT_26_audit_deps.py`, `…_pnpm_audit_isolation.py` | ✔ |
| AC-PLT-27 | `scripts/tests/test_AC_PLT_27_line_endings.py` | ✔ |
| AC-PLT-28 | `frontend/src/components/shell/AppShell.test.tsx`, `frontend/src/components/EmptyState.test.tsx`, `ErrorNotice.test.tsx`, `frontend/src/modules/home/components/HomeEmpty.test.tsx`, `frontend/src/modules/settings/components/SettingsSectionList.test.tsx` | ✔ |
| AC-PLT-29 | `frontend/scripts/check-client-bundle.test.ts`, `scripts/tests/test_AC_PLT_25_dockerfiles.py` (`test_AC_PLT_29_builder_checks_the_bundle_built_with_sentinels`) | ⚠ parcial: los tests usan builds simulados y leen el Dockerfile. El chequeo sobre el bundle real corre en el stage `builder`, que CI todavía no construye (T-PLT-37); las páginas dinámicas quedan para el smoke (T-PLT-38); límites en `design.md §3.3.3` |
| AC-PLT-30 | `backend/tests/api/test_AC_PLT_30_throttle_429.py` | ✔ |
| AC-PLT-31 | `backend/tests/architecture/test_AC_PLT_31_no_float_money.py` | ✔ |
| AC-PLT-32 | `scripts/tests/test_AC_PLT_32_zona_roja_rules.py` | ⚠ parcial: reglas puras probadas; en `main` no hay `main()` ni workflow, así que el check no corre en los PR (T-PLT-07, PR #48 abierto) |
| AC-PLT-33 | `scripts/tests/test_AC_PLT_33_check_workflows.py`, `scripts/tests/test_AC_PLT_33_check_workflows_refs.py` | ✔ (incluye `test_AC_PLT_33_lint_job_runs_check_workflows`: el job `lint` lo ejecuta) |
| AC-PLT-34 | `backend/tests/api/test_AC_PLT_34_problem_json.py`, `…_problems_domain.py` | ✔ |

**Resumen:** 28 ✔ · 5 ⚠ · 1 ✘ · 34 AC.

## 2. Ejecución de la suite

| Suite | Comando | Estado |
|---|---|---|
| Pipeline en `main` | workflow `ci` en cada push a `main` (9 jobs: `lint`, `file-size`, `secrets`, `deps-audit`, `typecheck`, `architecture`, `tests`, `coverage`, `migrations`) | ✔ 9/9 jobs, run `42160113167` sobre `1cc858e`, 2026-11-06 |
| Backend completo, con PostgreSQL y Redis reales | job `tests` del pipeline (`pytest --cov`) | ✔ en el run de `1cc858e`; localmente no se corrió la parte `integration` |
| Migraciones (AC-PLT-16, 17, 18) | job `migrations` del pipeline, incluido `check_migrations_roundtrip --allow-data-loss` | ✔ en el run de `1cc858e` |
| Frontend | job `tests` (`pnpm test --coverage`) y job `typecheck` | ✔ en el run de `1cc858e`; `pnpm --dir frontend test` no se corrió localmente |
| Backend, unit (host) | `pytest -m "not integration"` desde `backend/` | ✔ 523 passed, 1 skipped, 35 deselected (`integration`), 2026-11-06 sobre `1cc858e`, con valores ficticios de entorno |
| Scripts (host) | `pytest -c scripts/pytest.ini scripts/tests -m "not gitleaks"` | ✔ 480 passed, 22 deselected (marker `gitleaks`), 2026-11-06 sobre `1cc858e` |
| Workflows (host) | `python scripts/check_workflows.py` | ✔ 2 archivos, 2026-11-06 sobre `1cc858e` |
| Secretos | job `secrets` del pipeline, incluido `pytest -m gitleaks` | ✔ en el run de `1cc858e`; el marker no se corrió localmente |
| Pre-commit | `pre-commit run --all-files` | ⏳ pendiente |
| Build de imágenes y smoke | job `build` | ✘ no existe todavía (T-PLT-37, T-PLT-38) |
| Check `zona-roja` | workflow `zona-roja` | ✘ no existe en `main` (T-PLT-07, PR #48) |

> Para pasar a `Verified` hace falta pegar la salida de estas corridas en este archivo (o el enlace al run de CI)
> y que el dueño lo apruebe. No se acepta “debería pasar”.

## 3. Pruebas transversales

- [ ] **Aislamiento entre organizaciones** — **N/A** en 00: no hay modelos de negocio todavía (Q-044).
- [ ] **Idempotencia / repetición** — **N/A** hasta webhooks (07).
- [ ] **Permisos por rol** — **N/A** hasta 01/02.
- [x] **Sin secretos ni PII en logs/respuestas** — cubierto por AC-PLT-08 y AC-PLT-19.
- [x] **Errores sin trazas ni hosts internos** — cubierto por AC-PLT-34 y AC-PLT-02.
- [x] **Migraciones aplican y revierten** — cubierto por AC-PLT-17 (paso `check_migrations_roundtrip` del job `migrations`).
- [ ] **Build de imágenes** — T-PLT-37 pendiente.

## 4. Validación funcional manual (la hace el dueño)

1. **Requisito previo:** `copy env.example .env` (`cp` en bash). No se ejecutó todavía sobre un clon limpio.
2. `docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait` → 6 servicios `healthy`.
3. `curl -i http://127.0.0.1:8000/healthz` → 200 con `version` (SHA corto).
4. `curl -i http://127.0.0.1:8000/readyz` → 200; detener Redis → 503 sin hosts ni trazas, `/healthz` sigue 200.
5. Revisar logs: una línea JSON por request con `request_id`, `duration_ms` y plantilla de ruta.
6. Superar el throttle anónimo → 429 con `Retry-After` y `problem+json`.
7. `pnpm --dir frontend build` e inspeccionar el bundle: sin URL interna del backend.
8. `python scripts/export_openapi.py --check` → sin diff.
9. `pre-commit run --all-files` → verde.
10. `python scripts/verify_repo_protection.py` → pendiente (T-PLT-40).

## 5. Revisión de código (reviewer)

| Severidad | Hallazgo | Archivo:línea | Regla | Estado |
|---|---|---|---|---|
| — | Sin revisión de cierre del diff completo todavía | — | C-15 | Pendiente |

La revisión por tarea sí ocurrió en los PR mergeados (comentario con SHA + label `zona-roja`). Lo que falta es la
revisión del **diff acumulado** del módulo.

## 6. Hallazgos de proceso

1. 30 tareas mergeadas seguían marcadas “en revisión” en `tasks.md` (drift de estado).
2. No existía `verification.md`: el paso 6 de SDD nunca se ejecutó para 00.
3. `README.md` y `AGENTS.md` decían que no había código.
4. Faltaba el archivo de ejemplo de entorno (Q-048, cerrada: `env.example` entró con T-PLT-39, #45). `.vscode/` sigue
   sin política.
5. El pipeline tiene 9 de los 11 checks: faltan `build` (T-PLT-37, con el smoke de T-PLT-38 como paso) y `zona-roja`
   (T-PLT-07). T-PLT-40 cuenta 10 jobs de `ci.yml` + `zona-roja`.
6. No había ningún mecanismo que detectara el drift: se agrega `scripts/check_spec_state.py`.
7. Cinco tareas mergeadas (#42, #43, #45, #46, #47) quedaron `🟡` en `tasks.md`: sus PR no llevaron la fila a `✅`
   (regla 1 de estados). Conciliado el 2026-11-06.
8. `scripts/spec_state_baseline.json` todavía lista `AC-PLT-17`, `29`, `32` y `33`, que ya tienen test. No produce
   drift, pero esas excepciones quedaron de más.

## 7. Decisión

**Con hallazgos. No aprobar como `Verified` todavía.**

Bloqueantes para cerrar 00-platform:

| Tarea | AC que desbloquea |
|---|---|
| T-PLT-07 (PR #48) | AC-PLT-32 |
| T-PLT-29 | Cierre de RF-PLT-12 (sin AC propio) |
| T-PLT-37 | AC-PLT-25, parte de AC-PLT-20 y parte de AC-PLT-29 |
| T-PLT-38 | AC-PLT-01 y el resto de AC-PLT-29 (E2E) |
| T-PLT-40 | AC-PLT-24 y el cierre de AC-PLT-20 |
| T-PLT-41 | Cierre documental (RF-PLT-16) |

Después de cerrarlas: ejecutar §2, repetir la matriz, marcar las filas `🧪` en `tasks.md` y volver a esta
verificación. La firma final la da el dueño.
