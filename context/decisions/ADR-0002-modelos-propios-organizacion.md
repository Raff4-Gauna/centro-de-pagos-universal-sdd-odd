# ADR-0002 — Modelos propios para Organization, Membership, Invitation y Branch

- **Estado:** Propuesto
- **Fecha:** 2026-10-31
- **Specs afectadas:** SPEC-02 (dueña), SPEC-01 (usuario y puerto de invitación), SPEC-04/05 (vínculos a Branch),
  SPEC-06 (Branch en cobros), SPEC-10 (eventos), SPEC-11 (lectura de Branch). Decisiones: Q-027 (modelos propios),
  Q-201, Q-202, Q-206, Q-211, Q-213, Q-214.

## Contexto
La propuesta original mencionaba `django-organizations` y `django-saas`; Q-027 decidió modelos propios. Hay que
formalizar por qué y cómo, porque el modelo es zona roja (roles, aislamiento, migraciones) y las reglas de la spec
son más estrictas que las de esas librerías: a lo sumo una membership vigente por (organización, usuario) con
historial de revocadas (RN-TEN-07/21); al menos un owner vigente también bajo concurrencia (RN-TEN-14); invitaciones
de un solo uso, con token solo como hash, una sola `pending` por (organización, email), vencimiento de 7 días y
reenviar = revocar + emitir (RN-TEN-12); Branch sin borrado físico y nombre único entre activas (RN-TEN-19); usuario
propio de SPEC-01 (`AUTH_USER_MODEL` en `apps/identity`) y un puerto de invitación definido por SPEC-01.

## Opciones
1. **`django-organizations`.** Da Organization/OrganizationUser/Owner e invitaciones. Contras: modela un único
   owner por FK (choca con varios owners y transferencia, Q-202), borra en vez de revocar, invitaciones con su propio
   backend de tokens/email, sin constraints parciales ni locks; habría que reescribir la mitad y quedar atado a su
   esquema de migraciones. Dependencia nueva en zona roja (`C-13`).
2. **`django-saas` / kits SaaS similares.** Traen además planes, facturación y autoalta, explícitamente fuera de
   alcance (registro público prohibido, RN-TEN-10). Contras: superficie y dependencias que no se usan, mismo choque
   de reglas.
3. **`django-guardian` / `django-rules` para permisos.** Permisos por objeto o predicados genéricos. Contras: la
   matriz es por rol y por organización con reglas de destino (admin no toca owners); expresarla en tablas de
   permisos por objeto agrega consultas y oculta la regla; `rules` es liviano pero suma una dependencia para lo que
   son unas pocas funciones puras.
4. **Modelos y matriz propios** (elegida). Contras: más código propio que mantener y testear.

## Decisión
Opción 4. Detalle en `specs/02-tenancy-rbac/design.md` §3 y §5.

1. **Modelos** en `apps/tenancy/models/` con PK `UUID`, enums como `varchar` + `CheckConstraint`, y `NoHardDeleteMixin`
   (borrado físico prohibido en modelo y queryset; FK con `PROTECT`):
   - `Organization` (raíz; `status ∈ {active, suspended}`; `platform_creation_key` único para el alta idempotente por
     comando).
   - `Membership(TenantModel)`: FK a `settings.AUTH_USER_MODEL`; `role`; `status ∈ {active, revoked}`;
     `ended_reason ∈ {revoked, left}`; `source_invitation` único.
   - `Invitation(TenantModel)`: `email` normalizado; `token_hash` (SHA-256 de un token de 256 bits) único; `purpose ∈
     {standard, first_owner, support, owner_recovery}`; invitador = usuario **o** operador (check XOR).
   - `Branch(TenantModel)`: `is_active`; único `(organization_id, id)` para que SPEC-04/05 declaren FK compuestas
     (RN-TEN-15).
2. **Invariantes en la BD** (red final aunque falle el servicio): único parcial `(organization_id, user_id) WHERE
   status='active'`; único parcial `(organization_id, email) WHERE status='pending'`; único parcial
   `(organization_id, name) WHERE is_active`; coherencia de estado/fin por `CheckConstraint`; email normalizado por
   `CheckConstraint`. Un `IntegrityError` de estas constraints se traduce al error de negocio (`invitation_pending`,
   `already_member`, `validation_error`).
3. **Concurrencia de RN-TEN-14 y de invitaciones**: toda operación que cambia memberships o invitaciones de una
   organización toma primero `SELECT … FOR NO KEY UPDATE` sobre la fila de `Organization` ("mutex de membership"),
   luego `FOR UPDATE` sobre la fila destino, y recién ahí cuenta owners y decide con `domain/role_rules.py`. Orden
   fijo de locks (organización → fila; varias organizaciones en orden de `id`) para evitar deadlocks. Este lock no
   bloquea las escrituras de negocio (que toman `FOR KEY SHARE`, ADR-0001) y sí se serializa con suspender/reactivar
   (`FOR UPDATE`). Se descarta contar owners con `FOR UPDATE` sobre las filas de owners: correcto pero sutil en
   `READ COMMITTED` (filas que cambian de rol durante la espera).
4. **Matriz y reglas propias** en `apps/tenancy/domain/` (sin Django): `TENANCY_ACTIONS` (rol × acción × tipo) y
   funciones `decide_*` para las reglas de destino; test que transcribe la matriz de la spec celda por celda.
5. **Relación con SPEC-01**: `Membership.user` es FK a `AUTH_USER_MODEL`; el email que se compara al aceptar es el
   del usuario autenticado (verificado por Google), normalizado igual que el de la invitación. `apps/tenancy`
   implementa el puerto de invitación de SPEC-01 (`TenancyInvitationPort`: `find_valid_invitations`,
   `accept_invitations`) y el selector de memberships activas que usa `GET /api/me`; ambos se registran por settings
   para que `apps/identity` no importe `apps/tenancy`. La aceptación (por token o por el puerto) comparte un único
   servicio con las mismas validaciones y locks.
6. **Token de invitación**: generado con `secrets`, guardado solo como hash, mostrado una vez (respuesta de
   crear/reenviar o stdout del comando), entregado en el fragmento de la URL (`#token=`) para que no llegue a access
   logs ni `Referer`.

## Consecuencias
- Se gana: las reglas de la spec quedan como constraints y funciones puras testeables; sin dependencias nuevas en
  zona roja; el esquema es el que necesitan RLS (ADR-0001) y las FK compuestas de SPEC-04/05.
- Se paga: mantener modelos, migraciones y el flujo de invitaciones propios; el mutex por organización serializa los
  cambios de membership (operaciones raras y cortas).
- Pendiente: firma final del puerto de SPEC-01 y si su aceptación "atómica" es todo-o-nada o "las válidas en una
  transacción" (el diseño implementa lo segundo); unicidad de nombre de Branch sin distinguir mayúsculas (Q-226) y
  unicidad de `code` (Q-227); confirmar Q-222/Q-224 antes de implementar los comandos de soporte y recuperación.
