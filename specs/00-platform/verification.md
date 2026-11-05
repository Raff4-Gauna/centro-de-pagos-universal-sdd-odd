---
spec: SPEC-00
fecha: 2026-11-05
resultado: Con hallazgos     # Aprobada | Con hallazgos | Rechazada
verificado_por: project-steward (cobertura) + qa-verifier (ejecución pendiente)
version_spec: 1.0.8
---

# Verificación — Módulo de Plataforma (SPEC-00)

## 0. Alcance y método

- Spec verificada: `specs/00-platform/spec.sdd.md` v1.0.8 (`Approved`).
- Tareas: `specs/00-platform/tasks.md` (estado conciliado con git el 2026-11-05).
- Método: matriz AC→test sobre el árbol real, revisión de la cadena de CI y checklist manual.
- **Leyenda de la columna “Cobertura”:** `✔` el AC tiene al menos un test con su ID y cubre el criterio completo;
  `⚠` cobertura parcial (el test existe pero no prueba todo el AC); `✘` sin test o tarea pendiente.
- **Este documento no declara tests en verde sin ejecutarlos.** Que un archivo exista no basta para `Verified`:
  la ejecución real se registra en §2 y la firma final la da el dueño.

## 1. Matriz AC → test

| AC | Test(s) | Cobertura |
|---|---|---|
| AC-PLT-01 | `scripts/tests/test_RF_PLT_02_compose_dev.py` (estático) | ⚠ parcial: falta `up --wait` real y el servicio `frontend` (T-PLT-36, T-PLT-38) |
| AC-PLT-02 | `backend/tests/health/test_AC_PLT_02_readyz.py` | ✔ |
| AC-PLT-03 | `backend/tests/config/test_AC_PLT_03_missing_required_var.py` | ✔ |
| AC-PLT-04 | `backend/tests/config/test_AC_PLT_04_check_deploy.py` | ✔ |
| AC-PLT-05 | — | ✘ sin test: `.env.example` no existe (T-PLT-39, Q-048) |
| AC-PLT-06 | `backend/tests/config/test_AC_PLT_06_no_provider_env.py`, `backend/tests/config/test_C_06_celery_broker_url.py` | ✔ (la parte de `spikes/.env.example` depende de T-PLT-39) |
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
| AC-PLT-17 | — | ✘ sin test: falta la reversibilidad (T-PLT-24) |
| AC-PLT-18 | `backend/tests/migrations/test_AC_PLT_18_names_and_mixing.py` | ✔ |
| AC-PLT-19 | `scripts/tests/test_AC_PLT_19_gitleaks.py`, `…_gitleaks_evasions.py`, `…_secrets_job.py` | ✔ |
| AC-PLT-20 | `scripts/tests/test_AC_PLT_20_pipeline_chain.py` | ✔ (cadena; la completan T-PLT-37 y T-PLT-40) |
| AC-PLT-21 | `backend/tests/typing/test_AC_PLT_21_mypy_strict.py`, `scripts/tests/test_AC_PLT_21_tsconfig_strict.py` | ✔ |
| AC-PLT-22 | `scripts/tests/test_AC_PLT_22_check_coverage.py` | ✔ |
| AC-PLT-23 | `backend/tests/contract/test_AC_PLT_23_openapi_up_to_date.py`, `frontend/src/lib/problem.test.ts` | ✔ |
| AC-PLT-24 | — | ✘ sin test: falta el ruleset (T-PLT-40) |
| AC-PLT-25 | `scripts/tests/test_AC_PLT_25_dockerfiles.py` | ⚠ parcial: chequeo estático; falta el build real (T-PLT-37) |
| AC-PLT-26 | `scripts/tests/test_AC_PLT_26_audit_deps.py`, `…_pnpm_audit_isolation.py` | ✔ |
| AC-PLT-27 | `scripts/tests/test_AC_PLT_27_line_endings.py` | ✔ |
| AC-PLT-28 | `frontend/src/components/shell/AppShell.test.tsx`, `frontend/src/components/EmptyState.test.tsx`, `ErrorNotice.test.tsx`, `frontend/src/modules/home/components/HomeEmpty.test.tsx`, `frontend/src/modules/settings/components/SettingsSectionList.test.tsx` | ✔ |
| AC-PLT-29 | — | ✘ sin test: falta la imagen del frontend y el bundle (T-PLT-36) |
| AC-PLT-30 | `backend/tests/api/test_AC_PLT_30_throttle_429.py` | ✔ |
| AC-PLT-31 | `backend/tests/architecture/test_AC_PLT_31_no_float_money.py` | ✔ |
| AC-PLT-32 | — | ✘ sin test: faltan los checks de zona roja (T-PLT-06, T-PLT-07) |
| AC-PLT-33 | — | ✘ sin test: falta `check_workflows.py` (T-PLT-05) |
| AC-PLT-34 | `backend/tests/api/test_AC_PLT_34_problem_json.py`, `…_problems_domain.py` | ✔ |

**Resumen:** 26 ✔ · 2 ⚠ · 6 ✘ · 34 AC.

## 2. Ejecución de la suite

| Suite | Comando | Estado |
|---|---|---|
| Scripts / tooling | `.venv\Scripts\python.exe -m pytest -c scripts/pytest.ini scripts/tests -q` | ⚠ 254 passed, 1 failed: `test_AC_PLT_26_pip_audit_is_isolated_from_planted_modules` falla por `UnicodeDecodeError` al decodificar la salida de `pip-audit` en una consola Windows en español. Es un defecto de entorno preexistente, no del cambio; no se marca `✔` hasta correrlo en CI/Linux. |
| Scripts nuevos (drift) | `.venv\Scripts\python.exe -m pytest -c scripts/pytest.ini scripts/tests/test_check_spec_state.py -q` | ✔ 16 passed |
| Backend | `docker compose … exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend pytest` | ⏳ pendiente (requiere el stack levantado) |
| Frontend | `pnpm --dir frontend test` | ⏳ pendiente |
| Tipos | `pnpm --dir frontend typecheck` · `docker compose … exec backend mypy . ../scripts` | ⏳ pendiente |
| Lint | `.venv\Scripts\ruff.exe check` + `format --check` sobre los `.py` nuevos | ✔ verde |
| Pre-commit | `pre-commit run --all-files` | ⏳ pendiente (el hook `no-commit-to-branch` exige rama, no `main`) |

> Para pasar a `Verified` hace falta pegar la salida de estas corridas en este archivo (o el enlace al run de CI)
> y que el dueño lo apruebe. No se acepta “debería pasar”.

## 3. Pruebas transversales

- [ ] **Aislamiento entre organizaciones** — **N/A** en 00: no hay modelos de negocio todavía (Q-044).
- [ ] **Idempotencia / repetición** — **N/A** hasta webhooks (07).
- [ ] **Permisos por rol** — **N/A** hasta 01/02.
- [x] **Sin secretos ni PII en logs/respuestas** — cubierto por AC-PLT-08 y AC-PLT-19.
- [x] **Errores sin trazas ni hosts internos** — cubierto por AC-PLT-34 y AC-PLT-02.
- [ ] **Migraciones aplican y revierten** — T-PLT-24 pendiente.
- [ ] **Build de imágenes** — T-PLT-37 pendiente.

## 4. Validación funcional manual (la hace el dueño)

1. **Requisito previo:** crear `.env.example` (T-PLT-39) o usar la tabla de `infra/README.md`. Hoy el paso 1 del
   AC-PLT-01 no se puede reproducir tal cual.
2. `docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait` → 5 servicios `healthy`
   (falta `frontend`, T-PLT-36).
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
4. `.env.example` ausente (Q-048) y `.vscode/` sin política.
5. Faltan los jobs `build` y `smoke` del pipeline (9 de 11).
6. No había ningún mecanismo que detectara el drift: se agrega `scripts/check_spec_state.py`.

## 7. Decisión

**Con hallazgos. No aprobar como `Verified` todavía.**

Bloqueantes para cerrar 00-platform:

| Tarea | AC que desbloquea |
|---|---|
| T-PLT-05, 06, 07 | AC-PLT-33 y AC-PLT-32 |
| T-PLT-24 | AC-PLT-17 |
| T-PLT-36 | AC-PLT-29 |
| T-PLT-37, 38 | AC-PLT-25 (completo) y AC-PLT-01 |
| T-PLT-39 (Q-048) | AC-PLT-05 |
| T-PLT-40 | AC-PLT-24 |
| T-PLT-41 | Cierre documental (RF-PLT-16) |

Después de cerrarlas: ejecutar §2, repetir la matriz, marcar las filas `🧪` en `tasks.md` y volver a esta
verificación. La firma final la da el dueño.
