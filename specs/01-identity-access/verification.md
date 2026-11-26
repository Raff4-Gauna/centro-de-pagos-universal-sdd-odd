---
spec: SPEC-01
fecha: 2026-11-26
resultado: Con hallazgos     # Aprobada | Con hallazgos | Rechazada
verificado_por: qa-verifier (pasada conjunta con SPEC-02, Q-108)
version_spec: 1.0.2
commit_verificado: 5536088504208697469930a25926c8397a87cb0e
---

# Verificación — Módulo de Identidad y Acceso (SPEC-01)

## 0. Alcance y método

- Spec verificada: `specs/01-identity-access/spec.sdd.md` v1.0.2 (`Approved`), 38 AC. Se verifica junto con SPEC-02
  (Q-108): la matriz de 02 está en `specs/02-tenancy-rbac/verification.md`.
- Tareas: `specs/01-identity-access/tasks.md`, 33 ✅, conciliadas con git (`check_spec_state.py`: `OK: sin drift`,
  38 AC con test que nombra el AC, 0 sin test).
- Commit verificado: `5536088` (`origin/main`, #152), rama `log/2026-11-26-verify-01-02`.
- **Leyenda:** `✔` hay test con el ID del AC, cubre el Dado/Cuando/Entonces completo y corrió en verde en las corridas
  de §2, hechas hoy sobre ese commit. `⚠` cubre una parte (se dice qué falta). `✘` sin test o en rojo.
- La suite corrió completa, sin tests salteados (`0 skipped`), así que un `✔` vale para todos los tests de su fila.
- No se agregaron tests: ningún AC quedó sin un test que lo verifique.

## 1. Matriz AC → test

Rutas relativas a `backend/tests/identity/` salvo que se indique otra. `fe:` es `frontend/src/`. `ten:` es
`backend/tests/tenancy/`.

| AC | Test(s) | Cobertura |
|---|---|---|
| AC-IDA-01 | `api/test_login_complete.py` (`test_AC_IDA_01_active_user_gets_session`, `…_invited_login_end_to_end_reaches_me`); `fe:app/api/auth/google/callback/route.test.ts`; `scripts/tests/test_e2e_login.py`; E2E real §3 | ✔ |
| AC-IDA-02 | `test_AC_IDA_02_invited_user.py` (`…_invited_user_is_created_and_invitation_accepted`, `…_a_race_lost_twice_fails_without_personal_data`), `test_AC_IDA_02_concurrent_callbacks.py` (`…_concurrent_callbacks_one_user`), `test_login_with_real_port.py` (puerto real de SPEC-02) | ✔ (incluye la concurrencia: un usuario, ningún `500`) |
| AC-IDA-03 | `api/test_login_complete.py` (`…_no_invitation_creates_nothing`, `…_rejected_is_audited`), `api/test_login_complete_errors.py` (`…_rejection_event_survives_the_rollback`) | ✔ |
| AC-IDA-04 | `test_AC_IDA_02_invited_user.py`, `test_login_with_real_port.py`, `ten:test_invitation_port_contract.py` (`…_expired_since_find_is_refused`, `…_revoked_between_find_and_accept`) | ✔ (incluye "vigente al iniciar el login") |
| AC-IDA-05 | `test_AC_IDA_05_rollback.py`, `test_login_with_real_port.py`, `ten:test_invitation_port_contract.py` (`…_one_invalid_rolls_back_all_inside_the_port`) | ✔ |
| AC-IDA-06 | `api/test_login_complete.py` (`test_AC_IDA_06_unverified_email`) | ✔ |
| AC-IDA-07 | `oidc/test_id_token.py` (firma, `aud`, `iss`, vencido >60 s y dentro de la tolerancia, algoritmos), `oidc/test_google_gateway.py` | ✔ |
| AC-IDA-08 | `api/test_login_complete.py` (`…_bad_state_never_calls_google`, `…_nonce_mismatch`, `…_repeated_callback`), `api/test_login_complete_errors.py`, `oidc/test_id_token.py` | ✔ |
| AC-IDA-09 | `api/test_login_complete.py`, `test_user_provisioning.py`, `test_refresh.py`, `api/test_refresh_view.py` (`…_inactive_user_refresh_via_api`) | ✔ |
| AC-IDA-10 | `tokens/test_access_token.py` (`…_expired_over_60s`, `…_issued_14_min_ago_is_valid`), `api/test_authentication.py` (`…_expired_via_api`) | ✔ |
| AC-IDA-11 | `tokens/test_access_token.py` (firma alterada, otra clave, `alg=none`, HS256, fuera de la lista), `api/test_authentication.py` | ✔ |
| AC-IDA-12 | `tokens/test_access_token.py` (`…_foreign_iss_aud`, `…_google_token_rejected`), `api/test_authentication.py` (`…_google_token_is_401`) | ✔ |
| AC-IDA-13 | `tokens/test_access_token.py` (`test_AC_IDA_13_exact_claims`) | ✔ |
| AC-IDA-14 | `test_refresh.py`, `api/test_refresh_view.py`, `test_session_constraints.py` (`…_database_refuses_anything_but_a_sha256`), `test_session_lifecycle.py` | ✔ |
| AC-IDA-15 | `test_refresh.py` (`…_used_token_past_grace_revokes_session`), `test_refresh_concurrency.py`, `domain/test_session_policy.py` | ✔ |
| AC-IDA-16 | `test_refresh.py`, `api/test_refresh_view.py`, `test_session_constraints.py`, `test_session_lifecycle.py`, `domain/test_session_policy.py` | ✔ (inactividad, absoluto y `absolute_expires_at` inmóvil) |
| AC-IDA-17 | `test_logout.py`, `api/test_logout_view.py`, `fe:app/api/auth/logout/route.test.ts`, `fe:modules/identity/hooks/useLogout.test.tsx`, `scripts/tests/test_e2e_login.py`; E2E real §3 | ✔ |
| AC-IDA-18 | `fe:lib/server/cookies.test.ts`, `fe:app/api/auth/google/callback/route.test.ts`, `fe:lib/server/session-proxy.test.ts`, `frontend/scripts/check-client-bundle.test.ts` | ✔ (lado BFF, que es lo que llega al navegador) |
| AC-IDA-19 | `domain/test_return_path.py`, `api/test_login_start.py`; `fe:lib/server/return-path.test.ts`, `fe:lib/server/csrf.test.ts`, `fe:proxy.test.ts`, `fe:app/api/auth/**/route.test.ts` y otros (15 archivos de frontend) | ✔ (redirect y CSRF) |
| AC-IDA-20 | `api/test_throttles.py`, `api/test_login_start.py` (`…_eleventh_start_is_429_without_google`), `api/test_login_complete.py` (`…_eleventh_callback_is_429`, sin canje con Google), `test_refresh_concurrency.py` (`…_31st_refresh_is_429`) | ✔ |
| AC-IDA-21 | `api/test_AC_IDA_21_me.py` (`…_returns_only_own_data`, `…_anonymous_is_401_unauthenticated`), `ten:test_membership_selector.py` (`…_me_uses_real_selector`) | ✔ |
| AC-IDA-22 | `api/test_AC_IDA_21_me.py`, `api/test_authentication.py`, `api/test_refresh_view.py` (`…_api_key_on_refresh`) | ✔ |
| AC-IDA-23 | `api/test_AC_IDA_23_no_secrets.py`, `test_AC_IDA_23_redaction_keys.py` y las pruebas de logs de start, callback, refresh y logout | ✔ (además, el barrido de logs del E2E, §3) |
| AC-IDA-24 | `api/test_AC_IDA_24_events.py` (`…_every_event_is_emitted`, `…_429_is_not_audited`, `…_catalog_matches_spec`), `test_AC_IDA_02_invited_user.py` (organización de la invitación) | ✔ |
| AC-IDA-25 | `api/test_sessions.py` (`…_foreign_session_is_404`, `…_ended_session_is_404`) | ✔ |
| AC-IDA-26 | `api/test_authentication.py`, `api/test_sessions.py`, `fe:lib/api-client.test.ts`, `fe:lib/server/session-proxy.refresh.test.ts` | ✔ |
| AC-IDA-27 | `test_AC_IDA_27_deactivate.py`, `test_revocation_concurrency.py`, `test_Q_242_operator_refused.py` | ✔ (incluye reactivar sin revivir sesiones) |
| AC-IDA-28 | `test_refresh_concurrency.py` (`…_two_concurrent_refreshes`), `test_refresh.py`, `domain/test_session_policy.py`, `fe:lib/server/refresh.test.ts` | ✔ |
| AC-IDA-29 | `test_user_provisioning.py` (`…_email_change_free`, `…_new_sub_with_taken_email_is_conflict`, con la alerta en el log) | ✔ |
| AC-IDA-30 | `test_user_provisioning.py`, `api/test_AC_IDA_21_me.py` (`…_no_memberships_returns_empty_list`), `fe:modules/identity/components/NoOrganizationState.test.tsx` | ✔ |
| AC-IDA-31 | `test_AC_IDA_31_normalization.py`, `test_AC_IDA_02_invited_user.py`, `test_login_with_real_port.py`, `test_user_constraints.py` | ✔ |
| AC-IDA-32 | `test_AC_IDA_32_no_endpoints.py` (esquema, rutas, admin ausente con `settings.prod`), `ten:commands/test_create_org.py` (`…_bootstrap_command_audited`) | ✔ |
| AC-IDA-33 | `api/test_sessions.py` (`…_revoke_others_keeps_current`, `…_list_has_no_ip`), `test_revocation_concurrency.py`, `fe:modules/identity/components/SessionsTable.test.tsx`, `scripts/tests/test_e2e_login.py`; E2E real §3 | ✔ |
| AC-IDA-34 | `tokens/test_access_token.py` (`…_skew_30s_accepted_120s_rejected`), `api/test_authentication.py` (`…_skew_via_api`) | ✔ |
| AC-IDA-35 | `test_logout.py`, `api/test_logout_view.py` (`…_expired_jwt_logs_out_via_api`), `tokens/test_access_token.py`, `fe:app/api/auth/logout/route.test.ts` | ✔ |
| AC-IDA-36 | `oidc/test_google_gateway.py` (timeout, conexión, `429`, `5xx`, JWKS caído, caché válida), `oidc/test_id_token.py` | ✔ |
| AC-IDA-37 | `api/test_throttles.py` (`…_ten_client_ips_share_no_quota`), `api/test_login_start.py`, `fe:lib/server/client-ip.test.ts` | ✔ |
| AC-IDA-38 | `test_purge.py` (`…_91_days_purged_89_kept`, `…_exactly_90_days_is_kept`, `…_user_is_never_deleted`), `test_purge_concurrency.py`, `test_purge_task.py` | ✔ |

**Resumen:** 38 ✔ · 0 ⚠ · 0 ✘ · 38 AC.

## 2. Ejecución (2026-11-26, commit `5536088`)

| Suite | Comando | Resultado |
|---|---|---|
| Backend completo (unit + integration), PostgreSQL y Redis reales | `pytest` en la imagen `centro-pagos-backend:dev` con el worktree montado en `/repo`, `config.settings.test`, `TZ=UTC`, BD `ver-pg` y Redis `ida00-redis` descartables | ✔ **3342 passed**, 0 skipped, 0 failed, 518 s. De esos, 833 están en `tests/identity/` y 387 llevan `AC_IDA` en el nombre |
| Frontend | `corepack enable && pnpm install --frozen-lockfile && pnpm test` en `node:24.22.2-trixie-slim` | ✔ 72 archivos, **631 passed** |
| Tipos frontend | `pnpm typecheck` (mismo contenedor) | ✔ exit 0 |
| Tipos backend y scripts | `mypy --no-incremental . ../scripts` en la imagen | ✔ `no issues found in 509 source files` |
| Scripts (host) | `python -m pytest -c scripts/pytest.ini scripts/tests` | ⚠ 924 passed, 7 failed, 22 deselected (`gitleaks`). Los 7 son de `test_AC_PLT_12_ruff_print.py`: el Python del host no tiene `ruff`. Es un problema del entorno, no de 01 |
| Los 7 de `ruff` | `pytest -c scripts/pytest.ini scripts/tests/test_AC_PLT_12_ruff_print.py` en la imagen (trae `ruff`) | ✔ 7 passed. Con eso pasan los 931 de scripts |
| Lint | `ruff check .` y `ruff format --check .` con `ruff 0.17.3` (imagen) | ✔ `All checks passed!`, `520 files already formatted` |
| Migraciones | `makemigrations --check --dry-run`, `lint_migrations` y `check_migrations_roundtrip --allow-data-loss` contra una BD creada para esto y borrada después (`hub_roundtrip_ver`) | ✔ `Round trip passed for 2 app(s): identity, tenancy` |
| Estado | `python scripts/check_spec_state.py` | ✔ `OK: sin drift` |
| CI sobre el mismo commit | workflow `ci`, run `45900649873` (push a `main`) | ✔ 10/10 jobs. En `tests`: backend 3342 passed, scripts 931 passed, vitest 631 passed |
| Pre-commit | `pre-commit run --all-files` | **pendiente**: no está instalado en el host. Lo cubren el `ruff` de esta tabla y el job `lint` del run `45900649873` |

## 3. Corrida real del E2E (`scripts/e2e_login.py`, T-IDA-31)

- **Fecha:** 2026-11-26. **Imágenes:** `hub-backend:5536088…` y `hub-frontend:5536088…`, de `docker build --target runtime
  --build-arg GIT_SHA=5536088504208697469930a25926c8397a87cb0e` sobre este commit.
- **Stack:** proyecto Compose propio `hub-e2e-ver`, con el archivo fuera del repo, como indica `infra/README.md` ("Stack
  descartable"): `db`, `redis`, `backend` (`127.0.0.1:18432`) y `frontend` (`127.0.0.1:13432`), con `config.settings.dev`,
  `IDENTITY_OIDC_PROVIDER=fake`, valores ficticios en línea y un par de claves P-256 generado para la corrida. No usó el
  `.env` ni los volúmenes de desarrollo. `/healthz` dio `version 5536088`.
- **Usuario:** creado con el comando de `infra/README.md`.
- **Comando:** `python scripts/e2e_login.py --email e2e@example.test --frontend-url http://127.0.0.1:13432
  --provider-url http://127.0.0.1:18432`.
- **Salida:** `e2e ok [login-A]` · `[login-B]` · `[login-C]` · `[sessions-before]` · `[revoke-others]` · `[logout]` ·
  `e2e passed`, código 0.
- **Lo que se miró después** (sin imprimir valores), en el mismo stack, que luego corrió también el E2E de tenancy:
  - `auth_sessions` de esta corrida: 1 `revoked`/`logout` y 2 `revoked`/`revoked_others` (AC-IDA-33, AC-IDA-17). Las 3
    `active` que quedan son de las personas del E2E de tenancy, que no hace logout.
  - Log de auditoría: 6 `identity.login_succeeded` (3 de cada E2E), 2 `identity.session_revoked` y 1 `identity.logout`.
  - Logs de los cuatro servicios (245 líneas): ninguna aparición de un email `@example.test`, de la credencial del BFF,
    del client secret, de `PRIVATE KEY`, de `__Host-cpu_rt` ni de `#token=`. Ninguna línea `error` ni `Traceback`.
- **Limpieza:** `docker compose down -v`, que no dejó contenedor, volumen ni red de `hub-e2e-ver`. El archivo Compose y
  las claves se borraron. Quedan las imágenes `hub-*:5536088…`, que no tienen secretos.

**Límites:** el E2E no corre en CI, porque el stack de CI usa `settings.prod`, sin el proveedor falso; sumarlo toca
`ci.yml` (Q-063). Prueba el login por HTTP, no el render de las pantallas, y no prueba Google real (§5, paso 1).

## 4. Pruebas transversales

- [x] **Aislamiento entre personas:** AC-IDA-25 (sesión de otro usuario → `404`, y la de B sigue `active`) y AC-IDA-21
  (`/api/me` devuelve solo lo propio). El aislamiento por organización está en la verificación de 02.
- [x] **Idempotencia / repetición:** un callback repetido no crea sesión (AC-IDA-08); el segundo logout da `204` sin
  efectos (AC-IDA-17); desactivar o reactivar dos veces no cambia nada y se audita (AC-IDA-27); el E2E se repite sobre el
  mismo stack.
- [x] **Duplicados y concurrencia:** dos callbacks a la vez dejan un usuario (AC-IDA-02); dos refrescos a la vez no dan
  `refresh_reuse_detected` (AC-IDA-28); el reuso fuera de la tolerancia revoca (AC-IDA-15).
- [x] **Orden de eventos:** desactivar contra un refresh en curso (`test_AC_IDA_27_deactivate_waits_for_a_refresh`,
  `…_refresh_waits_for_deactivate`), cerrar las demás contra un refresh (AC-IDA-33), la purga contra refresh y logout
  (AC-IDA-38).
- [x] **Permisos:** 01 no tiene roles. Una API key no es sesión de persona (AC-IDA-22) y no hay endpoint que provisione
  o desactive (AC-IDA-32). Los roles están en 02.
- [x] **Sin secretos ni PII en logs y respuestas:** AC-IDA-18, AC-IDA-23 y el barrido de logs del E2E (§3).
- [x] **Migraciones aplican y revierten:** `check_migrations_roundtrip` (§2).

## 5. Validación funcional manual (la hace el dueño)

1. **Google real** (`design.md §9`, fila "Manual (paso 6)", AC-IDA-01, 02 y 28). Requisito: un entorno con HTTPS y un
   client ID de Google propio. No hay staging: depende del hosting (Q-020, Q-065). Pasos: entrar con una cuenta
   invitada; cancelar en la pantalla de Google y comprobar que vuelve a `/login` con el aviso de cancelación; abrir dos
   pestañas y dejarlas más de 15 min, y comprobar que las dos siguen operando; hacer logout y comprobar que la otra
   pestaña vuelve al login en su siguiente request. **No se ejecutó.** Si el dueño lo posterga hasta tener hosting,
   conviene que lo deje escrito.
2. **E2E por HTTP**, reproducible: los pasos de §3, con `infra/README.md` ("E2E del login" y "Stack descartable").
   Resultado esperado: `e2e passed` y código 0. Con un email sin usuario: `e2e failed [login-A-callback]:
   /login?error=not_invited` y código 1.
3. **Pantalla "Seguridad"**, con el stack de desarrollo y el proveedor falso: con tres sesiones, "Cerrar las demás" deja
   solo la actual, y el listado muestra navegador/SO y fechas, sin IP (AC-IDA-33).
4. **Confirmar el tope `refresh_ip`** (`tasks.md`, "Ajustes al diseño"): `RefreshIpThrottle`, `60/min` por IP del
   cliente, además de los 30/min por sesión de RN-IDA-15. No está en la spec ni en `design.md §7.6`. Si se acepta, va
   al "Historial de cambios" de la spec o del diseño; si no, se abre una tarea para sacarlo.

## 6. Revisión de código (reviewer)

| Severidad | Hallazgo | Archivo:línea | Regla | Estado |
|---|---|---|---|---|
| — | Falta la revisión del diff acumulado del módulo (paso 2 de `/verify`) | — | C-15 | Pendiente |

Cada PR de 01 tuvo veredicto del `reviewer` con SHA y el label `zona-roja` (`tasks.md`, columna Evidencia). La revisión
de cierre del diff completo de 01 y 02 la pide la sesión principal.

## 7. Hallazgos

1. **Tope `refresh_ip` sin confirmar** (§5, paso 4): el código además limita por IP, y la spec no lo pide.
2. **Validación manual con Google real sin hacer** (§5, paso 1): `design.md §9` la planifica para el paso 6 y no hay
   un entorno donde correrla.
3. **`scripts/spec_state_baseline.json` desactualizado:** la lista `allow_missing_tests` de `01-identity-access` sigue
   con 26 AC que ya tienen test. No da drift (`check_spec_state.py` cuenta 0 en baseline), pero si se borrara el test de
   uno de esos AC, el chequeo no lo detectaría. Lo corrige `project-steward`; no corresponde a este PR.
4. **Revisión del diff acumulado** pendiente (§6).

Ninguno es un hallazgo de código ni de cobertura: los 38 AC tienen test y corrieron en verde.

## 8. Decisión

**Con hallazgos. No marcar `Verified` todavía.** Lo automatizable está completo: 38 ✔ y la suite completa en verde sobre
`5536088`. Para cerrar 01 falta:

| Acción | Quién | Qué desbloquea |
|---|---|---|
| Confirmar o rechazar el tope `refresh_ip` (§5, paso 4) | dueño | hallazgo 1 |
| Correr Google real, o dejar escrito que se posterga hasta tener hosting (§5, paso 1) | dueño | hallazgo 2: AC-IDA-01, 02 y 28 en un entorno real |
| Revisar el diff acumulado de 01 y 02 (§6) | `reviewer` | cierre del módulo |

No hay tareas para reabrir. Cuando esto se resuelva, las filas de `tasks.md` pasan a `🧪` y el dueño decide `Verified`,
junto con SPEC-02 (Q-108).
