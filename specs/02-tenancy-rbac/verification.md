---
spec: SPEC-02
fecha: 2026-11-26
resultado: Con hallazgos     # Aprobada | Con hallazgos | Rechazada
verificado_por: qa-verifier (pasada conjunta con SPEC-01, Q-108)
version_spec: 1.0.3
commit_verificado: 5536088504208697469930a25926c8397a87cb0e
---

# Verificación — Módulo de Organizaciones, Sucursales y Roles (SPEC-02)

## 0. Alcance y método

- Spec verificada: `specs/02-tenancy-rbac/spec.sdd.md` v1.0.3 (`Approved`), 40 AC (`AC-TEN-01` a `AC-TEN-40`). Se
  verifica junto con SPEC-01 (Q-108): la matriz de 01 está en `specs/01-identity-access/verification.md`.
- **`AC-CHG-13`** aparece en la spec (§7, aislamiento de listados) como cita a SPEC-06, no como AC de 02. Por eso
  `check_spec_state.py` lo cuenta entre los 41 y lo deja en el baseline (`spec_state_baseline.json`, "sale cuando exista
  su test"). No tiene fila en la matriz: se verifica con SPEC-06. El comportamiento que cita para 02 (los listados nunca
  incluyen recursos de otra organización) lo cubren AC-TEN-01, 02, 08 y 12.
- Tareas: `specs/02-tenancy-rbac/tasks.md`, 39 ✅, conciliadas con git (`check_spec_state.py`: `OK: sin drift`; 40 AC con
  test que nombra el AC, 1 sin test, que es `AC-CHG-13`, en baseline).
- Commit verificado: `5536088` (`origin/main`, #152), rama `log/2026-11-26-verify-01-02`.
- **Leyenda:** `✔` hay test con el ID del AC, cubre el Dado/Cuando/Entonces completo y corrió en verde en las corridas
  de §2, hechas hoy sobre ese commit. `⚠` cubre una parte (se dice qué falta). `✘` sin test o en rojo.
- La suite corrió completa, sin tests salteados (`0 skipped`), así que un `✔` vale para todos los tests de su fila.
- No se agregaron tests: el único hueco (AC-TEN-28, s2s sobre un cobro) no se puede cubrir sin el módulo de cobros.

## 1. Matriz AC → test

Rutas relativas a `backend/tests/tenancy/` salvo que se indique otra. `ct:` es `backend/tests/cross_tenant/`, `arch:`
es `backend/tests/architecture/` y `fe:` es `frontend/src/`.

| AC | Test(s) | Cobertura |
|---|---|---|
| AC-TEN-01 | `api/test_branch_detail.py` (`test_AC_TEN_01_other_org_branch_is_404`, `…_malformed_id_is_404`); `ct:test_routes.py` (todas las rutas) | ✔ |
| AC-TEN-02 | `api/test_membership_role.py`, `api/test_membership_exit.py` (`…_other_org_membership_is_404`), `api/test_invitations_manage_refusals.py` (`…_other_org_invitation_is_404`), `api/test_memberships.py`, `api/test_invitations_list.py` | ✔ |
| AC-TEN-03 | `api/test_resolution.py` (`…_foreign_equals_nonexistent`, `…_malformed_header_equals_nonexistent`) | ✔ (código y cuerpo idénticos) |
| AC-TEN-04 | `api/test_resolution.py` (`…_revoked_membership_with_valid_jwt`), `api/test_membership_exit.py` (`…_revoked_admin_is_rejected`) | ✔ |
| AC-TEN-05 | `api/test_branch_detail.py` (`…_demoted_admin_cannot_edit_branch`), `api/test_membership_role.py` (`…_demoted_admin_next_request_403`) | ✔ |
| AC-TEN-06 | `api/test_resolution.py` (`…_missing_header`, `…_anonymous_is_401_before_the_header`) | ✔ |
| AC-TEN-07 | `api/test_branches.py` (`…_org_in_body_creates_nothing_in_b`, `…_body_is_strict`), `api/test_branch_detail.py`, `test_AC_TEN_07_tenant_model.py`, `test_AC_TEN_07_tenant_updates.py` | ✔ |
| AC-TEN-08 | `api/test_organizations.py` (`…_exactly_my_orgs_and_roles`), `scripts/tests/test_e2e_tenancy.py`; E2E real §3 (`[two-orgs]`) | ✔ |
| AC-TEN-09 | `api/test_branch_filter.py` (`…_foreign_branch_filter_is_404`) | ✔ |
| AC-TEN-10 | `arch:test_tenant_queries.py` (`…_raw_manager_fails_naming_the_file`, `…_real_code_has_no_violations`), `arch:test_tenant_models.py`, `arch:test_model_scopes.py`, `arch:test_restricted_*.py` y otros | ✔ |
| AC-TEN-11 | `test_AC_TEN_11_fail_closed.py`, `test_AC_TEN_11_scoped_writes.py`, `test_AC_TEN_07_tenant_model.py` (`…_tenant_model_without_scope_raises`), `test_branch.py`, `test_membership_for_user.py` | ✔ |
| AC-TEN-12 | `ct:test_routes.py` (`…_the_suite_walks_every_real_route`, `…_new_route_without_case_fails`, `…_every_case_runs`), `ct:test_walker.py` | ✔ |
| AC-TEN-13 | `api/test_membership_role.py` (`…_last_owner_demotion`), `api/test_membership_exit.py` (`…_last_owner_cannot_leave`), `api/test_memberships.py`, `domain/test_role_rules.py`; `fe:` `MemberDialogs.test.tsx` | ✔ (incluye el evento `owner_protection.rejected`) |
| AC-TEN-14 | `test_membership_exit_race.py` (`test_AC_TEN_14_mutual_demotion_keeps_one_owner`, dos requests reales en paralelo) | ✔ |
| AC-TEN-15 | `domain/test_permission_matrix_active.py` (`…_matrix_admin_owner_actions`), `domain/test_role_rules.py`, `api/test_invitations_create.py`, `api/test_invitations_manage_refusals.py`, `api/test_membership_role.py`, `api/test_membership_exit.py` | ✔ |
| AC-TEN-16 | `domain/test_permission_matrix_active.py` (`…_matrix_operator_viewer`), `domain/test_role_rules.py` (`…_no_self_elevation`), `api/test_branches.py`, `api/test_branch_detail.py`, `api/test_invitations_create.py`, `api/test_membership_role.py` | ✔ |
| AC-TEN-17 | `test_invitation_accept.py` (`…_accept_creates_membership`), `test_invitation_accept_race.py` (`…_double_accept_in_parallel_by_another_account`), `api/test_invitation_accept_api.py`; Q-243: `test_Q_243_idempotent_accept.py`, `test_Q_243_double_accept_in_parallel_by_the_same_person`; `fe:` `AcceptInvitation.test.tsx`, `invitation-token.test.ts` | ✔ |
| AC-TEN-18 | `test_invitation_accept.py` (`…_other_email_keeps_pending`), `api/test_invitation_accept_api.py`, `domain/test_invitations.py` | ✔ |
| AC-TEN-19 | `test_invitation_accept.py` (`…_expired_or_revoked`), `api/test_invitation_accept_api.py`, `domain/test_invitations.py` | ✔ |
| AC-TEN-20 | `api/test_invitations_create.py` (`…_already_member`) | ✔ |
| AC-TEN-21 | `api/test_organizations.py` (`…_no_org_creation_via_api`, `…_anonymous_post_is_401_before_405`) | ✔ |
| AC-TEN-22 | `commands/test_create_org.py` (`…_org_without_memberships_plus_invitation`, `…_accept_gives_one_owner`), `scripts/tests/test_e2e_tenancy.py`; E2E real §3 (`[org-A]`, `[owner-A]`) | ✔ |
| AC-TEN-23 | `test_audit.py` (`…_event_carries_actor_action_organization_and_date`, `…_catalog_equals_spec_list`), `ct:test_action_kinds.py` (`…_every_write_route_emits_its_event`), `test_audit_triggers.py`, comandos de soporte y recuperación | ✔ |
| AC-TEN-24 | `api/test_invitations_create.py` (`…_token_only_in_create_response`), `api/test_invitations_manage.py` (`…_old_token_is_invalid`), `api/test_invitations_list.py` (`…_list_has_no_token`), aceptación: `api/test_invitation_accept_api.py` (`test_RNF_TEN_03_token_and_email_never_reach_the_logs`); `fe:` `InviteDialog.test.tsx`, `InvitationDialogs.test.tsx`, `useInvitations.test.ts` | ✔ (crear, reenviar y aceptar, con logs, errores, eventos y listado) |
| AC-TEN-25 | `test_invitation_accept.py` (`…_at_seven_days`), `domain/test_invitations.py`, `test_my_invitations_commit.py` | ✔ |
| AC-TEN-26 | `api/test_invitations_create.py` (`…_second_pending_rejected`), `api/test_invitations_manage.py` (`…_resend_revokes_old_and_renews`, `…_new_token_is_accepted_for_seven_days`), `test_invitation_create.py` (`…_two_creations_at_once_leave_one_pending`), `test_invitation_manage_race.py` | ✔ |
| AC-TEN-27 | `api/test_membership_role.py` (`…_transfer_ownership`), `api/test_memberships.py`, `domain/test_role_rules.py` | ✔ |
| AC-TEN-28 | `ct:test_action_kinds.py` (`…_every_write_case_is_409_when_suspended`, `…_reads_pass_when_suspended`), `test_AC_TEN_28_locks.py`, `test_AC_TEN_28_lock_races.py` (`…_suspend_waits_for_write_in_flight`), `test_AC_TEN_28_tasks.py` (`…_system_task_runs_on_suspended_org`), aceptar invitación: `api/test_my_invitations_api.py` (`…_accept_from_session_is_409`), `api/test_invitation_accept_api.py`; `fe:` `useBranches.test.tsx` | ⚠ lectura y bloqueo de escrituras, completos. **Falta** la cláusula "un evento servidor-a-servidor sobre un cobro `pending` de A se sigue procesando": no hay cobros (SPEC-06/07). Se probó el mecanismo con una `TenantTask` de prueba (`tenant_probe`) con actor sistema sobre una organización suspendida, como planificó `tasks.md` (T-TEN-11). El cobro en sí no se puede verificar todavía |
| AC-TEN-29 | `api/test_current_organization.py` (`…_status_is_not_writable`, `…_owner_of_a_suspended_one_cannot_reactivate_it`), `commands/test_set_org_status.py` | ✔ |
| AC-TEN-30 | `api/test_branch_lifecycle.py` (`…_deactivate_keeps_the_branch`, `…_no_physical_delete`, `…_reactivate_with_taken_name`), `api/test_branches.py` (`…_inactive_listed`), `api/test_branch_detail.py` (`…_no_delete_route`); `fe:` `BranchFormDialog.test.tsx` | ✔ (incluye `branch.deactivated`) |
| AC-TEN-31 | `api/test_membership_exit.py` (`…_leave_then_reinvite_is_new_membership`); `fe:` `MemberDialogs.test.tsx`, `MembersLeave.test.tsx` | ✔ |
| AC-TEN-32 | `api/test_branch_filter.py` (`…_operator_filters_any_branch`) | ✔ |
| AC-TEN-33 | `api/test_resolution.py` (`…_superuser_without_membership`), `ct:test_routes.py` (`…_superuser_body_identical`) | ✔ |
| AC-TEN-34 | `api/test_invitations_list.py` (`…_operator_cannot_list`, `…_viewer_cannot_list`), `api/test_memberships.py`, `domain/test_permission_matrix_*.py`; `fe:` `MembersTable.test.tsx`, `InvitationsTable.test.tsx` | ✔ |
| AC-TEN-35 | `test_invitation_accept.py` (`…_case_and_alias`), `domain/test_invitations.py`, `test_invitation.py`, `test_invitation_port_contract.py` | ✔ |
| AC-TEN-36 | `api/test_membership_exit_invitations.py` (`…_auto_revoked_on_demotion_revoke_and_leave`), `api/test_membership_role.py`, `test_membership_exit_race.py` (los dos órdenes con la aceptación) | ✔ |
| AC-TEN-37 | `test_AC_TEN_37_invitation_expiry.py` (`…_expiry_task_emits_system_event`), `api/test_branch_lifecycle.py` (`…_reactivate_active_is_invalid_transition`), `api/test_invitations_manage_refusals.py`, `test_invitation_manage_race.py`, `commands/test_owner_invite.py`, `commands/test_set_org_status.py` | ✔ |
| AC-TEN-38 | `api/test_branches.py` (`…_name_case_insensitive_and_code`, `…_inactive_frees_values`, `…_other_org_accepts`), `api/test_branch_detail.py`, `test_branch.py` (restricciones de BD) | ✔ |
| AC-TEN-39 | `api/test_my_invitations_api.py` (`…_lists_only_my_email`, `…_expired_and_suspended_are_not_listed`, `…_response_has_no_token`, `…_foreign_and_missing_same_body`, `…_foreign_attempt_is_audited`), `test_my_invitations_commit.py`, `test_invitation_session_scopes.py`; `fe:` `PendingInvitationsNotice.test.tsx`, `useMyInvitations.test.ts`; `scripts/tests/test_e2e_tenancy.py`; E2E real §3 (`[mine]`, `[accept-other-email]`, `[accept-from-session]`) | ✔ |
| AC-TEN-40 | `commands/test_create_org.py` (`…_existing_user_gets_invitation_not_membership`, `…_next_login_does_not_accept`, `…_accept_from_session_gives_one_owner`) | ✔ |

**Resumen:** 39 ✔ · 1 ⚠ (AC-TEN-28) · 0 ✘ · 40 AC. `AC-CHG-13`: cita a SPEC-06, fuera de la matriz.

## 2. Ejecución (2026-11-26, commit `5536088`)

Las mismas corridas que `specs/01-identity-access/verification.md §2`: son una sola suite.

| Suite | Comando | Resultado |
|---|---|---|
| Backend completo (unit + integration), PostgreSQL y Redis reales | `pytest` en la imagen `centro-pagos-backend:dev` con el worktree montado en `/repo`, `config.settings.test`, `TZ=UTC`, BD `ver-pg` y Redis `ida00-redis` descartables | ✔ **3342 passed**, 0 skipped, 0 failed, 518 s. De esos, 1639 están en `tests/tenancy/` y 1196 llevan `AC_TEN` en el nombre (incluye `tests/cross_tenant/` y `tests/architecture/`) |
| Frontend | `corepack enable && pnpm install --frozen-lockfile && pnpm test` en `node:24.22.2-trixie-slim` | ✔ 72 archivos, **631 passed** |
| Tipos frontend | `pnpm typecheck` | ✔ exit 0 |
| Tipos backend y scripts | `mypy --no-incremental . ../scripts` en la imagen | ✔ `no issues found in 509 source files` |
| Scripts | host: `python -m pytest -c scripts/pytest.ini scripts/tests` · imagen: `test_AC_PLT_12_ruff_print.py` | ✔ 924 passed en el host más los 7 de `ruff` en la imagen (el host no tiene `ruff`; problema conocido, no es de 02). 22 deselected (`gitleaks`) |
| Lint | `ruff check .` y `ruff format --check .` (`ruff 0.17.3`) | ✔ |
| Migraciones | `makemigrations --check --dry-run`, `lint_migrations` y `check_migrations_roundtrip --allow-data-loss` contra una BD creada para esto y borrada después | ✔ `Round trip passed for 2 app(s): identity, tenancy` |
| Estado | `python scripts/check_spec_state.py` | ✔ `OK: sin drift` |
| CI sobre el mismo commit | workflow `ci`, run `45900649873` | ✔ 10/10 jobs |
| Pre-commit | `pre-commit run --all-files` | **pendiente**: no está instalado en el host. Lo cubren `ruff` y el job `lint` del run `45900649873` |

## 3. Corrida real del E2E (`scripts/e2e_tenancy.py`, T-TEN-36)

- **Fecha:** 2026-11-26. Corrió sobre el stack descartable del E2E de login (`specs/01-identity-access/verification.md
  §3`): proyecto `hub-e2e-ver`, imágenes `runtime` de `5536088`, `config.settings.dev`, proveedor falso, `backend` en
  `127.0.0.1:18432` y `frontend` en `127.0.0.1:13432`. `FRONTEND_BASE_URL` igual a `HUB_APP_ORIGIN` y
  `PLATFORM_OPERATOR_EMAILS=ops@example.test`, ficticios y en línea.
- **Comando:** `python scripts/e2e_tenancy.py --operator ops@example.test --frontend-url http://127.0.0.1:13432
  --provider-url http://127.0.0.1:18432 --manage "docker compose -p hub-e2e-ver exec -T backend python manage.py"`.
- **Salida:** `e2e ok [org-A]` · `[owner-A]` · `[branch-A]` · `[invite-operator]` · `[operator-A]` · `[operator-branches]`
  · `[org-B]` · `[org-C]` · `[owner-B]` · `[invite-B]` · `[suspend-C]` · `[mine]` · `[accept-other-email]` ·
  `[accept-from-session]` · `[two-orgs]` · `e2e passed`, código 0.
- **Estado de la BD después** (solo conteos): 3 organizaciones (2 `active`, 1 `suspended`); memberships `owner` 2,
  `operator` 1 y `viewer` 1, todas `active`; invitaciones: 4 `accepted` y 2 `pending` (la de C, suspendida, y la de otro
  email); 1 sucursal; 4 usuarios, contando el del E2E de login.
- **Logs:** 25 `audit.event` en total entre los dos E2E (entre ellos `invitation.created` 3, `invitation.accepted` 4,
  `membership.created` 4, `branch.created` 1 e `invitation.rejected` 1). Los eventos de los comandos del operador salen
  por la salida del comando, que el script no imprime. Ningún email, token, `#token=` ni credencial en los logs de los
  servicios (barrido de §3 de 01).
- **Limpieza:** `down -v`. Se borraron el archivo Compose y las claves.

**Límites:** no corre en CI (misma razón que el de login, Q-063). Es por HTTP, sin navegador: no ve el render de las
pantallas (§5).

## 4. Pruebas transversales

- [x] **Aislamiento entre organizaciones:** recurso de otra organización → `404` por ID, en filtros y en listados
  (AC-TEN-01, 02, 09); organización ajena igual que inexistente, también para staff (AC-TEN-03, 33); el cuerpo no puede
  elegir organización (AC-TEN-07); fallo cerrado sin scope (AC-TEN-10, 11); test parametrizado de todas las rutas
  registradas (AC-TEN-12).
- [x] **Idempotencia / repetición:** la misma persona repite la aceptación y recibe la respuesta de éxito sin escribir
  (Q-243, AC-TEN-17); repetir `tenancy_create_org` con la misma `--key` no duplica y se audita (Q-235); la tarea de
  vencimiento no hace nada si ya no hay vencidas (`test_AC_TEN_37_expiry_task_is_a_noop_once_no_longer_due`).
- [x] **Duplicados:** una sola `pending` por email, también con dos creaciones a la vez (AC-TEN-26); un solo uso del
  token entre cuentas, también en paralelo (AC-TEN-17); `409 conflict` por nombre o `code` entre sucursales activas
  (AC-TEN-38).
- [x] **Orden de eventos:** degradación mutua de dos owners en paralelo (AC-TEN-14); aceptar antes o después de revocar
  a quien invitó (AC-TEN-36); gestionar antes o después de aceptar (AC-TEN-26, 37); la suspensión espera a la escritura
  en curso, y la escritura posterior la ve (AC-TEN-28); aceptar desde la sesión contra revocar (AC-TEN-39).
- [x] **Permisos por rol:** matrices completas con la organización activa y suspendida
  (`domain/test_permission_matrix_active.py`, `…_suspended.py`), AC-TEN-15, 16 y 34, protección del último owner
  (AC-TEN-13) y sin autoelevación (AC-TEN-16).
- [x] **Sin secretos ni PII en logs y respuestas:** AC-TEN-24, RNF-TEN-03 y el barrido de logs del E2E.
- [x] **Migraciones aplican y revierten:** `check_migrations_roundtrip` (§2).
- [ ] **Evento servidor-a-servidor sobre una organización suspendida:** solo con la tarea de prueba (AC-TEN-28, ⚠).

## 5. Validación funcional manual (la hace el dueño)

Lo que `design.md §9` deja como manual (fila "E2E / manual"). Requisito: el stack de desarrollo con el proveedor falso
(`infra/README.md`, "E2E del login") y una empresa creada con `tenancy_create_org`.

1. **Selector con dos pestañas en empresas distintas:** con un usuario en A y en B, abrir A en una pestaña y B en otra.
   Cada pestaña opera sobre su empresa; cambiar en una no cambia la otra.
2. **Estados de "Aceptar invitación"** (`/invitacion#token=…`): vigente (se acepta y entra a la empresa), vencida,
   revocada, ya usada por otra cuenta, otro email, empresa suspendida y sin token. Cada rechazo muestra su estado y un
   único botón "Ir a Inicio" (Q-233); una falla de red ofrece "Reintentar".
3. **Banner de empresa suspendida:** con `tenancy_set_org_status` suspender A; el owner ve el aviso, puede listar
   Sucursales y datos de la empresa, y no se le ofrecen acciones de escritura (AC-TEN-28, UI).
4. **E2E por HTTP**, reproducible: §3. Resultado esperado: `e2e passed`, código 0.
5. **Decidir la cláusula s2s de AC-TEN-28:** aceptar como evidencia la prueba con la tarea de prueba hasta que exista
   SPEC-06/07, o pasar la cláusula a SPEC-06 como referencia cruzada (como `AC-CHG-13`), con entrada en el "Historial de
   cambios".
6. **Q-229 sigue abierta** (`clarifications.md`): `full_clean()` / `validate_unique()` y el `UniqueValidator` de DRF
   fallan con `TenantScopeError` en los modelos de tenant. Hoy ningún código los usa (no bloquea 02), pero el primer
   módulo que los use daría `500`. Hay que asignarla al architect antes de SPEC-04.

## 6. Revisión de código (reviewer)

| Severidad | Hallazgo | Archivo:línea | Regla | Estado |
|---|---|---|---|---|
| — | Falta la revisión del diff acumulado del módulo (paso 2 de `/verify`) | — | C-15 | Pendiente |

Cada PR de 02 tuvo veredicto del `reviewer` con SHA y el label `zona-roja` (`tasks.md`, columna Evidencia).

## 7. Hallazgos

1. **AC-TEN-28 ⚠:** la cláusula del evento servidor-a-servidor sobre un cobro `pending` no se puede verificar sin
   SPEC-06/07. Sí está verificado el mecanismo que la sostiene (tarea con actor sistema sobre organización suspendida).
2. **Q-229 abierta** (§5, paso 6). No bloquea 02.
3. **Validación manual de la UI sin hacer** (§5, pasos 1 a 3).
4. **`scripts/spec_state_baseline.json` desactualizado:** `allow_missing_tests` de `02-tenancy-rbac` sigue con los 40
   `AC-TEN` que ya tienen test (debería quedar solo `AC-CHG-13`). No da drift, pero si se borrara el test de uno de esos
   AC, el chequeo no lo detectaría. Lo corrige `project-steward`.
5. **Revisión del diff acumulado** pendiente (§6).

## 8. Decisión

**Con hallazgos. No marcar `Verified` todavía.** 39 de 40 AC quedan ✔ con la suite completa en verde sobre `5536088`. El
único ⚠ no es una tarea sin hacer: depende de un módulo que todavía no existe.

| Acción | Quién | Qué desbloquea |
|---|---|---|
| Decidir la cláusula s2s de AC-TEN-28 (§5, paso 5) | dueño | AC-TEN-28 |
| Validación manual de la UI (§5, pasos 1 a 3) | dueño | AC-TEN-08, 22 y 28 en pantalla (`design.md §9`) |
| Asignar Q-229 | dueño / architect | riesgo para SPEC-04 en adelante, no para 02 |
| Revisar el diff acumulado de 01 y 02 (§6) | `reviewer` | cierre del módulo |

No hay tareas para reabrir. Cuando esto se resuelva, las filas de `tasks.md` pasan a `🧪` y el dueño decide `Verified`,
junto con SPEC-01 (Q-108).
