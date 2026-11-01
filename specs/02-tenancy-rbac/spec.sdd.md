---
id: SPEC-02
modulo: tenancy-rbac
estado: Designed         # Draft | Clarified | Designed | Approved | Implemented | Verified
track: S
version: 0.3.0
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
- `Organization` (tenant): alta **solo** por el operador de la plataforma (comando de gestión, Q-212), datos de la
  empresa (Q-209), estados `active` / `suspended` (Q-208).
- `Membership` usuario ↔ organización con rol `owner` / `admin` / `operator` / `viewer`, estados `active` / `revoked`
  (Q-214).
- `Invitation`: sumar usuarios a una organización por email (Q-012). Implementa el **puerto de invitación** que
  define SPEC-01 (Q-108 de 01).
- `Branch` (sucursal local del Hub): alta, edición, consulta, desactivación y reactivación; sin borrado físico (Q-211).
- Resolución de la **organización activa** por request: viaja en un **header** de cada request tenant-scoped,
  elegida en el selector (`context/07-frontend-ui-guidelines.md §5.1`), y se revalida contra `Membership` en cada
  request.
- Selector de memberships activas del usuario, que reutiliza `GET /api/me` de SPEC-01.
- Managers/selectors tenant-aware y utilidad de permisos por rol, reutilizables por todos los módulos.
- Test cross-tenant obligatorio por endpoint y test de arquitectura que prohíbe accesos crudos (`C-01`).
- Matriz de permisos de las acciones de este módulo (§4, §4.1) y lista de eventos que debe auditar SPEC-10.
- Pantallas de Configuración: "Colaboradores", "Datos de la empresa", "Sucursales"; aceptación de invitación.

### 3.2 Fuera de alcance
- Login con Google, emisión/renovación/revocación de JWT, sesión y cookie `httpOnly` (SPEC-01, ADR-0004). El JWT no
  lleva rol, organización ni membership (acordado con SPEC-01).
- Integraciones, credenciales y el **vínculo Branch ↔ Store / caja ↔ POS** (SPEC-04/05). Este módulo solo exige
  que ese vínculo pertenezca a la misma organización que la Branch (RN-TEN-15).
- La entidad local **Caja** y las terminales: no se modelan acá; dueño a definir en SPEC-04/05 (Q-220, no bloquea 02).
- API keys y scopes del ERP (SPEC-11); este módulo solo declara que el ERP necesita leer Branch (Q-216).
- Almacenamiento y consulta del log de auditoría (SPEC-10); acá solo se enumeran los eventos (RNF-TEN-04).
- Activación de RLS de PostgreSQL como segunda barrera (ADR-0001): se activa antes de onboardear comercios ajenos
  (Q-215); acá solo se exige que el esquema no la impida.
- Registro público, autoalta de organizaciones, planes, facturación, límites comerciales.
- Roles personalizados, permisos por usuario individual y **permisos por sucursal** (Q-204: no en el MVP).
- Proveedor de email transaccional (Q-207: dependencia nueva → ADR cuando se incorpore; en dev, consola).
- Mecanismo técnico concreto (nombre del header, middleware, clases, locks): lo decide `design.md`.

## 4. Actores y permisos
Actores: los 4 roles de `Membership`; **operador de la plataforma** (quien opera el Hub, Q-001; actúa por comando de
gestión y no tiene acceso implícito a datos de negocio, Q-212); **usuario autenticado sin membership** en la
organización; **ERP** (API key, SPEC-11).

Matriz con la organización en estado `active`:

| Acción | owner | admin | operator | viewer | Sin membership | ERP (API key) | Operador plataforma |
|---|---|---|---|---|---|---|---|
| Crear organización (+ invitación del primer owner) | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ comando (Q-212, Q-213) |
| Reemitir / revocar la invitación del primer owner (aún sin owner) | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ comando (Q-213) |
| Suspender / reactivar organización | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ comando (Q-208) |
| Obtener membership explícita de soporte | — | — | — | — | — | ✘ | ✔ comando, auditada (Q-212; mecanismo Q-222) |
| Invitación `owner` de recuperación (org con owner) | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ comando (Q-224, default) |
| Listar mis organizaciones y mi rol en cada una | ✔ | ✔ | ✔ | ✔ | ✔ (lista vacía) | ✘ | ✘ sin membership (Q-212) |
| Elegir organización activa (solo con membership vigente) | ✔ | ✔ | ✔ | ✔ | ✘ `404` (Q-219) | ✘ (org fija de la key) | ✘ sin membership (Q-212) |
| Ver datos de la organización activa | ✔ | ✔ | ✔ | ✔ | ✘ | ✘ (Q-216) | ✘ sin membership |
| Editar datos de la organización | ✔ | ✔ (Q-209) | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Listar miembros e invitaciones pendientes | ✔ | ✔ | ✘ (Q-218) | ✘ (Q-218) | ✘ | ✘ | ✘ sin membership |
| Invitar / asignar rol admin, operator o viewer | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Invitar / asignar o quitar rol owner | ✔ | ✘ (Q-202) | ✘ | ✘ | ✘ | ✘ | ✘ (salvo Q-213/Q-224) |
| Revocar membership de otro (no owner) | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Revocar membership de un owner | ✔ salvo último (Q-201) | ✘ (Q-202) | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Degradar el propio rol | ✔ salvo último owner (Q-201, Q-202) | ✔ a operator/viewer (Q-202) | ✘ (puede abandonar) | — | — | ✘ | — |
| Elevar el propio rol | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | — |
| Abandonar la organización (uno mismo) | ✔ salvo último (Q-201) | ✔ (Q-203) | ✔ (Q-203) | ✔ (Q-203) | — | ✘ | — |
| Revocar / reenviar invitación pendiente admin/operator/viewer | ✔ | ✔ (Q-202) | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Revocar / reenviar invitación pendiente owner | ✔ | ✘ (Q-202) | ✘ | ✘ | ✘ | ✘ | ✔ solo la del primer owner (Q-213) |
| Aceptar invitación | el usuario autenticado cuyo email coincide (Q-206); no requiere organización activa |||||||
| Ver sucursales de la organización (activas e inactivas) | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ lectura (Q-216) | ✘ sin membership |
| Crear / editar / desactivar / reactivar sucursal | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ sin membership |
| Borrar físicamente una sucursal | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ (Q-211) |

Notas: un `operator` o `viewer` no cambia roles (ni el propio); para irse usa "abandonar" (Q-203). Un `admin` puede
degradarse a sí mismo y degradar o revocar a otro `admin`, porque gestiona memberships `admin`/`operator`/`viewer`
(Q-202). Con una membership de soporte (Q-222), el operador de plataforma tiene exactamente los permisos del
rol de esa membership, como cualquier usuario.

### 4.1 Organización `suspended` (Q-208)
Los miembros conservan **solo lectura**: todo lo marcado ✔ de lectura en §4 sigue igual. Se rechazan con
`organization_suspended` (sin efectos): editar datos de la organización, invitar, reenviar invitación, cambiar
roles, aceptar invitación, crear/editar/desactivar/reactivar sucursal, y cualquier escritura de negocio de otros
módulos (p. ej. cobros nuevos). Siguen permitidas, por default de **Q-221** (pendiente de confirmar): revocar
membership, abandonar la organización y revocar invitaciones pendientes (reducen acceso), respetando Q-201/Q-202.
Los procesos servidor-a-servidor sobre cobros `pending` (webhooks, poller) **no** se bloquean por la suspensión.

Fuentes: Q-010 y brief §5 (owner/admin configuran sucursales y usuarios; operator cobra; viewer lee),
`context/07 §5.3` (operator ve sucursales en lectura) y las decisiones del 2026-10-31 en `clarifications.md`. Acción
no listada → denegada (RN-TEN-09).

## 5. Glosario del módulo
- **Organización activa**: la organización elegida por el usuario en el selector, enviada en un header de cada
  request tenant-scoped; es un dato que manda el cliente y que el backend **revalida** siempre (no es una
  autorización por sí misma).
- **Membership vigente**: membership en estado `active` (Q-214). Si la organización está `suspended`, la membership
  sigue vigente pero solo habilita lo de §4.1 (Q-208).
- **Endpoint tenant-scoped**: todo endpoint que lee o escribe datos de una organización.
- **Invitation**: oferta de membership a un email, con rol, de un solo uso, vigente 7 días (Q-206).
- **Operador de la plataforma**: quien administra el Hub por comando de gestión; no es un rol de `Membership` y no
  tiene acceso implícito a datos de negocio (Q-212).

## 6. Reglas de negocio
- **RN-TEN-01** Toda entidad de negocio lleva `organization_id`; `Organization` es la raíz. `Membership`,
  `Invitation` y `Branch` pertenecen a exactamente una organización (`C-01`).
- **RN-TEN-02** Toda lectura/escritura de datos de negocio pasa por managers/selectors tenant-aware; está prohibido
  el acceso crudo (`Model.objects` sin filtro) desde servicios de negocio. Una consulta de negocio sin organización
  explícita **falla cerrada**: no devuelve datos de ninguna organización (`C-01`).
- **RN-TEN-03** Cada request a un endpoint tenant-scoped indica una organización activa en un header. El backend
  verifica en **cada** request que el usuario tenga una membership vigente en ella y aplica el estado de la
  organización (§4.1); el resultado no se reutiliza entre requests. Ni el selector de UI ni el JWT son fuente de
  autorización: el JWT no lleva rol, organización ni membership (`context/07 §5.1`, `context/08 §8`, SPEC-01).
- **RN-TEN-04** La organización de una escritura sale **siempre** del contexto validado (RN-TEN-03), nunca de un
  campo del cuerpo, de la query ni de la URL elegida por el cliente.
- **RN-TEN-05** Pedir por ID un recurso de otra organización responde igual que si no existiera (`404`); los
  listados nunca incluyen recursos de otra organización (mismo criterio que AC-CHG-13).
- **RN-TEN-06** Una organización activa inexistente o sin membership vigente del usuario se rechaza con
  `404 organization_not_found`, **indistinguible** entre ambos casos (mismo código y cuerpo), sin datos ni efectos
  (Q-219).
- **RN-TEN-07** Un usuario puede tener memberships en varias organizaciones (glosario), pero **a lo sumo una
  vigente** por organización, con exactamente un rol de {`owner`, `admin`, `operator`, `viewer`}. El rol es por
  organización.
- **RN-TEN-08** Los permisos se evalúan con el rol **vigente** de la membership al momento de la request: un cambio
  de rol o una revocación rige desde la request siguiente, aunque la sesión/JWT del usuario siga vigente.
- **RN-TEN-09** La matriz §4/§4.1 es la única fuente de permisos de este módulo; toda acción no listada para un rol
  se deniega (`403 forbidden`). Ningún usuario puede elevar su propio rol.
- **RN-TEN-10** Solo el operador de la plataforma crea organizaciones, mediante **comando de gestión** (y Django
  admin restringido); no existe registro público ni endpoint de API de autoalta (Q-001, Q-212). Al crearla indica un
  email y se emite una invitación con rol `owner` a ese email (Q-213).
- **RN-TEN-11** Los usuarios se suman a una organización solo aceptando una invitación por email (Q-012); la
  aceptación exige estar autenticado con Google (SPEC-01). `Invitation` implementa el puerto de invitación de SPEC-01.
- **RN-TEN-12** Una invitación (Q-206):
  - vence a los **7 días** de emitida (vigente mientras `ahora < expires_at`, en UTC);
  - se acepta **una sola vez**, solo por el usuario autenticado cuyo email de Google coincide con el invitado sin
    distinguir mayúsculas y sin espacios al inicio/fin; no se aplican otras equivalencias (puntos, `+alias`);
  - hay a lo sumo **una** `pending` por (organización, email): crear otra mientras existe una se rechaza
    (`invitation_pending`); para renovarla se usa **reenviar**, que revoca la anterior y emite una nueva con token y
    vigencia nuevos;
  - aceptarla crea una membership `active` con el rol de la invitación; invitar a quien ya es miembro vigente se
    rechaza (`already_member`, RN-TEN-07).
- **RN-TEN-13** Un invitador solo puede invitar, asignar o quitar los roles que la matriz §4 le permite: solo un
  `owner` invita con rol `owner`, asigna o quita `owner` y revoca a un owner; un `admin` gestiona `admin`,
  `operator` y `viewer` y sus invitaciones (Q-202).
- **RN-TEN-14** La organización conserva siempre al menos un `owner` vigente: degradar, revocar o hacer abandonar al
  último owner se rechaza (`last_owner`), también bajo concurrencia (Q-201). Transferir la propiedad = un owner
  promueve a otro a `owner` y después se degrada o abandona (Q-202). Única excepción: una organización recién creada
  no tiene owner hasta que se acepta la invitación del primer owner (Q-213).
- **RN-TEN-15** Una `Branch` es una sucursal **local** del Hub (≠ Store de MP). Todo vínculo de una Branch con una
  integración, Store o caja (SPEC-04/05) pertenece a la misma organización que la Branch.
- **RN-TEN-16** La sucursal elegida en el selector es solo un **filtro** dentro de la organización activa: se valida
  que pertenezca a ella; no es frontera de autorización. En el MVP no hay memberships restringidas a sucursales
  (Q-204).
- **RN-TEN-17** Toda acción sensible de este módulo queda auditada con quién, qué, cuándo y organización (`C-08`;
  lista en RNF-TEN-04).
- **RN-TEN-18** Una organización está `active` o `suspended`; solo el operador de la plataforma la suspende o
  reactiva (Q-208). Suspendida, sus miembros tienen solo lectura (§4.1) y los cobros `pending` se siguen procesando
  servidor-a-servidor.
- **RN-TEN-19** Una Branch nunca se borra físicamente; se **desactiva** y es reactivable. Una Branch inactiva no
  admite cobros nuevos, pero no afecta los cobros `pending`, sus vínculos ni el histórico/reportes (Q-211). Su nombre
  es único por organización entre las Branch activas; reactivar una cuyo nombre ya usa otra activa se rechaza
  (`validation_error`, Q-210).
- **RN-TEN-20** Ser operador de la plataforma, superusuario o staff **no** otorga acceso a datos de negocio por la
  API: para operar en una organización necesita una membership explícita y auditada, y entonces tiene solo los
  permisos de ese rol (Q-212; mecanismo en Q-222).
- **RN-TEN-21** Revocar o abandonar marca la membership como `revoked` y la conserva (con motivo distinguible en
  auditoría); una membership `revoked` no se reactiva: re-invitar crea una membership nueva (Q-203, Q-214).

## 7. Requisitos funcionales
- **RF-TEN-01** Resolver y validar la organización activa (header) en cada request tenant-scoped y exponer ese
  contexto (usuario, organización, rol, estado de la organización) a servicios y selectors. (RN-TEN-03…06, 08, 18, 20)
- **RF-TEN-02** Listar las organizaciones del usuario con su rol en cada una (memberships `active`), incluido el
  selector que reutiliza `GET /api/me` de SPEC-01. (RN-TEN-07)
- **RF-TEN-03** Ver y editar los datos de la organización activa: `name` (obligatorio), `legal_name`, `tax_id`
  (CUIT), `timezone` (default `America/Argentina/Buenos_Aires`) (Q-209). (§4)
- **RF-TEN-04** Gestionar memberships: listar, cambiar rol, revocar, abandonar. (RN-TEN-07, 09, 13, 14, 21)
- **RF-TEN-05** Invitaciones: crear (link copiable visible una sola vez + email cuando haya proveedor, Q-207),
  listar pendientes, revocar, reenviar, aceptar. (RN-TEN-11…13)
- **RF-TEN-06** Sucursales: crear, listar, ver, editar, desactivar, reactivar (Q-210, Q-211). (RN-TEN-15, 16, 19)
- **RF-TEN-07** Comando de gestión del operador de la plataforma: crear organización con email del primer owner
  (emite la invitación `owner`), reemitir/revocar esa invitación mientras no haya owner, suspender/reactivar.
  (RN-TEN-10, 14, 18, 20; Q-212, Q-213; Q-222/Q-224 por default)
- **RF-TEN-08** Proveer managers/selectors tenant-aware y la verificación de permisos por rol para que los demás
  módulos (04, 06, 07, 08, 09, 11) los reutilicen, incluido el rechazo de escrituras en organizaciones `suspended`.
  (RN-TEN-01, 02, 09, 18)
- **RF-TEN-09** Emitir los eventos de auditoría de RNF-TEN-04 hacia el módulo 10. (RN-TEN-17)

## 8. Requisitos no funcionales
- **RNF-TEN-01 Seguridad / pruebas:** cada endpoint tenant-scoped (de este y de todo módulo) tiene un test
  cross-tenant; un test de arquitectura prohíbe accesos crudos en servicios de negocio (`C-01`, `C-11`).
- **RNF-TEN-02 Observabilidad:** todo log de request tenant-scoped incluye `organization_id` validado (`C-16`). Un
  rechazo por organización o permiso se loguea con `request_id`, usuario y organización pedida, y suma a una métrica
  de denegaciones (Q-217).
- **RNF-TEN-03 Secretos:** el token de invitación tiene alta entropía, se guarda solo como hash, es de un solo uso,
  se muestra en claro **una sola vez** (respuesta de crear/reenviar, Q-207) y nunca aparece en logs, errores ni
  listados (`C-06`).
- **RNF-TEN-04 Auditoría (`C-08`, para SPEC-10):** `organization.created`, `organization.updated`,
  `organization.suspended`, `organization.reactivated`, `membership.created`, `membership.role_changed`,
  `membership.revoked`, `membership.left`, `invitation.created`, `invitation.resent`, `invitation.revoked`,
  `invitation.accepted`, `invitation.rejected` (email no coincide / vencida / usada / organización suspendida),
  `branch.created`, `branch.updated`, `branch.deactivated`, `branch.reactivated`, `owner_protection.rejected`.
  Las acciones del operador de la plataforma por comando se auditan con el operador como actor (Q-212). Intentos
  denegados de acceso a otra organización: log operativo + métrica; a auditoría solo si se repiten, umbral en SPEC-10
  (Q-217).
- **RNF-TEN-05 Reversibilidad:** migraciones reversibles y probadas en ambos sentidos (`C-17`); el esquema no
  impide activar RLS antes de onboardear comercios ajenos (ADR-0001, Q-215).
- **RNF-TEN-06 Privacidad:** de un invitado se guarda solo el email; no se guarda PII adicional (`C-10`, Q-021).
- **RNF-TEN-07 Rendimiento:** la revalidación de membership no introduce consultas N+1 por request; el objetivo
  numérico lo fija `design.md`.

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `Organization` | id, name, legal_name?, tax_id?, timezone (default `America/Argentina/Buenos_Aires`), status ∈ {`active`, `suspended`}, created_by (operador), timestamps | ≥1 owner vigente salvo antes de aceptar el primer owner (RN-TEN-14) |
| `Membership` | id, organization, user, role, status ∈ {`active`, `revoked`}, motivo de fin (revocada / abandonó), invited_by, timestamps | a lo sumo una `active` por `(organization, user)`; `role` ∈ 4 valores; las `revoked` se conservan |
| `Invitation` | id, organization, email (normalizado: recortado + minúsculas), role, token_hash, status ∈ {`pending`, `accepted`, `revoked`, `expired`}, expires_at (= emisión + 7 días), invited_by (usuario u operador), accepted_by?, timestamps | un solo uso; a lo sumo una `pending` por `(organization, email)` |
| `Branch` | id, organization, name, code?, dirección?, is_active, timestamps | pertenece a una sola organización; `name` único por organización entre activas; sin borrado físico |

El vínculo Branch ↔ Store/integración (y la entidad Caja, Q-220) vive en SPEC-04/05 y hereda RN-TEN-15.

## 10. Estados y transiciones
| Entidad | Desde | Evento | Hacia | Quién |
|---|---|---|---|---|
| Invitation | — | crear | `pending` | owner/admin según §4; operador (primer owner, Q-213) |
| Invitation | `pending` | aceptar (email coincide, vigente, organización `active`) | `accepted` | usuario invitado |
| Invitation | `pending` | revocar | `revoked` | owner/admin según §4; operador (primer owner) |
| Invitation | `pending` | reenviar → se crea otra `pending` con token nuevo | `revoked` | owner/admin según §4; operador (primer owner) |
| Invitation | `pending` | `ahora ≥ expires_at` | `expired` | sistema |
| Membership | — | aceptar invitación | `active` | usuario invitado |
| Membership | `active` | cambiar rol (respeta RN-TEN-13/14) | `active` | owner/admin según §4; uno mismo solo para degradarse |
| Membership | `active` | revocar / abandonar (respeta RN-TEN-14) | `revoked` | owner/admin según §4 / el propio usuario |
| Organization | — | crear | `active` (sin owner hasta aceptar Q-213) | operador |
| Organization | `active` | suspender | `suspended` | operador (Q-208) |
| Organization | `suspended` | reactivar | `active` | operador (Q-208) |
| Branch | — | crear | activa | owner/admin |
| Branch | activa | desactivar | inactiva | owner/admin (Q-211) |
| Branch | inactiva | reactivar (nombre libre entre activas) | activa | owner/admin (Q-211) |

Terminales: Invitation `accepted`, `revoked`, `expired`; Membership `revoked`. Transición inválida → rechazada y
auditada (`C-05`). Una invitación vencida se rechaza al aceptar aunque todavía no se haya pasado a `expired`.

## 11. Contratos (nivel conceptual; detalle en `design.md`)
- `GET /api/organizations/` (mis organizaciones + rol) · `GET/PATCH /api/organizations/current/`.
- `GET /api/memberships/` · `PATCH /api/memberships/{id}/` (rol) · `DELETE /api/memberships/{id}/` (revocar:
  marca `revoked`, no borra) · `POST /api/memberships/me/leave/`.
- `POST/GET /api/invitations/` · `POST /api/invitations/{id}/revoke/` · `POST /api/invitations/{id}/resend/` ·
  `POST /api/invitations/accept/` (con token; no requiere organización activa).
- `GET/POST /api/branches/` · `GET/PATCH /api/branches/{id}/` · desactivar / reactivar (ruta en `design.md`);
  **sin** `DELETE` físico (Q-211).
- Alta, suspensión y reactivación de organización: **comando de gestión**, sin endpoint de API (Q-212).
- Organización activa: **header** en cada request tenant-scoped (nombre en `design.md`).
- Interfaz interna: contexto de tenant (usuario, organización, rol, estado) + selectors tenant-aware + verificación
  de rol + selector de memberships activas para `GET /api/me` (SPEC-01) + implementación del puerto de invitación de
  SPEC-01.
- Errores normalizados: `organization_required`, `organization_not_found` (`404`, Q-219), `organization_suspended`,
  `forbidden`, `not_found`, `validation_error`, `already_member`, `invitation_pending`, `invitation_invalid`,
  `last_owner` (Q-201). Códigos HTTP de los que no los fija esta spec: `design.md`.

## 12. Casos límite y excepciones
- Usuario sin ninguna membership vigente: puede autenticarse (SPEC-01) pero no opera nada; ve la pantalla "sin
  organización" con contacto del operador (Q-205).
- Organización activa al iniciar sesión: la última usada si sigue vigente; si no, la primera por nombre (Q-205).
- Rol cambiado o membership revocada a mitad de sesión: rige desde la request siguiente (RN-TEN-08).
- Dos owners se degradan/revocan mutuamente a la vez siendo los únicos: a lo sumo uno prospera (RN-TEN-14).
- Invitación aceptada dos veces en paralelo, o aceptada y revocada/reenviada a la vez: una sola transición desde
  `pending`; a lo sumo una membership (RN-TEN-07/12).
- Dos invitaciones simultáneas al mismo (organización, email): queda una sola `pending` (RN-TEN-12).
- Invitado que ya es miembro, o invitado desde dos organizaciones: cada organización es independiente.
- Quien emitió una invitación pierde el permiso antes de que se acepte: Q-223 (default: se revoca automáticamente).
- Organización recién creada sin owner: nadie opera en ella hasta que se acepta la invitación del primer owner; si
  vence, el operador la reemite (Q-213).
- El único owner pierde su cuenta de Google: recuperación por comando del operador, Q-224 (default).
- Branch desactivada con cobros `pending` o vínculos a Store: los `pending` siguen su curso y los vínculos se
  conservan; no se crean cobros nuevos con esa Branch (RN-TEN-19; 06 §12).
- Organización suspendida con cobros `pending`: se siguen procesando servidor-a-servidor; usuarios en solo lectura
  (RN-TEN-18, §4.1).
- Operador de la plataforma / superusuario sin membership que llama a la API con una organización activa: mismo
  rechazo que cualquier usuario sin membership (RN-TEN-06/20).
- Procesos sin usuario (webhooks, poller, tareas Celery): fijan la organización del recurso que procesan antes de
  tocar datos de negocio y no se bloquean por la suspensión; la forma de enumerar trabajo de varias organizaciones la
  define `design.md`.
- `branch_id` de otra organización usado como filtro: `404`, nunca datos (RN-TEN-05/16).
- Emails con mayúsculas o espacios al inicio/fin: se normalizan antes de guardar y comparar; `+alias` y puntos no se
  consideran equivalentes (RN-TEN-12).

## 13. Criterios de aceptación
- **AC-TEN-01** (RN-TEN-05) **Dado** un usuario `owner` de A y una Branch de B **cuando** hace GET, PATCH,
  desactivar o reactivar por su ID con A activa **entonces** `404`, sin cambios en B; y `GET /api/branches/` no
  incluye Branch de B.
- **AC-TEN-02** (RN-TEN-05) **Dado** un `owner` de A **cuando** opera por ID sobre una membership o invitación de
  B **entonces** `404` y nada cambia en B.
- **AC-TEN-03** (RN-TEN-03/06) **Dado** un usuario con membership solo en A **cuando** envía B como organización
  activa **entonces** recibe `404 organization_not_found` idéntico (código y cuerpo) al de una organización
  inexistente, sin datos.
- **AC-TEN-04** (RN-TEN-03/08) **Dado** un `admin` de A con sesión válida **cuando** se revoca su membership y hace
  otra request con A activa **entonces** es rechazada aunque su JWT siga vigente.
- **AC-TEN-05** (RN-TEN-08) **Dado** un `admin` de A degradado a `viewer` **cuando** intenta editar una Branch en
  la request siguiente **entonces** `403`.
- **AC-TEN-06** (RN-TEN-03) **Dado** una request autenticada a un endpoint tenant-scoped **cuando** no envía el
  header de organización activa **entonces** `organization_required` y ningún dato.
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
- **AC-TEN-14** (RN-TEN-14) **Dado** A con exactamente dos `owner` **cuando** se degradan o revocan mutuamente en
  paralelo **entonces** A termina con ≥1 owner vigente.
- **AC-TEN-15** (RN-TEN-13, Q-202) **Dado** un `admin` **cuando** invita con rol `owner`, asigna `owner`, quita
  `owner`, revoca a un owner o revoca/reenvía una invitación `owner` **entonces** `403` y nada cambia.
- **AC-TEN-16** (RN-TEN-09) **Dado** un `operator` o `viewer` **cuando** crea/edita/desactiva una Branch, invita
  o cambia un rol ajeno **entonces** `403`; y ningún usuario puede elevar su propio rol.
- **AC-TEN-17** (RN-TEN-12) **Dado** una invitación `pending` a `x@dominio` con rol `operator` **cuando** la acepta
  el usuario autenticado con ese email **entonces** existe una membership `operator` `active` y la invitación queda
  `accepted`; un segundo uso del mismo token (también en paralelo) → `invitation_invalid` y una sola membership.
- **AC-TEN-18** (RN-TEN-12, Q-206) **Dado** esa invitación **cuando** la intenta aceptar un usuario con otro email
  **entonces** `invitation_invalid`, sin membership, y la invitación sigue `pending`.
- **AC-TEN-19** (RN-TEN-12) **Dado** una invitación `expired` o `revoked` **cuando** se intenta aceptar
  **entonces** `invitation_invalid` y ninguna membership nueva.
- **AC-TEN-20** (RN-TEN-07/12) **Dado** un miembro vigente de A **cuando** se lo invita de nuevo a A
  **entonces** `already_member`.
- **AC-TEN-21** (RN-TEN-10) **Dado** cualquier usuario autenticado (incluso `owner`) **cuando** intenta crear una
  organización por la API **entonces** la cantidad de organizaciones no cambia.
- **AC-TEN-22** (RN-TEN-10, Q-212/213) **Dado** el operador de la plataforma **cuando** crea una organización por
  comando indicando un email **entonces** existe la organización `active` sin memberships, hay una invitación
  `pending` con rol `owner` a ese email y eventos `organization.created` e `invitation.created` con el operador como
  actor; al aceptarla, A tiene exactamente un owner.
- **AC-TEN-23** (RN-TEN-17) **Dado** cada acción de RNF-TEN-04 **cuando** ocurre **entonces** se emite un evento
  con actor, acción, organización y fecha.
- **AC-TEN-24** (RNF-TEN-03) **Dado** la creación, el reenvío y la aceptación de una invitación **entonces** el token
  en claro solo aparece en la respuesta de crear/reenviar y nunca en logs, errores ni en `GET /api/invitations/`.
- **AC-TEN-25** (RN-TEN-12, Q-206) **Dado** una invitación emitida en T **cuando** se acepta en T + 7 días − 1 min
  **entonces** se acepta; **cuando** se acepta en T + 7 días o después **entonces** `invitation_invalid` y ninguna
  membership.
- **AC-TEN-26** (RN-TEN-12, Q-206) **Dado** una invitación `pending` de A a `x@dominio` **cuando** se crea otra para
  el mismo email en A **entonces** `invitation_pending` y sigue habiendo una sola `pending`; **cuando** se reenvía
  **entonces** la anterior queda `revoked`, su token da `invitation_invalid`, y el token nuevo es aceptable con
  vigencia de 7 días desde el reenvío.
- **AC-TEN-27** (RN-TEN-14, Q-202) **Dado** A con un único `owner` U y un `admin` V **cuando** U promueve a V a
  `owner` y después U se degrada a `admin` **entonces** ambas operaciones prosperan y A tiene exactamente un owner (V).
- **AC-TEN-28** (RN-TEN-18, Q-208) **Dado** A `suspended` y un `owner` de A **cuando** lista Branch y ve datos de la
  empresa **entonces** los recibe; **cuando** crea/edita una Branch, edita datos, invita, cambia un rol o se acepta
  una invitación de A **entonces** `organization_suspended` sin efectos; y un evento servidor-a-servidor sobre un
  cobro `pending` de A se sigue procesando.
- **AC-TEN-29** (RN-TEN-18) **Dado** cualquier usuario autenticado de A (incluso `owner`) **cuando** intenta cambiar
  el estado de A por la API **entonces** el estado no cambia.
- **AC-TEN-30** (RN-TEN-19, Q-210/211) **Dado** una Branch activa de A **cuando** un `admin` la desactiva **entonces**
  la Branch sigue existiendo como inactiva, aparece en el listado marcada inactiva, no hay forma por la API de borrarla
  físicamente, y queda evento `branch.deactivated`; **cuando** se la reactiva y su nombre lo usa otra Branch activa de
  A **entonces** `validation_error` y sigue inactiva.
- **AC-TEN-31** (RN-TEN-21, Q-203/214) **Dado** un `operator` de A **cuando** abandona A **entonces** su membership
  queda `revoked` (conservada), su siguiente request con A activa da `404 organization_not_found`; y si luego se lo
  re-invita y acepta, existe una membership `active` **nueva** distinta de la revocada.
- **AC-TEN-32** (RN-TEN-16, Q-204) **Dado** un `operator` de A **cuando** filtra por cualquier Branch activa de A
  **entonces** obtiene los datos de esa Branch (no hay restricción por sucursal).
- **AC-TEN-33** (RN-TEN-20, Q-212) **Dado** un usuario superusuario/staff (operador de la plataforma) sin membership
  en A **cuando** llama a cualquier endpoint tenant-scoped con A activa **entonces** `404 organization_not_found`
  idéntico al de AC-TEN-03, sin datos.
- **AC-TEN-34** (RN-TEN-09, Q-218) **Dado** un `operator` o `viewer` de A **cuando** pide `GET /api/memberships/` o
  `GET /api/invitations/` **entonces** `403` y ningún email.
- **AC-TEN-35** (RN-TEN-12, Q-206) **Dado** una invitación a `" X@Dominio.com "` **cuando** la acepta el usuario
  autenticado `x@dominio.com` **entonces** se acepta; **cuando** la intenta aceptar `x+1@dominio.com` **entonces**
  `invitation_invalid`.

## 14. Interfaz de usuario
- **Selector empresa/sucursal** (shell en SPEC-00, `context/07 §5.1`): se alimenta de RF-TEN-02 y RF-TEN-06 (solo
  Branch activas para operar); la elección viaja como header y no es autorización (RN-TEN-03). Una organización
  `suspended` se muestra indicada como tal.
- **Configuración → Colaboradores** (solo owner/admin, Q-218): miembros y rol, invitaciones pendientes, invitar,
  cambiar rol, revocar, reenviar; el link de invitación se muestra una sola vez (Q-207); acciones visibles solo según
  §4/§4.1.
- **Configuración → Datos de la empresa**: lectura para todos, edición para owner/admin (campos Q-209).
- **Configuración → Sucursales**: listado (activas e inactivas) y alta/edición/desactivación/reactivación para
  owner/admin; lectura para operator/viewer. Las cajas de esa pantalla las aporta el módulo dueño de la Caja (Q-220).
- **Aceptar invitación**: tras login; estados válida / vencida / revocada / ya usada / email no coincide /
  organización suspendida.
- Estados de cada pantalla: cargando, vacío, error, sin permiso, "sin organización" con contacto del operador
  (Q-205), "organización suspendida (solo lectura)" (Q-208).

## 15. Riesgos y supuestos
- Supuesto (acordado con SPEC-01): SPEC-01 entrega un usuario autenticado con email verificado por Google; el JWT
  **no** lleva rol, organización ni membership (RN-TEN-03/08); la organización activa viaja en un header.
- Decidido: modelos propios para Organization/Membership (Q-027) → se formaliza en ADR-0002.
- Riesgo: un módulo futuro consulta sin selector → mitigación AC-TEN-10/12 en CI.
- Riesgo: el comando del operador es la vía más privilegiada; mitigación: sin acceso implícito (RN-TEN-20,
  AC-TEN-33) y auditoría con el operador como actor.
- Para el architect (paso 3, antes de *Designed*):
  - **ADR-0001 (multi-tenancy):** esquema compartido + `organization_id`; cómo se garantiza "falla cerrada"
    (RN-TEN-02) en managers/selectors; cómo se resuelve y revalida la organización activa del header por request
    sin N+1 (RNF-TEN-07); cómo fijan la organización los procesos sin usuario (Celery/webhooks/poller); cómo se aplica
    el estado `suspended` a escrituras de todos los módulos; diseño compatible con RLS y su activación antes de
    onboardear comercios ajenos (Q-215); forma del test de arquitectura y del test cross-tenant parametrizado
    (AC-TEN-10/12).
  - **ADR-0002 (modelos propios, Q-027):** Organization/Membership/Invitation/Branch propios (sin
    `django-organizations`/`django-saas`); constraints de unicidad parciales (una membership `active` por
    organización+usuario, una invitación `pending` por organización+email, nombre de Branch único entre activas);
    cómo se serializan las operaciones concurrentes de RN-TEN-14 (locks); relación con el modelo de usuario de
    SPEC-01 y con su puerto de invitación.

## 16. Preguntas abiertas
Ver `specs/02-tenancy-rbac/clarifications.md`. **Bloqueantes abiertas: ninguna** (Q-201, Q-202, Q-204, Q-206,
Q-208, Q-211, Q-212, Q-213 decididas el 2026-10-31). Decididas por defecto (confirmables antes de *Approved*): Q-221
(escrituras durante suspensión), Q-222 (mecanismo de la membership de soporte), Q-223 (invitaciones de quien pierde
permiso), Q-224 (recuperación de owner). Nuevas del diseño, no bloqueantes: Q-225 (catálogo de auditoría vs
C-05/C-08), Q-226 (nombre de Branch sin distinguir mayúsculas), Q-227 (unicidad de `code` de Branch). Dirigida a
otro módulo: Q-220 (dueño de la Caja, SPEC-04/05). Decididas transversales que aplican: Q-001, Q-006, Q-010, Q-012,
Q-027 (`specs/00-platform/clarifications.md`).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial | Tenancy + RBAC sobre Q-001, Q-006, Q-010, Q-012, Q-027 |
| 0.2.0 | 2026-10-31 | Estado → *Clarified*. Se incorporan las decisiones Q-201…Q-219 a §3/§4/§5/§6/§7/§9/§10/§11/§12/§14; matriz completa con columnas "sin membership" y operador, más §4.1 (organización suspendida); nuevas RN-TEN-18…21; nuevas AC-TEN-25…35; organización activa por header y JWT sin rol/organización (acuerdo con SPEC-01); Invitation implementa el puerto de SPEC-01; Q-012/Q-027 tratadas como decididas; nuevas Q-220 (dirigida a 04/05) y Q-221…Q-224 (no bloqueantes); insumos para ADR-0001/0002 en §15 | Decisiones del usuario del 2026-10-31 (clarify) |
| 0.3.0 | 2026-10-31 | Estado → *Designed*. Se agrega `design.md` (header `X-Organization-Id`, resolución en permiso DRF con 1 consulta, `TenantQuerySet` que falla cerrado, matriz como código, locks sobre `Organization`, contratos, UI, pruebas) y ADR-0001 / ADR-0002 (*Propuestos*). Q-221…Q-224 registradas como decididas por defecto (confirmables antes de *Approved*); nuevas Q-225…Q-227 (no bloqueantes). Sin cambios en RN/RF/AC | Paso 3 SDD (architect) |

---
**Hecho:** spec *Designed*: 21 RN, 9 RF, 7 RNF y 35 AC con destino en `design.md` (§2 y §9); ADR-0001 y ADR-0002
*Propuestos*.
**Pendiente:** confirmar Q-221…Q-224 (default aplicado) y decidir Q-225…Q-227 antes de *Approved* (si Q-223 o Q-225
se confirman, agregar sus AC y ajustar RNF-TEN-04); Q-220 para SPEC-04/05; ajustar `context/07 §5.1` según
`design.md §3.10`; firma final del puerto de invitación con SPEC-01.
**Siguiente rol:** humano (gate *Approved*) → task-planner.
