---
spec: SPEC-00
fecha: 2026-11-06
resultado: Con hallazgos     # Aprobada | Con hallazgos | Rechazada
verificado_por: project-steward (cobertura) + qa-verifier (ejecución pendiente)
version_spec: 1.0.15
---

# Verificación — Módulo de Plataforma (SPEC-00)

## 0. Alcance y método

- Spec verificada: `specs/00-platform/spec.sdd.md` v1.0.15 (`Approved`), la de `main` en `2d53815`. La versión
  siguiente no cambia AC: 1.0.16 (provisional) solo suma trazabilidad de Q-065 en `design.md`.
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
| AC-PLT-10 | `frontend/src/lib/server/backend-proxy.test.ts`, `backend-proxy.errors.test.ts`, `backend-proxy.paths.test.ts`; lado backend: `test_AC_PLT_09_valid_uuid4_is_kept_in_log_and_response`. E2E entre los dos servicios: T-PLT-38 | ✔ |
| AC-PLT-11 | `backend/tests/logging/test_AC_PLT_11_celery_task_log.py`, `…_celery_rejected_messages.py` | ✔ |
| AC-PLT-12 | `scripts/tests/test_AC_PLT_12_ruff_print.py` | ✔ |
| AC-PLT-13 | `scripts/tests/test_AC_PLT_13_check_file_size.py`, `test_AC_PLT_20_pipeline_chain.py`, `test_AC_PLT_27_line_endings.py` | ✔ |
| AC-PLT-14 | `backend/tests/architecture/test_AC_PLT_14_adapter_boundary.py` | ✔ |
| AC-PLT-15 | `backend/tests/architecture/test_AC_PLT_15_no_raw_objects_in_services.py` | ✔ |
| AC-PLT-16 | `backend/tests/migrations/test_AC_PLT_16_missing_migration.py` | ✔ |
| AC-PLT-17 | `backend/tests/migrations/test_AC_PLT_17_reversibility.py`, `scripts/tests/test_AC_PLT_20_pipeline_chain.py` (`test_AC_PLT_17_migrations_job_runs_roundtrip_last`) | ✔ (reglas de `RunPython`/`RunSQL`, ida y vuelta en BD descartable y paso `check_migrations_roundtrip` del job `migrations`) |
| AC-PLT-18 | `backend/tests/migrations/test_AC_PLT_18_names_and_mixing.py` | ✔ |
| AC-PLT-19 | `scripts/tests/test_AC_PLT_19_gitleaks.py`, `…_gitleaks_evasions.py`, `…_secrets_job.py` | ✔ |
| AC-PLT-20 | `scripts/tests/test_AC_PLT_20_pipeline_chain.py` (`test_AC_PLT_20_build_is_last_and_needs_migrations`) | ⚠ parcial: forma de la cadena probada y `build` corre último en CI (`needs: migrations`). Ningún run real mostró un lint rojo con `build` sin ejecutar: el último `ci` en rojo es del 2026-11-03, anterior a `build`. Lo cierran el smoke (T-PLT-38) y el ruleset con su PR de sacrificio (T-PLT-40) |
| AC-PLT-21 | `backend/tests/typing/test_AC_PLT_21_mypy_strict.py`, `scripts/tests/test_AC_PLT_21_tsconfig_strict.py` | ✔ |
| AC-PLT-22 | `scripts/tests/test_AC_PLT_22_check_coverage.py` | ✔ |
| AC-PLT-23 | `backend/tests/contract/test_AC_PLT_23_openapi_up_to_date.py`, `frontend/src/lib/problem.test.ts` | ✔ |
| AC-PLT-24 | — | ✘ sin test: falta el ruleset (T-PLT-40) |
| AC-PLT-25 | `scripts/tests/test_AC_PLT_25_dockerfiles.py`, `scripts/tests/test_AC_PLT_25_build_job.py` | ✔ (job `build` real en `main`, run `42231351569` sobre `2d53815`: `uv sync --frozen` y `pnpm install --frozen-lockfile`, imágenes `hub-*:<sha>` con label `revision` = SHA, uid 10001 y 1000) |
| AC-PLT-26 | `scripts/tests/test_AC_PLT_26_audit_deps.py`, `…_pnpm_audit_isolation.py` | ✔ |
| AC-PLT-27 | `scripts/tests/test_AC_PLT_27_line_endings.py` | ✔ |
| AC-PLT-28 | `frontend/src/components/shell/AppShell.test.tsx`, `frontend/src/components/EmptyState.test.tsx`, `ErrorNotice.test.tsx`, `frontend/src/modules/home/components/HomeEmpty.test.tsx`, `frontend/src/modules/settings/components/SettingsSectionList.test.tsx` | ✔ |
| AC-PLT-29 | `frontend/scripts/check-client-bundle.test.ts`, `scripts/tests/test_AC_PLT_25_dockerfiles.py` (`test_AC_PLT_29_builder_checks_the_bundle_built_with_sentinels`) | ⚠ parcial: el chequeo ya corre sobre el bundle real en CI (`client bundle clean: 52 files checked`, runs `42219315435` y `42231351569`). Quedan las páginas dinámicas, que `design.md §3.3.3` asigna al smoke (T-PLT-38) y que el smoke todavía no incluye (§6, hallazgo 12) |
| AC-PLT-30 | `backend/tests/api/test_AC_PLT_30_throttle_429.py` | ✔ |
| AC-PLT-31 | `backend/tests/architecture/test_AC_PLT_31_no_float_money.py` | ✔ |
| AC-PLT-32 | `scripts/tests/test_AC_PLT_32_zona_roja_rules.py`, `scripts/tests/test_AC_PLT_32_zona_roja_cli.py` | ⚠ parcial: los unitarios cubren el criterio con un cliente HTTP falso. En vivo se vio rojo sin veredicto y verde tras publicarlo y re-ejecutar (#50, run `42228562758`; #51, run `42229918324`). Falta probar en vivo "rutas rojas sin label → rojo" y "push nuevo → rojo" (ficha de T-PLT-07; §6, hallazgo 11) |
| AC-PLT-33 | `scripts/tests/test_AC_PLT_33_check_workflows.py`, `scripts/tests/test_AC_PLT_33_check_workflows_refs.py` | ✔ (incluye `test_AC_PLT_33_lint_job_runs_check_workflows`: el job `lint` lo ejecuta) |
| AC-PLT-34 | `backend/tests/api/test_AC_PLT_34_problem_json.py`, `…_problems_domain.py` | ✔ |

**Resumen:** 29 ✔ · 4 ⚠ · 1 ✘ · 34 AC.

## 2. Ejecución de la suite

| Suite | Comando | Estado |
|---|---|---|
| Pipeline en `main` | workflow `ci` en cada push a `main` (10 jobs: `lint`, `file-size`, `secrets`, `deps-audit`, `typecheck`, `architecture`, `tests`, `coverage`, `migrations`, `build`) | ✔ 10/10 jobs, run `42231351569` sobre `2d53815`, 2026-11-06 |
| Backend completo, con PostgreSQL y Redis reales | job `tests` del pipeline (`pytest --cov`) | ✔ 559 passed en el run de `2d53815`; localmente no se corrió la parte `integration` |
| Migraciones (AC-PLT-16, 17, 18) | job `migrations` del pipeline, incluido `check_migrations_roundtrip --allow-data-loss` | ✔ en el run de `2d53815` |
| Frontend | job `tests` (`pnpm test --coverage`) y job `typecheck` | ✔ 90 tests de vitest en el run de `2d53815`; `pnpm --dir frontend test` no se corrió localmente |
| Backend, unit (host) | `pytest -m "not integration"` desde `backend/` | ✔ 523 passed, 1 skipped, 35 deselected (`integration`), 2026-11-06 sobre `1cc858e`, con valores ficticios de entorno; no se repitió sobre `2d53815` |
| Scripts (host) | `pytest -c scripts/pytest.ini scripts/tests -m "not gitleaks"` | ⚠ 549 passed, 7 failed, 22 deselected (marker `gitleaks`), 2026-11-06 sobre `2d53815`. Los 7 son `test_AC_PLT_12_ruff_print.py`: el Python del host no tiene `ruff`. Es del entorno, no de la suite: el job `tests` del run de `2d53815` da 556 passed, 22 deselected, con esos 7 incluidos |
| Workflows (host) | `python scripts/check_workflows.py` | ✔ 3 archivos, 2026-11-06 sobre `2d53815` |
| Secretos | job `secrets` del pipeline, incluido `pytest -m gitleaks` | ✔ 22 passed en el run de `2d53815`; el marker no se corrió localmente |
| Pre-commit | `pre-commit run --all-files` | ⏳ pendiente |
| Build de imágenes | job `build` | ✔ en el run de `2d53815`, con `client bundle clean: 52 files checked` |
| Smoke | paso del job `build` | ✘ no existe todavía (T-PLT-38) |
| Check `zona-roja` | workflow `zona-roja`, solo en PR | ✔ rojo sin veredicto y verde tras publicarlo: #50 (run `42228562758`, intentos 1 y 2) y #51 (run `42229918324`, intentos 1 y 2). No corre en `push` a `main` |

> Para pasar a `Verified` hace falta pegar la salida de estas corridas en este archivo (o el enlace al run de CI)
> y que el dueño lo apruebe. No se acepta “debería pasar”.

## 3. Pruebas transversales

- [ ] **Aislamiento entre organizaciones** — **N/A** en 00: no hay modelos de negocio todavía (Q-044).
- [ ] **Idempotencia / repetición** — **N/A** hasta webhooks (07).
- [ ] **Permisos por rol** — **N/A** hasta 01/02.
- [x] **Sin secretos ni PII en logs/respuestas** — cubierto por AC-PLT-08 y AC-PLT-19.
- [x] **Errores sin trazas ni hosts internos** — cubierto por AC-PLT-34 y AC-PLT-02.
- [x] **Migraciones aplican y revierten** — cubierto por AC-PLT-17 (paso `check_migrations_roundtrip` del job `migrations`).
- [x] **Build de imágenes** — cubierto por AC-PLT-25 (job `build`, run `42231351569`).

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
5. El pipeline tiene los 11 checks que cuenta T-PLT-40: 10 jobs de `ci.yml` + `zona-roja`. Falta el smoke, un paso
   dentro de `build` (T-PLT-38), y el ruleset que los exija (T-PLT-40).
6. No había ningún mecanismo que detectara el drift: se agrega `scripts/check_spec_state.py`.
7. Cinco tareas mergeadas (#42, #43, #45, #46, #47) quedaron `🟡` en `tasks.md`: sus PR no llevaron la fila a `✅`
   (regla 1 de estados). Conciliado el 2026-11-06.
8. `scripts/spec_state_baseline.json` listaba `AC-PLT-17`, `29`, `32` y `33`, que ya tienen test. No producía drift.
   Conciliado el 2026-11-06: queda solo `AC-PLT-24`.
9. T-PLT-07, T-PLT-37 y T-PLT-42 quedaron `🟡` tras mergearse (#48, #50, #51), otra vez la regla 1 de estados.
   Conciliado el 2026-11-06.
10. El verde de `zona-roja` en #48 no comprobó nada: el workflow corre el script de la base (D-09) y en `8cd5bd9`
    `check_zona_roja.py` no tenía `main()`. Es propio del PR que lo crea. El primer run real es el de #50.
11. El rojo de #50 y #51 tras el rebase no prueba "push nuevo → rojo". Los dos tenían un veredicto sobre el SHA
    anterior, pero en el formato viejo, sin `<!-- reviewer-verdict -->`, que el check no cuenta como veredicto: el
    rojo sale igual por falta de veredicto válido, no por SHA vencido. Tampoco hubo ningún PR sin label desde que el
    check existe.
12. `design.md §3.3.3` asigna las páginas dinámicas de AC-PLT-29 al smoke, pero la secuencia de `§3.5` y el plan de
    pruebas de T-PLT-38 no tienen ningún paso ni test de AC-PLT-29. Para el planner, antes de cerrar T-PLT-38.
13. #48 lo mergeó Claude como excepción puntual a Q-063, autorizada por el dueño (comentario en #48). Q-063 sigue
    vigente para los PR siguientes que toquen `zona-roja.yml`.

## 7. Decisión

**Con hallazgos. No aprobar como `Verified` todavía.**

Bloqueantes para cerrar 00-platform:

| Tarea | AC que desbloquea |
|---|---|
| Verificación manual de la ficha de T-PLT-07 | AC-PLT-32: rutas rojas sin label → rojo; push nuevo sobre un veredicto válido → rojo |
| T-PLT-29 (PR #52 abierto) | Cierre de RF-PLT-12 (sin AC propio) |
| T-PLT-38 | AC-PLT-01 y el resto de AC-PLT-29 (E2E) |
| T-PLT-40 | AC-PLT-24 y el cierre de AC-PLT-20 |
| T-PLT-41 | Cierre documental (RF-PLT-16) |

Después de cerrarlas: ejecutar §2, repetir la matriz, marcar las filas `🧪` en `tasks.md` y volver a esta
verificación. La firma final la da el dueño.
