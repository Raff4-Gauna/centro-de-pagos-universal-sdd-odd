---
id: SPEC-02
modulo: tenancy-rbac
estado: Draft            # Draft | Clarified | Designed | Approved | Implemented | Verified
track: S
version: 0.1.0
depende_de: [SPEC-00, SPEC-01]
actualizado: 2026-10-31
---

# Módulo de Organizaciones, Sucursales y Roles (tenancy + RBAC)

## 1. Contexto y problema
El Hub es multi-organización (Q-001: multi-tenant real, operado por el dueño de la plataforma, sin registro público).
Cada organización es dueña de sus integraciones, sucursales, cobros y reportes, y un usuario puede pertenecer a
varias (glosario). Una fuga entre organizaciones o un permiso mal evaluado expone dinero y datos de terceros: es
el riesgo "fuga entre organizaciones" del brief §8. Este módulo fija la raíz del aislamiento (`C-01`) que reusan
todos los demás módulos y la matriz de roles de Q-010.

## 2. Objetivo
Permitir que cada usuario opere **solo** dentro de las organizaciones donde tiene una `Membership` vigente, con los
permisos de su rol en esa organización, validado por el backend en **cada** request, y que ninguna lectura o
escritura de negocio pueda saltear el filtro por `organization_id` sin que un test automático lo detecte.

## 3. Alcance
### 3.1 Incluido
- `Organization` (tenant): alta **solo** por el operador de la plataforma, datos de la empresa, estado (Q-208).
- `Membership` usuario ↔ organización con rol `owner` / `admin` / `operator` / `viewer`.
- `Invitation`: sumar usuarios a una organización por email (Q-012).
- `Branch` (sucursal local del Hub): alta, edición, consulta y baja (Q-211).
- Resolución de la **organización activa** por request (elegida en el selector, `context/07-frontend-ui-guidelines.md §5.1`)
  y su revalidación contra `Membership` en cada request.
- Managers/selectors tenant-aware y utilidad de permisos por rol, reutilizables por todos los módulos.
- Test cross-tenant obligatorio por endpoint y test de arquitectura que prohíbe accesos crudos (`C-01`).
- Matriz de permisos de las acciones de este módulo (§4) y lista de eventos que debe auditar SPEC-10.
- Pantallas de Configuración: "Colaboradores", "Datos de la empresa", "Sucursales"; aceptación de invitación.

### 3.2 Fuera de alcance
- Login con Google, emisión/renovación/revocación de JWT, sesión y cookie `httpOnly` (SPEC-01, ADR-0004).
- Integraciones, credenciales y el **vínculo Branch ↔ Store / caja ↔ POS** (SPEC-04/05). Este módulo solo exige
  que ese vínculo pertenezca a la misma organización que la Branch (RN-TEN-15).
- Cajas (POS) y terminales: no se modelan acá (ver contradicción 4 en `clarifications.md`).
- API keys y scopes del ERP (SPEC-11); este módulo solo declara qué lecturas necesitaría el ERP (Q-216).
- Almacenamiento y consulta del log de auditoría (SPEC-10); acá solo se enumeran los eventos (RNF-TEN-04).
- Activación de RLS de PostgreSQL como segunda barrera (ADR-0001, Q-215): solo se exige no impedirla.
- Registro público, autoalta de organizaciones, planes, facturación, límites comerciales.
- Roles personalizados o permisos por usuario individual; permisos por sucursal (salvo decisión en Q-204).
- Mecanismo técnico concreto (header vs cookie, middleware, nombres de clases): lo decide `design.md`.

## 4. Actores y permisos
Actores: los 4 roles de `Membership`; **operador de la plataforma** (quien opera el Hub, Q-001, representación en
Q-212); **usuario autenticado** sin membership en la organización; **ERP** (API key, SPEC-11).

| Acción | owner | admin | operator | viewer | ERP (API key) | Operador plataforma |
|---|---|---|---|---|---|---|
| Crear organización | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ (Q-212) |
| Suspender / reactivar organización | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ (Q-208) |
| Listar mis organizaciones y mi rol en cada una | ✔ | ✔ | ✔ | ✔ | ✘ | — |
| Elegir organización activa (solo con membership vigente) | ✔ | ✔ | ✔ | ✔ | ✘ (org fija de la key) | — |
| Ver datos de la organización activa | ✔ | ✔ | ✔ | ✔ | ✘ (Q-216) | — |
| Editar datos de la organización | ✔ | ✔ (Q-209) | ✘ | ✘ | ✘ | — |
| Listar miembros e invitaciones pendientes | ✔ | ✔ | ✘ (Q-218) | ✘ (Q-218) | ✘ | — |
| Invitar / asignar rol admin, operator o viewer | ✔ | ✔ | ✘ | ✘ | ✘ | — |
| Invitar / asignar o quitar rol owner | ✔ | ✘ (Q-202) | ✘ | ✘ | ✘ | — |
| Revocar membership de otro (no owner) | ✔ | ✔ | ✘ | ✘ | ✘ | — |
| Revocar membership de un owner | ✔ (Q-201) | ✘ (Q-202) | ✘ | ✘ | ✘ | — |
| Abandonar la organización (uno mismo) | ✔ (Q-201) | ✔ (Q-203) | ✔ (Q-203) | ✔ (Q-203) | ✘ | — |
| Revocar / reenviar invitación pendiente | ✔ | ✔ (Q-202) | ✘ | ✘ | ✘ | — |
| Aceptar invitación | el usuario autenticado cuyo email coincide con la invitación (Q-206) |||||
| Ver sucursales de la organización | ✔ | ✔ | ✔ | ✔ | ✔ lectura (Q-216) | — |
| Crear / editar / dar de baja sucursal | ✔ | ✔ | ✘ | ✘ | ✘ | — |

Fuentes: Q-010 y brief §5 (owner/admin configuran sucursales y usuarios; operator cobra; viewer lee),
`context/07 §5.3` (operator ve sucursales en lectura). Marcas `(Q-xxx)` = pendiente de confirmar. Acción no listada
→ denegada (RN-TEN-09).

## 5. Glosario del módulo
- **Organización activa**: la organización elegida por el usuario en el selector para una request; es un dato que
  manda el cliente y que el backend **revalida** siempre (no es una autorización por sí misma).
- **Membership vigente**: membership en estado activo de una organización no suspendida (estados en Q-208/Q-214).
- **Endpoint tenant-scoped**: todo endpoint que lee o escribe datos de una organización.
- **Invitation**: oferta de membership a un email, con rol, de un solo uso (vigencia en Q-206).
- **Operador de la plataforma**: quien administra el Hub; no es un rol de `Membership` (Q-212).

## 6. Reglas de negocio
- **RN-TEN-01** Toda entidad de negocio lleva `organization_id`; `Organization` es la raíz. `Membership`,
  `Invitation` y `Branch` pertenecen a exactamente una organización (`C-01`).
- **RN-TEN-02** Toda lectura/escritura de datos de negocio pasa por managers/selectors tenant-aware; está prohibido
  el acceso crudo (`Model.objects` sin filtro) desde servicios de negocio. Una consulta de negocio sin organización
  explícita **falla cerrada**: no devuelve datos de ninguna organización (`C-01`).
- **RN-TEN-03** Cada request a un endpoint tenant-scoped indica una organización activa. El backend verifica en
  **cada** request que el usuario tenga una membership vigente en ella; el resultado no se reutiliza entre
  requests. El selector de UI nunca es fuente de autorización (`context/07 §5.1`, `context/08 §8`).
- **RN-TEN-04** La organización de una escritura sale **siempre** del contexto validado (RN-TEN-03), nunca de un
  campo del cuerpo, de la query ni de la URL elegida por el cliente.
- **RN-TEN-05** Pedir por ID un recurso de otra organización responde igual que si no existiera (`404`); los
  listados nunca incluyen recursos de otra organización (mismo criterio que AC-CHG-13).
- **RN-TEN-06** Una organización activa inexistente o sin membership vigente del usuario se rechaza con una
  respuesta **indistinguible** entre ambos casos, sin datos ni efectos (código en Q-219).
- **RN-TEN-07** Un usuario puede tener memberships en varias organizaciones (glosario), pero **a lo sumo una** por
  organización, con exactamente un rol de {`owner`, `admin`, `operator`, `viewer`}. El rol es por organización.
- **RN-TEN-08** Los permisos se evalúan con el rol **vigente** de la membership al momento de la request: un cambio
  de rol o una revocación rige desde la request siguiente, aunque la sesión/JWT del usuario siga vigente.
- **RN-TEN-09** La matriz §4 es la única fuente de permisos de este módulo; toda acción no listada para un rol se
  deniega (`403`). Ningún usuario puede elevar su propio rol.
- **RN-TEN-10** Solo el operador de la plataforma crea organizaciones; no existe registro público ni endpoint de
  autoalta para usuarios (Q-001). Mecanismo y primer owner: Q-212, Q-213.
- **RN-TEN-11** Los usuarios se suman a una organización solo aceptando una invitación por email (Q-012); la
  aceptación exige estar autenticado (SPEC-01).
- **RN-TEN-12** Una invitación se acepta una sola vez, dentro de su vigencia, solo por el usuario cuyo email
  coincide (Q-206); aceptarla crea la membership con el rol de la invitación. Invitar a quien ya es miembro vigente
  se rechaza (RN-TEN-07).
- **RN-TEN-13** Un invitador solo puede invitar o asignar roles que la matriz §4 le permite (Q-202).
- **RN-TEN-14** *(pendiente Q-201)* La organización conserva siempre al menos un `owner` vigente: degradar, revocar
  o hacer abandonar al último owner se rechaza, también bajo concurrencia.
- **RN-TEN-15** Una `Branch` es una sucursal **local** del Hub (≠ Store de MP). Todo vínculo de una Branch con una
  integración, Store o caja (SPEC-04/05) pertenece a la misma organización que la Branch.
- **RN-TEN-16** La sucursal elegida en el selector es un **filtro** dentro de la organización activa: se valida que
  pertenezca a ella; no es frontera de autorización salvo decisión distinta en Q-204.
- **RN-TEN-17** Toda acción sensible de este módulo queda auditada con quién, qué, cuándo y organización (`C-08`;
  lista en RNF-TEN-04).

## 7. Requisitos funcionales
- **RF-TEN-01** Resolver y validar la organización activa en cada request tenant-scoped y exponer ese contexto
  (usuario, organización, rol) a servicios y selectors. (RN-TEN-03…06, 08)
- **RF-TEN-02** Listar las organizaciones del usuario con su rol en cada una. (RN-TEN-07)
- **RF-TEN-03** Ver y editar los datos de la organización activa (campos en Q-209). (§4)
- **RF-TEN-04** Gestionar memberships: listar, cambiar rol, revocar, abandonar. (RN-TEN-07, 09, 13, 14)
- **RF-TEN-05** Invitaciones: crear, listar pendientes, revocar, reenviar, aceptar. (RN-TEN-11…13)
- **RF-TEN-06** Sucursales: crear, listar, ver, editar, dar de baja (forma de baja en Q-211). (RN-TEN-15, 16)
- **RF-TEN-07** Alta de organización por el operador de la plataforma, con designación del primer owner.
  (RN-TEN-10; Q-212, Q-213)
- **RF-TEN-08** Proveer managers/selectors tenant-aware y la verificación de permisos por rol para que los demás
  módulos (04, 06, 07, 08, 09, 11) los reutilicen. (RN-TEN-01, 02, 09)
- **RF-TEN-09** Emitir los eventos de auditoría de RNF-TEN-04 hacia el módulo 10. (RN-TEN-17)

## 8. Requisitos no funcionales
- **RNF-TEN-01 Seguridad / pruebas:** cada endpoint tenant-scoped (de este y de todo módulo) tiene un test
  cross-tenant; un test de arquitectura prohíbe accesos crudos en servicios de negocio (`C-01`, `C-11`).
- **RNF-TEN-02 Observabilidad:** todo log de request tenant-scoped incluye `organization_id` validado (`C-16`). Un
  rechazo por organización o permiso se loguea con `request_id`, usuario y organización pedida.
- **RNF-TEN-03 Secretos:** el token de invitación tiene alta entropía, se guarda solo como hash, es de un solo uso y
  nunca aparece en logs, errores ni listados (`C-06`).
- **RNF-TEN-04 Auditoría (`C-08`, para SPEC-10):** `organization.created`, `organization.updated`,
  `organization.suspended` / `reactivated` (Q-208), `membership.created`, `membership.role_changed`,
  `membership.revoked`, `membership.left`, `invitation.created`, `invitation.resent`, `invitation.revoked`,
  `invitation.accepted`, `invitation.rejected` (email no coincide / vencida / usada), `branch.created`,
  `branch.updated`, `branch.deactivated` (Q-211), `owner_protection.rejected` (Q-201). Intentos denegados de acceso
  a otra organización: canal en Q-217.
- **RNF-TEN-05 Reversibilidad:** migraciones reversibles y probadas en ambos sentidos (`C-17`); el esquema no
  impide activar RLS más adelante (ADR-0001, Q-215).
- **RNF-TEN-06 Privacidad:** de un invitado se guarda solo el email; no se guarda PII adicional (`C-10`, Q-021).
- **RNF-TEN-07 Rendimiento:** la revalidación de membership no introduce consultas N+1 por request; el objetivo
  numérico lo fija `design.md`.

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `Organization` | id, name, status (Q-208), datos de empresa (Q-209), created_by (operador), timestamps | ≥1 owner vigente (Q-201) |
| `Membership` | id, organization, user, role, status (Q-214), invited_by, timestamps | única vigente por `(organization, user)`; `role` ∈ 4 valores |
| `Invitation` | id, organization, email (normalizado), role, token_hash, status, expires_at (Q-206), invited_by, accepted_by?, timestamps | un solo uso; unicidad de pendientes por `(organization, email)` en Q-206 |
| `Branch` | id, organization, name, campos en Q-210, estado activo/inactivo (Q-211), timestamps | pertenece a una sola organización; unicidad de nombre en Q-210 |

El vínculo Branch ↔ Store/integración vive en SPEC-04/05 y hereda RN-TEN-15.

## 10. Estados y transiciones
| Entidad | Desde | Evento | Hacia | Quién |
|---|---|---|---|---|
| Invitation | — | crear | `pending` | owner/admin (§4) |
| Invitation | `pending` | aceptar (email coincide, vigente) | `accepted` | usuario invitado |
| Invitation | `pending` | revocar / reenviar (Q-206) | `revoked` | owner/admin |
| Invitation | `pending` | vence `expires_at` | `expired` | sistema |
| Membership | — | aceptar invitación / alta de primer owner (Q-213) | `active` | usuario / operador |
| Membership | `active` | revocar / abandonar | `revoked` (Q-214) | owner/admin / el propio usuario |
| Organization | `active` ↔ `suspended` | suspender / reactivar | — | operador (Q-208) |
| Branch | activa ↔ inactiva | dar de baja / reactivar | — | owner/admin (Q-211) |

Terminales de Invitation: `accepted`, `revoked`, `expired`. Transición inválida → rechazada y auditada.

## 11. Contratos (nivel conceptual; detalle en `design.md`)
- `GET /api/organizations/` (mis organizaciones + rol) · `GET/PATCH /api/organizations/current/`.
- `GET /api/memberships/` · `PATCH /api/memberships/{id}/` (rol) · `DELETE /api/memberships/{id}/` (revocar) ·
  `POST /api/memberships/me/leave/`.
- `POST/GET /api/invitations/` · `POST /api/invitations/{id}/revoke/` · `POST /api/invitations/{id}/resend/` ·
  `POST /api/invitations/accept/` (con token; no requiere organización activa).
- `GET/POST /api/branches/` · `GET/PATCH /api/branches/{id}/` · baja según Q-211.
- Alta de organización: **sin endpoint público** (Q-212).
- Organización activa: viaja en cada request tenant-scoped (header o cookie: decide `design.md`).
- Interfaz interna: contexto de tenant (usuario, organización, rol) + selectors tenant-aware + verificación de rol.
- Errores normalizados: `organization_required`, `organization_not_found` (Q-219), `forbidden`, `not_found`,
  `validation_error`, `already_member`, `invitation_invalid`, `last_owner` (Q-201).

## 12. Casos límite y excepciones
- Usuario sin ninguna membership vigente: puede autenticarse (SPEC-01) pero no opera nada (pantalla en Q-205).
- Rol cambiado o membership revocada a mitad de sesión: rige desde la request siguiente (RN-TEN-08).
- Dos owners se degradan mutuamente a la vez siendo los únicos: a lo sumo uno prospera (RN-TEN-14).
- Invitación aceptada dos veces en paralelo: una sola membership (RN-TEN-07/12).
- Invitado que ya es miembro, o que es invitado desde dos organizaciones: cada organización es independiente.
- Branch dada de baja con cobros `pending` o vínculos a Store: Q-211 (06 §12 ya exige no cortar los `pending`).
- Organización suspendida con cobros `pending`: se siguen procesando eventos (06 §12); acceso de usuarios en Q-208.
- Procesos sin usuario (webhooks, poller, tareas Celery): fijan la organización del recurso que procesan antes de
  tocar datos de negocio; la forma de enumerar trabajo de varias organizaciones la define `design.md`.
- `branch_id` de otra organización usado como filtro: `404`, nunca datos (RN-TEN-05/16).
- Emails con mayúsculas/espacios: se normalizan antes de comparar (regla exacta en Q-206).

## 13. Criterios de aceptación
- **AC-TEN-01** (RN-TEN-05) **Dado** un usuario `owner` de A y una Branch de B **cuando** hace GET, PATCH o baja
  por su ID con A activa **entonces** `404`, sin cambios en B; y `GET /api/branches/` no incluye Branch de B.
- **AC-TEN-02** (RN-TEN-05) **Dado** un `owner` de A **cuando** opera por ID sobre una membership o invitación de
  B **entonces** `404` y nada cambia en B.
- **AC-TEN-03** (RN-TEN-03/06) **Dado** un usuario con membership solo en A **cuando** envía B como organización
  activa **entonces** el rechazo es idéntico (código y cuerpo) al de una organización inexistente, sin datos.
- **AC-TEN-04** (RN-TEN-03/08) **Dado** un `admin` de A con sesión válida **cuando** se revoca su membership y hace
  otra request con A activa **entonces** es rechazada aunque su JWT siga vigente.
- **AC-TEN-05** (RN-TEN-08) **Dado** un `admin` de A degradado a `viewer` **cuando** intenta editar una Branch en
  la request siguiente **entonces** `403`.
- **AC-TEN-06** (RN-TEN-03) **Dado** una request autenticada a un endpoint tenant-scoped **cuando** no indica
  organización activa **entonces** `organization_required` y ningún dato.
- **AC-TEN-07** (RN-TEN-04) **Dado** A activa **cuando** se crea una Branch enviando `organization_id` de B en el
  cuerpo **entonces** no existe ninguna Branch nueva en B.
- **AC-TEN-08** (RN-TEN-07) **Dado** un usuario `operator` en A y `viewer` en B **cuando** pide
  `GET /api/organizations/` **entonces** recibe exactamente A y B con esos roles y ninguna otra.
- **AC-TEN-09** (RN-TEN-16) **Dado** A activa **cuando** se filtra por un `branch_id` de B **entonces** `404`.
- **AC-TEN-10** (RN-TEN-02) **Dado** un servicio de negocio que usa el manager crudo de un modelo tenant-scoped
  **cuando** corre el test de arquitectura **entonces** el test falla señalando el archivo.
- **AC-TEN-11** (RN-TEN-02) **Dado** una consulta a un selector tenant-aware sin organización **entonces** se
  lanza error y no se devuelve ningún registro.
- **AC-TEN-12** (RNF-TEN-01) **Dado** el listado de rutas tenant-scoped registradas **cuando** corre el test
  cross-tenant parametrizado **entonces** cada ruta tiene caso; una ruta nueva sin caso hace fallar el test.
- **AC-TEN-13** (RN-TEN-14, Q-201) **Dado** A con un solo `owner` **cuando** se lo degrada, revoca o abandona
  **entonces** `last_owner`, la membership no cambia y queda evento `owner_protection.rejected`.
- **AC-TEN-14** (RN-TEN-14) **Dado** A con exactamente dos `owner` **cuando** se degradan mutuamente en paralelo
  **entonces** A termina con ≥1 owner vigente.
- **AC-TEN-15** (RN-TEN-13, Q-202) **Dado** un `admin` **cuando** invita con rol `owner`, asigna `owner` o revoca a
  un owner **entonces** `403` y nada cambia.
- **AC-TEN-16** (RN-TEN-09) **Dado** un `operator` o `viewer` **cuando** crea/edita/da de baja una Branch, invita
  o cambia un rol **entonces** `403`; y nadie puede elevar su propio rol.
- **AC-TEN-17** (RN-TEN-12) **Dado** una invitación `pending` a `x@dominio` con rol `operator` **cuando** la acepta
  el usuario autenticado con ese email **entonces** existe una membership `operator` y la invitación queda
  `accepted`; un segundo uso del mismo token → `invitation_invalid`.
- **AC-TEN-18** (RN-TEN-12, Q-206) **Dado** esa invitación **cuando** la intenta aceptar un usuario con otro email
  **entonces** `invitation_invalid`, sin membership, y la invitación sigue `pending`.
- **AC-TEN-19** (RN-TEN-12) **Dado** una invitación `expired` o `revoked` **cuando** se intenta aceptar
  **entonces** `invitation_invalid` y ninguna membership nueva.
- **AC-TEN-20** (RN-TEN-07/12) **Dado** un miembro vigente de A **cuando** se lo invita de nuevo a A
  **entonces** `already_member`.
- **AC-TEN-21** (RN-TEN-10) **Dado** cualquier usuario autenticado (incluso `owner`) **cuando** intenta crear una
  organización por la API **entonces** la cantidad de organizaciones no cambia.
- **AC-TEN-22** (RN-TEN-10, Q-212/213) **Dado** el operador de la plataforma **cuando** crea una organización
  **entonces** existe la organización, el primer owner queda designado según Q-213 y hay evento `organization.created`.
- **AC-TEN-23** (RN-TEN-17) **Dado** cada acción de RNF-TEN-04 **cuando** ocurre **entonces** se emite un evento
  con actor, acción, organización y fecha.
- **AC-TEN-24** (RNF-TEN-03) **Dado** la creación y aceptación de una invitación **entonces** el token en claro no
  aparece en logs, errores ni en `GET /api/invitations/`.

## 14. Interfaz de usuario
- **Selector empresa/sucursal** (shell en SPEC-00, `context/07 §5.1`): se alimenta de RF-TEN-02 y RF-TEN-06.
- **Configuración → Colaboradores**: miembros y rol, invitaciones pendientes, invitar, cambiar rol, revocar,
  reenviar; acciones visibles solo según §4.
- **Configuración → Datos de la empresa**: lectura para todos, edición según §4 (campos Q-209).
- **Configuración → Sucursales**: listado y alta/edición/baja para owner/admin; lectura para operator/viewer. Las
  cajas de esa pantalla las aporta SPEC-05.
- **Aceptar invitación**: tras login; estados válida / vencida / revocada / email no coincide.
- Estados de cada pantalla: cargando, vacío, error, sin permiso, "sin organización" (Q-205).

## 15. Riesgos y supuestos
- Supuesto: SPEC-01 entrega un usuario autenticado con email verificado por Google; el JWT **no** se usa como fuente
  de rol ni de membership (RN-TEN-08). Debe coordinarse con SPEC-01.
- Supuesto: modelos propios para Organization/Membership (Q-027, recomendación por defecto; ADR-0002 pendiente).
- Riesgo: un módulo futuro consulta sin selector → mitigación AC-TEN-10/12 en CI.
- Riesgo: ADR-0001 y ADR-0002 aún no están escritos y se necesitan antes del diseño de este módulo.

## 16. Preguntas abiertas
Ver `specs/02-tenancy-rbac/clarifications.md` (Q-201 a Q-219). Bloqueantes: Q-201, Q-202, Q-204, Q-206, Q-208,
Q-211, Q-212, Q-213. Decididas que aplican: Q-001, Q-006, Q-010 (`specs/00-platform/clarifications.md`).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial | Tenancy + RBAC sobre Q-001, Q-006, Q-010, Q-012, Q-027 |

---
**Hecho:** spec Draft con 17 RN, 9 RF, 7 RNF, 24 AC; matriz de permisos; eventos de auditoría para SPEC-10.
**Pendiente:** 19 preguntas (8 bloqueantes) en `clarifications.md`; ADR-0001/0002; coordinación con SPEC-01.
**Siguiente rol:** clarifier.
