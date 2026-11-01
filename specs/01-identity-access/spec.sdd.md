---
id: SPEC-01
modulo: identity-access
estado: Designed
track: S
version: 0.3.0
depende_de: [SPEC-00]
actualizado: 2026-10-31
---

# Módulo de Identidad y Acceso

> **Zona roja (auth).** Todo cambio pasa por Carril S y `reviewer`. Preguntas en
> `specs/01-identity-access/clarifications.md` (rango Q-101…Q-199). **0 bloqueantes abiertas**; Q-119…Q-123 quedaron
> **decididas por defecto** en el diseño con su recomendación (marcado donde aplica), **confirmables antes de
> Approved**; Q-124 y Q-125 (nuevas, no bloqueantes) están abiertas. Diseño: `design.md` + ADR-0004 (Propuesto).
> SPEC-01 y SPEC-02 se cierran juntas en H1 (Q-108).

## 1. Contexto y problema
Toda persona que usa el Hub (owner, admin, operator, viewer) entra con su cuenta de Google; no hay contraseñas propias ni
registro público (Q-001, Q-012, Q-101). Hace falta saber **quién** hace cada request de forma confiable, que la credencial
del navegador no pueda robarse con un XSS (Q-013, Q-102, ADR-0004), que una sesión se pueda cerrar y vencer con efecto
inmediato (Q-103), y que nadie sin invitación termine con un usuario creado. La propuesta original manda el JWT al
JavaScript del frontend y exige "JWT en todos los endpoints": ambas cosas quedan descartadas (ver §15).

## 2. Objetivo
Permitir que una persona invitada inicie sesión con Google y obtenga una sesión del Hub segura, vencible y revocable,
identificada y revalidada en cada request del backend, sin que ningún token sea accesible desde el JavaScript del navegador.

## 3. Alcance
### 3.1 Incluido
- Entidad Usuario (identidad global, vinculada a una cuenta de Google).
- Login con Google por OAuth 2.0 / OpenID Connect y validación del token de identidad de Google.
- Emisión y validación del JWT de acceso propio del Hub; sesión revocable en servidor con chequeo por request; refresh, expiración y logout (Q-103).
- Sesión en el navegador vía cookie `httpOnly` gestionada por el servidor de Next.js (BFF) (Q-102 decidido).
- Lo que toca a identidad de la invitación por email (Q-012): aceptar o rechazar el primer login según exista invitación vigente, a través de un puerto que implementa SPEC-02 (Q-108).
- Rate limiting de los endpoints de autenticación (umbrales Q-111).
- `GET /api/me` (identidad + memberships activas vía selector de SPEC-02, Q-114).
- Pantallas "Ingresar", "Mi perfil" y "Seguridad" (`context/07-frontend-ui-guidelines.md §5.3`; "Seguridad" entra al MVP, Q-113).
- Comandos de gestión (sin HTTP) para bootstrap de owner (Q-106) y desactivar/reactivar usuarios (Q-116).
- Definición de qué eventos de identidad se auditan (el almacenamiento es de SPEC-10).
### 3.2 Fuera de alcance
- Organizaciones, memberships, roles, matriz de permisos, selector de empresa como autorización, validación del header de organización activa (SPEC-02).
- Crear, enviar, reenviar, revocar o vencer invitaciones; su política de expiración; envío de emails; aceptación de invitaciones por usuarios ya existentes (SPEC-02; Q-121).
- API keys y autenticación máquina-a-máquina del ERP (SPEC-11, Q-011).
- Almacenamiento, consulta y retención del log de auditoría (SPEC-10).
- Mecanismo genérico de rate limiting, logging estructurado, CI (SPEC-00); acá solo se fijan los umbrales de auth.
- Otros proveedores de identidad (GitHub, Microsoft…), usuario/contraseña, MFA propia, registro público, "olvidé mi contraseña" (Q-101).
- Filtrado por dominio de Google Workspace (`hd`) (Q-105).
- Impersonación, rol global de plataforma en la API, borrado de cuenta autoservicio, edición del perfil, idioma (Q-115, Q-116).
- Borrado definitivo de usuarios (a definir con asesoría legal, Q-118).
- Autenticación de webhooks de proveedores (firma, SPEC-07).

## 4. Actores y permisos
Las acciones de identidad no dependen del rol en una organización: aplican a toda persona autenticada, tenga o no
memberships (Q-109). El rol se resuelve en SPEC-02. "Operador de plataforma" = quien tiene shell en el servidor
(Q-001, Q-116); no es un rol de la API. Matriz completa en `clarifications.md §2`.

| Acción | anónimo | owner / admin / operator / viewer | sin membership | sistema/ERP | operador de plataforma |
|---|---|---|---|---|---|
| Iniciar login con Google | ✔ | ✔ | ✔ | ✘ (API key, SPEC-11) | — |
| Completar callback | ✔ si cumple RN-IDA-05 | ✔ | ✔ (Q-109) | ✘ | — |
| Refrescar la propia sesión | ✘ | ✔ | ✔ | ✘ `401` | — |
| Logout de la propia sesión | ✔ `204` sin efectos | ✔ | ✔ | ✘ | — |
| `GET /api/me` (solo de sí mismo) | ✘ `401` | ✔ | ✔ (memberships vacías) | ✘ `401` | — |
| Listar / revocar sesiones propias, "cerrar las demás" (Q-113) | ✘ `401` | ✔ | ✔ | ✘ | — |
| Ver o revocar sesiones de **otro** usuario | ✘ | ✘ `404` | ✘ `404` | ✘ | ✘ (Q-116) |
| Crear organización + invitación owner (bootstrap) | ✘ | ✘ | ✘ | ✘ | ✔ comando, sin HTTP, auditado (Q-106, Q-123) |
| Desactivar / reactivar un usuario (global) | ✘ | ✘ | ✘ | ✘ | ✔ comando, sin HTTP, auditado (Q-116) |
| Admin de Django | ✘ | ✘ | ✘ | ✘ | ✘ en producción (Q-116) |

## 5. Glosario del módulo
- **Usuario (User):** identidad global de una persona en el Hub; uno por cuenta de Google (`sub`). Puede tener varias memberships.
- **Token de identidad de Google (ID token):** JWT emitido por Google en el flujo OIDC; se valida y se descarta, nunca se reenvía.
- **JWT de acceso:** token propio del Hub, de 15 min, que identifica al usuario y a la sesión ante el backend. Nunca llega al JavaScript del navegador.
- **Sesión:** registro del lado servidor de un login (Q-103); agrupa los refresh tokens rotados, se revalida en cada request y puede revocarse con efecto inmediato.
- **Refresh token:** credencial de un solo uso que permite obtener un nuevo JWT de acceso sin volver a Google.
- **BFF:** capa servidor de Next.js (Route Handlers) que guarda la cookie `httpOnly`, la traduce a `Authorization`, setea/rota/borra la cookie, aplica CSRF y adjunta el header de organización activa (`07 §3.2`, ampliado por ADR-0004).
- **Organización activa:** empresa elegida en el selector; viaja por header en cada request y se persiste en la sesión del servidor del BFF; **nunca** es claim del JWT; Django la revalida siempre contra Membership (Q-112, SPEC-02).
- **Puerto de invitaciones:** interfaz definida por SPEC-01 e implementada por SPEC-02 para consultar y aceptar invitaciones (Q-108).

## 6. Reglas de negocio
- **RN-IDA-01** Las personas se autentican **solo** con Google (OIDC). No existen contraseñas propias ni registro público; el alta de personas es **solo por invitación** (Q-001, Q-012, Q-101 decidido). Cualquier login sin Google para desarrollo/CI: Q-122 (decidida por defecto, confirmable: solo un proveedor OIDC falso en settings de test/local, imposible de activar en staging/producción).
- **RN-IDA-02** El token de identidad de Google se acepta solo si: la firma valida contra las claves públicas vigentes de Google, `iss` es Google, `aud` es el client ID del Hub, no está vencido (tolerancia 60 s, Q-104), y `state` y `nonce` coinciden con los generados al iniciar ese login. Cualquier falla → rechazo `google_auth_failed`, sin crear usuario ni sesión. Se admite cualquier cuenta de Google, sin filtrar por `hd` (Q-105).
- **RN-IDA-03** Si el claim `email_verified` no es verdadero, el login se rechaza con `email_not_verified`, sin crear usuario ni sesión.
- **RN-IDA-04** El identificador estable de la persona es el `sub` de Google; el email es un atributo (cambios y colisiones: RN-IDA-21).
- **RN-IDA-05** Un login se acepta solo si **(a)** existe un usuario activo con ese `sub`, o **(b)** no existe y hay al menos una invitación pendiente y vigente para el email verificado, consultada a través del puerto de invitaciones de SPEC-02 (Q-108). La coincidencia de email es **exacta tras recortar espacios y pasar a minúsculas**, sin normalizar puntos ni alias `+` (Q-107). La vigencia se evalúa **en el callback**, no al iniciar el login. En otro caso → `not_invited` y no se crea nada. En el caso (a) el login **no** acepta invitaciones pendientes (Q-121 decidida por defecto, confirmable: la aceptación por un usuario existente es un flujo explícito de SPEC-02; ver Q-124).
- **RN-IDA-06** En el caso (b), la creación del usuario y la aceptación de **todas** las invitaciones vigentes para ese email ocurren de forma atómica: o quedan todas, o ninguna (cantidad: Q-120 decidida por defecto, confirmable: todas las vigentes).
- **RN-IDA-07** Un usuario inactivo no puede iniciar sesión (`user_inactive`) ni refrescar (`session_revoked`). Al desactivarse, todas sus sesiones pasan a `revoked` y el acceso se corta **en la request siguiente**, aunque su JWT de acceso no haya vencido (Q-103, RN-IDA-20). Reactivar al usuario no revive sesiones.
- **RN-IDA-08** El Hub emite su **propio** JWT de acceso; nunca usa ni reenvía el token de Google como credencial. El JWT se valida en cada request: firma, algoritmo dentro de una lista fija permitida (nunca `none`), `iss`, `aud`, y `exp`/`iat`/`nbf` con tolerancia de reloj de **60 s** (Q-104). Falla → `401` (`token_expired` si solo venció; `token_invalid` en cualquier otro caso).
- **RN-IDA-09** El JWT de acceso solo transporta identidad (usuario y sesión) y metadatos de validez: **no** lleva roles, organización activa, membership ni permisos. La organización activa viaja por request en un header elegido en el selector y persistido en la sesión del servidor del BFF; la autorización la resuelve SPEC-02 en cada request desde Membership (C-01, `08 §8`, Q-112). Alcance de la selección con varias pestañas: Q-119 (decidida por defecto, confirmable, dueña SPEC-02/ADR-0004: cada pestaña manda su empresa en el header; la sesión del BFF guarda la última elegida solo como valor inicial).
- **RN-IDA-10** El refresh token es de un solo uso y se rota en cada refresh; en BD solo se guarda su hash. Presentar uno ya usado revoca la sesión completa y se audita como posible robo (`refresh_reuse_detected`). Refreshes concurrentes legítimos de la misma sesión (varias pestañas) **no** cuentan como reuso: se evitan serializando el refresh en el BFF o con una ventana de gracia acotada (Q-103; mecanismo y parámetros en ADR-0004).
- **RN-IDA-11** Duración (Q-104): JWT de acceso **15 min**; sesión con vencimiento por **inactividad de 7 días** y **vida máxima absoluta de 30 días** desde el login; el refresh nunca extiende la vida absoluta. Vencida, la persona vuelve a Google.
- **RN-IDA-12** Ningún token (de Google, de acceso o de refresh) es legible por JavaScript del navegador: viajan en cookie `httpOnly`, `Secure`, `SameSite` gestionada por el BFF; el backend entrega tokens solo al BFF, nunca en un cuerpo de respuesta destinado al navegador (Q-013, Q-102 decidido, ADR-0004).
- **RN-IDA-13** Toda operación que cambia estado y se autentica por cookie está protegida contra CSRF; la redirección posterior al login solo admite rutas internas relativas (sin redirección abierta).
- **RN-IDA-14** Logout revoca en el servidor la sesión identificada por la cookie (su refresh token deja de servir), **aunque el JWT de acceso ya haya vencido**, y borra la cookie. Es idempotente: hacerlo sin sesión válida responde éxito sin efectos.
- **RN-IDA-15** Rate limiting (Q-111): inicio de login y callback **10 por minuto por IP del cliente**; refresh **30 por minuto por sesión**. La IP es la del navegador, no la del BFF ni la de un proxy (si no, todas las personas compartirían el cupo). Al excederse → `429` con `Retry-After`, sin llamar a Google.
- **RN-IDA-16** El client secret de Google y la clave de firma del JWT son secretos distintos entre sí y de cualquier otro propósito (`08 §8`); nunca aparecen en código, logs, errores ni respuestas (C-06).
- **RN-IDA-17** Se auditan (C-08, vía SPEC-10) con actor, resultado, motivo, fecha UTC y organización (Q-117: nula para eventos globales; la de la invitación cuando el login acepta una, un evento por invitación): login exitoso; login rechazado (`google_auth_failed`, `email_not_verified`, `not_invited`, `user_inactive`, `identity_conflict`); usuario creado por invitación; organización + invitación owner creadas por bootstrap; logout; sesión revocada (por usuario, por "cerrar las demás", por desactivación o por reuso de refresh); reuso de refresh detectado; usuario desactivado/reactivado; cambio de email de Google. Los `429` y `google_unavailable` van solo a logs operativos y métricas, no a auditoría (Q-111).
- **RN-IDA-18** `GET /api/me` devuelve solo datos de la persona autenticada (identidad + memberships activas vía selector de SPEC-02, Q-114); no acepta identificador de usuario.
- **RN-IDA-19** La sesión de persona (JWT) y la API key del ERP (SPEC-11) son mecanismos separados: este módulo no acepta API keys como sesión.
- **RN-IDA-20** Cada request autenticada verifica, además del JWT, que la sesión a la que pertenece siga `active` (no revocada ni vencida) y que su usuario siga activo. Una revocación o desactivación confirmada en BD rechaza la request siguiente con `401 session_revoked`; ninguna caché puede demorar ese efecto (Q-103 decidido).
- **RN-IDA-21** Cambios de identidad (Q-110): con el mismo `sub`, si Google trae otro email verificado y ningún otro usuario lo tiene, se actualiza en ese login y se audita; si colisiona con otro usuario, el email no se cambia, el login sigue con el email anterior y se audita la colisión. Un `sub` nuevo cuyo email ya pertenece a otro usuario → `identity_conflict` + alerta operativa, sin crear usuario ni sesión (aunque haya invitación). Nombre y avatar se sincronizan desde Google en cada login.
- **RN-IDA-22** Una persona con usuario activo y **sin memberships activas** puede iniciar sesión; `GET /api/me` devuelve memberships vacías y la UI muestra "no pertenecés a ninguna empresa" (Q-109). Quitar una membership no revoca sesiones; desactivar al usuario sí.
- **RN-IDA-23** No hay rol global de plataforma en la API del MVP. Crear el primer owner (organización + invitación owner para un email) y desactivar/reactivar usuarios se hace **solo** por comandos de gestión en el servidor, cada ejecución auditada; no existe endpoint HTTP para ninguna de las dos cosas y el admin de Django no se expone en producción (Q-106, Q-116). Uso del comando para cada organización nueva y su comportamiento al repetirse: Q-123 (decidida por defecto, confirmable, dueña SPEC-02: crea toda organización nueva, idempotente, auditado).
- **RN-IDA-24** "Seguridad" (Q-113): la persona ve sus sesiones `active` con navegador/SO resumido, fecha de inicio y último uso, y puede cerrar una o "cerrar las demás" (todas salvo la actual). No hay límite de sesiones concurrentes. No se guarda la IP completa del cliente.
- **RN-IDA-25** Retención (Q-118): los usuarios se desactivan de forma lógica (no se borran); las sesiones `revoked`/`expired` y sus refresh tokens se purgan a los **90 días**; los intentos de login se descartan al vencer o usarse.

## 7. Requisitos funcionales
- **RF-IDA-01** Iniciar login: genera `state`, `nonce` (y lo que el diseño requiera para el flujo de código) atados a ese intento y redirige a Google. (RN-IDA-02, 13, 15)
- **RF-IDA-02** Callback de Google: valida el resultado, aplica las reglas de acceso en el orden de §12, crea usuario y acepta invitaciones si corresponde y abre una sesión. (RN-IDA-02…06, 21)
- **RF-IDA-03** Validación del JWT de acceso **y de la sesión** en cada request autenticada del backend, adjuntando la identidad al contexto de la request. (RN-IDA-07…09, 20)
- **RF-IDA-04** Refresh con rotación, detección de reuso y tolerancia a refreshes concurrentes de la misma sesión. (RN-IDA-10, 11, 15)
- **RF-IDA-05** Logout de la sesión actual. (RN-IDA-14)
- **RF-IDA-06** `GET /api/me`: identidad + memberships activas vía selector de SPEC-02. (RN-IDA-18, 22; Q-114)
- **RF-IDA-07** Listar sesiones propias activas, revocar una y "cerrar las demás" (pantalla "Seguridad"). (RN-IDA-24, 14)
- **RF-IDA-08** Comandos de gestión, sin endpoint HTTP y auditados: bootstrap de organización + invitación owner (Q-106) y desactivar/reactivar usuario (Q-116). (RN-IDA-07, 23)
- **RF-IDA-09** Emisión de los eventos de auditoría de RN-IDA-17 hacia SPEC-10.
- **RF-IDA-10** Purga periódica de sesiones y refresh tokens terminales con más de 90 días e intentos de login vencidos. (RN-IDA-25)

## 8. Requisitos no funcionales
- **RNF-IDA-01** Seguridad: validación de JWT sin llamada externa por request; las claves públicas de Google se cachean y se refrescan ante un `kid` desconocido.
- **RNF-IDA-02** Rendimiento: validar el JWT de acceso agrega ≤ 20 ms p95 a la request. El chequeo de sesión de RN-IDA-20 tiene presupuesto propio, que fija `design.md`, sin cachés que demoren una revocación.
- **RNF-IDA-03** Observabilidad (C-16): logs estructurados de login/refresh/logout con `request_id`, `user_id` (si existe), resultado y motivo; **nunca** tokens, códigos de autorización, cookies, `state`/`nonce` ni client secret.
- **RNF-IDA-04** Métricas: logins exitosos y rechazados por motivo, `429` por endpoint, `google_unavailable`, reusos de refresh detectados, sesiones activas; alerta ante `identity_conflict` y `refresh_reuse_detected`.
- **RNF-IDA-05** Privacidad: del perfil de Google se guarda solo `sub`, email, nombre visible y, opcionalmente, URL del avatar (Q-115); del dispositivo, solo navegador/SO resumido, sin IP completa (Q-113); retención según RN-IDA-25 (Q-118).
- **RNF-IDA-06** Reversibilidad (C-17): las migraciones de usuario y sesión son reversibles; la activación del login real va detrás de feature flag. Ningún mecanismo de login alternativo puede activarse en staging/producción (Q-122).
- **RNF-IDA-07** Fechas y vencimientos en UTC en BD y en los claims; la UI las muestra en `America/Argentina/*`.

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `users` | id (UUID), google_sub, email, display_name, avatar_url?, is_active, last_login_at, created_at, deactivated_at? | `google_sub` único; `email` único sin distinguir mayúsculas (guardado normalizado, Q-107); sin contraseña utilizable |
| `auth_sessions` | id (UUID), user, created_at, last_used_at, idle_expires_at, absolute_expires_at, revoked_at?, revoke_reason?, client_hint (navegador/SO resumido) | `absolute_expires_at = created_at + 30 días` y no se extiende; revocada o vencida no vuelve a `active`; sin IP completa |
| `refresh_tokens` | id, session, token_hash, issued_at, used_at?, replaced_by? | solo hash; un solo uso; reuso fuera de la tolerancia de concurrencia ⇒ sesión revocada |
| `login_attempts` (transitorio) | state, nonce, return_path, created_at, expires_at | un solo uso; vida corta; `return_path` relativo |
| Invitación | *(de SPEC-02, Q-108)* — este módulo solo la consulta y la acepta por el puerto | — |
| Organización activa | *(dónde se persiste en la sesión del BFF: ADR-0004)* | preferencia de UI, nunca autorización ni claim |

Ninguna de estas entidades lleva `organization_id`: son globales a la plataforma (excepción acotada a C-01, que aplica a entidades de negocio).

## 10. Estados y transiciones
**Sesión** (Q-103):

| Desde | Evento | Hacia | Disparador |
|---|---|---|---|
| — | login aceptado | `active` | callback |
| `active` | refresh válido | `active` (token rotado; `idle_expires_at` se renueva, `absolute_expires_at` no) | BFF |
| `active` | logout | `revoked` | usuario |
| `active` | revocación desde "Seguridad" (una o "cerrar las demás") | `revoked` | usuario (Q-113) |
| `active` | reuso de refresh token | `revoked` | sistema |
| `active` | usuario desactivado | `revoked` | comando de gestión (Q-116) |
| `active` | vence inactividad (7 días) o vida absoluta (30 días) | `expired` | sistema |

Terminales: `revoked`, `expired` (purgados a los 90 días, RN-IDA-25). Cualquier evento sobre una sesión terminal → `401 session_revoked`, sin cambios. **Usuario:** `active` ⇄ `inactive` solo por comando de gestión (Q-116); volver a `active` no reactiva sesiones.

## 11. Contratos
Rutas tentativas; nombres finales, quién termina el callback (BFF o Django), el flujo exacto y el nombre del header de
organización se fijan en `design.md` y ADR-0004. Los errores del callback llegan al navegador como redirección a
"Ingresar" con un código de error, nunca con tokens. **Contratos finales: `design.md §6`** (el BFF termina el
navegador y Django termina OIDC; los endpoints que emiten tokens son `/api/auth/bff/*`, solo-BFF; header
`X-Organization-Id`, a confirmar con SPEC-02).

| Operación | Ruta tentativa | Respuesta | Errores |
|---|---|---|---|
| Iniciar login | `GET /api/auth/google/start` | redirección a Google | `rate_limited` |
| Callback | `GET /api/auth/google/callback` | sesión abierta (cookie vía BFF) + redirección a ruta interna | `google_auth_failed`, `google_unavailable`, `email_not_verified`, `not_invited`, `user_inactive`, `identity_conflict`, `rate_limited` |
| Refresh | `POST /api/auth/refresh` (solo BFF) | nuevo par de tokens (solo al BFF) | `session_revoked`, `token_invalid`, `rate_limited` |
| Logout | `POST /api/auth/logout` | `204` | — (idempotente) |
| Yo | `GET /api/me` | id, email, nombre, avatar + memberships activas (organización, rol) del selector de SPEC-02 (Q-114) | `unauthenticated`, `token_expired`, `token_invalid`, `session_revoked` |
| Sesiones | `GET /api/auth/sessions` · `POST /api/auth/sessions/{id}/revoke` · `POST /api/auth/sessions/revoke-others` | lista propia de activas · `204` · `204` | `not_found` (sesión ajena = inexistente), `unauthenticated` |

Interfaces internas:
- **Puerto de invitaciones** (definido por SPEC-01, implementado por SPEC-02, Q-108): `find_valid_invitations(email_normalizado)` → invitaciones vigentes (plural por Q-120, decidida por defecto) y `accept_invitations(invitations, user)`, ejecutado dentro de la misma transacción que crea el usuario (RN-IDA-06). Hasta que exista SPEC-02, un stub sin invitaciones (todo login nuevo → `not_invited`).
- **Selector de memberships** de SPEC-02 para `/api/me` (Q-114); stub vacío hasta que exista.
- **Puerto de auditoría** de SPEC-10.
- **Comandos de gestión** (sin HTTP): bootstrap de organización + invitación owner (usa servicios de SPEC-02 para crear la organización y la invitación; Q-106, Q-123); desactivar/reactivar usuario (Q-116).

## 12. Casos límite y excepciones
- **Orden de evaluación del callback** (determinístico): `rate_limited` → `state` ausente, ajeno, vencido o ya usado (`google_auth_failed`, sin llamar a Google) → canje del código con Google (`google_unavailable` si no responde, tarda o devuelve `429`) → validación del token y del `nonce` (`google_auth_failed`) → `email_not_verified` → si el `sub` existe: `user_inactive` o login (caso a, con RN-IDA-21) · si el `sub` es nuevo: `identity_conflict` si el email ya es de otro usuario, si no invitación vigente (caso b) o `not_invited`.
- Doble clic en "Ingresar con Google": dos intentos con `state` distintos; como mucho dos sesiones del mismo usuario, nunca dos usuarios.
- Callback repetido: el `state` es de un solo uso; el segundo callback falla con `google_auth_failed` sin crear otra sesión.
- Dos pestañas refrescan a la vez con el mismo refresh token: **no** revoca la sesión (RN-IDA-10, mecanismo en ADR-0004); un reuso posterior fuera de esa tolerancia sí la revoca.
- Persona invitada que entra con otra cuenta de Google (otro email): `not_invited` (Q-107).
- Invitación vencida o revocada entre el inicio del login y el callback: `not_invited` (vigencia evaluada en el callback).
- Dos callbacks simultáneos de la misma persona invitada: un solo usuario (restricción única de `google_sub`/email); el que pierde la carrera no responde `500`: relee, encuentra al usuario y continúa por el caso (a).
- Varias invitaciones vigentes para el mismo email en el primer login: se aceptan todas o ninguna (Q-120 decidida por defecto).
- Usuario existente con invitación pendiente a otra empresa: el login no la acepta (Q-121 decidida por defecto; la acepta SPEC-02; ver Q-124).
- Usuario desactivado con JWT de acceso vigente: `401 session_revoked` en la request siguiente (RN-IDA-20).
- Logout con el JWT de acceso ya vencido: igual revoca la sesión de la cookie (RN-IDA-14).
- Revocación de la sesión actual desde "Seguridad": equivale a logout de este navegador.
- Google caído o lento al validar: `google_unavailable`, recuperable, sin usuario ni sesión; nunca se acepta un token sin verificar.
- Rotación de claves de Google (`kid` desconocido): se refrescan las claves una vez antes de rechazar.
- Reloj del servidor desfasado: tolerancia de 60 s (Q-104); fuera de ella, `token_invalid` (o `token_expired` si solo venció).
- `return_path` absoluto, con esquema, `//host` o hacia otro dominio: se ignora y se redirige a "Inicio".
- Persona con login válido pero sin memberships activas: entra y ve "no pertenecés a ninguna empresa" (Q-109).
- Rol cambiado o membership quitada a mitad de sesión: no toca la sesión ni el JWT; SPEC-02 lo aplica en la request siguiente.
- Varias pestañas con distintas empresas activas: Q-119 (decidida por defecto b): cada pestaña manda la empresa que muestra; ADR-0004 §7).
- Sesión que llega a su vida absoluta en medio de una operación (p. ej. un cobro): la request recibe `401`; tras volver a ingresar, el reintento queda cubierto por la idempotencia de SPEC-06 (C-03).
- Varias cajas detrás de la misma IP pública: comparten el cupo de 10/min de inicio y callback (consecuencia directa de Q-111; con los pilotos previstos no debería alcanzarse, se vigila con la métrica de `429`).
- Nombre o avatar de Google vacíos o demasiado largos: se guardan vacíos/recortados sin rechazar el login (límites en `design.md`).

## 13. Criterios de aceptación
- **AC-IDA-01** (RN-IDA-05) **Dado** un usuario activo con `sub` S **cuando** completa el callback con un token de Google válido de S **entonces** se crea una sesión `active`, la cookie queda seteada y se audita `login_succeeded`.
- **AC-IDA-02** (RN-IDA-05, 06) **Dado** que no existe usuario y hay invitación vigente para `ana@x.com` **cuando** entra con Google verificado `ana@x.com` **entonces** se crea un usuario con ese `sub`, la invitación queda aceptada y existe sesión `active`; **y** si dos callbacks válidos de esa persona llegan a la vez, existe un solo usuario y ninguno responde `500`.
- **AC-IDA-03** (RN-IDA-05) **Dado** un email sin usuario ni invitación vigente **cuando** completa el callback **entonces** responde `not_invited`, no se crea usuario ni sesión y se audita el rechazo.
- **AC-IDA-04** (RN-IDA-05) **Dado** una invitación vencida o revocada para el email (incluso si estaba vigente al iniciar el login) **cuando** completa el callback **entonces** `not_invited` y no se crea usuario.
- **AC-IDA-05** (RN-IDA-06) **Dado** una o varias invitaciones vigentes **cuando** falla la aceptación de cualquiera de ellas durante el callback **entonces** no queda usuario creado, ni invitación aceptada, ni sesión.
- **AC-IDA-06** (RN-IDA-03) **Dado** un token de Google válido con `email_verified=false` **cuando** completa el callback **entonces** `email_not_verified`, sin usuario ni sesión, y se audita.
- **AC-IDA-07** (RN-IDA-02) **Dado** un token de Google con firma inválida, `aud` de otro cliente, `iss` ajeno o vencido hace más de 60 s **cuando** completa el callback **entonces** `google_auth_failed` en cada caso, sin usuario ni sesión.
- **AC-IDA-08** (RN-IDA-02, 13) **Dado** un callback cuyo `state` no corresponde a un intento vigente, o cuyo `nonce` no coincide **entonces** `google_auth_failed` sin llamar a Google por el `state` inválido; **y** repetir un callback ya usado no crea otra sesión.
- **AC-IDA-09** (RN-IDA-07) **Dado** un usuario inactivo **cuando** completa el callback o intenta refrescar **entonces** `user_inactive` / `session_revoked` y no obtiene tokens.
- **AC-IDA-10** (RN-IDA-08, 11) **Dado** un JWT de acceso vencido hace más de 60 s **cuando** llama a `GET /api/me` **entonces** `401 token_expired`; **y** un JWT emitido hace 14 min es aceptado.
- **AC-IDA-11** (RN-IDA-08) **Dado** un JWT con firma alterada, firmado con otra clave, con `alg=none` o con un algoritmo fuera de la lista **cuando** llama a cualquier endpoint autenticado **entonces** `401 token_invalid`.
- **AC-IDA-12** (RN-IDA-08) **Dado** un JWT con `iss` o `aud` distintos de los del Hub **entonces** `401 token_invalid`; **y** un token de Google presentado como JWT de acceso también es `401`.
- **AC-IDA-13** (RN-IDA-09) **Dado** un JWT de acceso emitido **cuando** se decodifica **entonces** no contiene rol, organización, membership ni permisos; solo identidad de usuario/sesión y claims de validez; **y** su `exp` es 15 min posterior a su `iat`.
- **AC-IDA-14** (RN-IDA-10) **Dado** una sesión activa **cuando** se refresca **entonces** se obtiene un nuevo par de tokens y el refresh anterior queda usado; en BD no existe el refresh en claro.
- **AC-IDA-15** (RN-IDA-10) **Dado** un refresh token ya usado **cuando** se presenta de nuevo fuera de la tolerancia de concurrencia de ADR-0004 **entonces** `session_revoked`, la sesión pasa a `revoked`, el refresh vigente de esa sesión tampoco sirve y se audita `refresh_reuse_detected`.
- **AC-IDA-16** (RN-IDA-11) **Dado** una sesión sin uso desde hace más de 7 días, o creada hace más de 30 días aunque se haya usado a diario, **cuando** intenta refrescar **entonces** `session_revoked` y la sesión queda `expired`; **y** refrescar nunca mueve `absolute_expires_at`.
- **AC-IDA-17** (RN-IDA-14) **Dado** una sesión activa **cuando** hace logout **entonces** `204`, la cookie se borra, el refresh deja de servir y se audita; un segundo logout responde `204` sin efectos.
- **AC-IDA-18** (RN-IDA-12) **Dado** un login exitoso o un refresh **cuando** se inspecciona toda respuesta que llega al navegador **entonces** ningún token aparece en el cuerpo ni en cookies sin `httpOnly`; la cookie de sesión tiene `httpOnly`, `Secure` y `SameSite`.
- **AC-IDA-19** (RN-IDA-13) **Dado** un `return_path` absoluto, con esquema, `//host` o de otro dominio **cuando** termina el login **entonces** se redirige a la ruta interna por defecto; **y** una mutación autenticada por cookie sin la protección CSRF exigida es rechazada.
- **AC-IDA-20** (RN-IDA-15) **Dado** 10 inicios de login (o 10 callbacks) desde la misma IP de cliente en un minuto **cuando** llega el 11.º **entonces** `429` con `Retry-After` y no hay llamada a Google; **y dado** 30 refreshes de una sesión en un minuto, el 31.º recibe `429`.
- **AC-IDA-21** (RN-IDA-18, Q-114) **Dado** una persona autenticada **cuando** llama a `GET /api/me` **entonces** recibe solo sus datos de identidad y sus memberships activas tal como las devuelve el selector de SPEC-02; sin sesión → `401 unauthenticated`.
- **AC-IDA-22** (RN-IDA-19) **Dado** una API key de ERP válida **cuando** se presenta en `GET /api/me` o en refresh **entonces** no se acepta como sesión de persona (`401`).
- **AC-IDA-23** (RN-IDA-16, RNF-IDA-03) **Dado** un login, refresh, logout y un rechazo **cuando** se capturan los logs y los errores **entonces** no contienen tokens, códigos, cookies, `state`/`nonce`, client secret ni clave de firma.
- **AC-IDA-24** (RN-IDA-17, Q-117) **Dado** cada evento de la lista de RN-IDA-17 **cuando** ocurre **entonces** se emite un evento de auditoría con actor, resultado, motivo, fecha UTC y organización (nula en eventos globales; la de la invitación en los que aceptan una); **y** un `429` no genera evento de auditoría.
- **AC-IDA-25** (§4, RN-IDA-24) **Dado** el usuario A **cuando** intenta listar o revocar una sesión del usuario B por su ID **entonces** `404` y la sesión de B sigue `active`.
- **AC-IDA-26** (RN-IDA-20, Q-103) **Dado** una sesión con un JWT de acceso vigente **cuando** esa sesión se revoca (logout desde otro dispositivo o desde "Seguridad") **entonces** la request siguiente con ese JWT responde `401 session_revoked`.
- **AC-IDA-27** (RN-IDA-07, 23) **Dado** un usuario con dos sesiones activas **cuando** el comando de gestión lo desactiva **entonces** ambas sesiones quedan `revoked`, la request siguiente de cualquiera responde `401 session_revoked` y se audita; **y** al reactivarlo, esas sesiones siguen `revoked` y debe volver a ingresar.
- **AC-IDA-28** (RN-IDA-10, Q-103) **Dado** una sesión abierta en dos pestañas **cuando** ambas refrescan a la vez con el mismo refresh token **entonces** la sesión sigue `active`, ambas pestañas siguen operando y no se audita `refresh_reuse_detected`.
- **AC-IDA-29** (RN-IDA-21, Q-110) **Dado** un usuario con `sub` S y email `a@x.com` **cuando** entra con S y email verificado `b@x.com` libre **entonces** su email pasa a `b@x.com` y se audita el cambio; **y dado** un `sub` nuevo con email `a@x.com` (aun con invitación vigente) **entonces** `identity_conflict`, sin usuario ni sesión, con auditoría y alerta.
- **AC-IDA-30** (RN-IDA-22, Q-109) **Dado** un usuario activo sin memberships activas **cuando** completa el callback **entonces** obtiene sesión `active` y `GET /api/me` devuelve memberships vacías.
- **AC-IDA-31** (RN-IDA-05, Q-107) **Dado** una invitación para ` Ana@X.com ` **cuando** entra con Google verificado `ana@x.com` **entonces** el login se acepta; **y** con `ana+1@x.com` o una variante con puntos **entonces** `not_invited`.
- **AC-IDA-32** (RN-IDA-23, Q-106, Q-116) **Dado** el sistema desplegado **cuando** se recorre el esquema de la API **entonces** no existe endpoint HTTP que cree organizaciones/owners ni que desactive o reactive usuarios, y el admin de Django no responde en producción; **y** el comando de bootstrap crea organización + invitación owner y emite su evento de auditoría.
- **AC-IDA-33** (RN-IDA-24, Q-113) **Dado** una persona con tres sesiones activas **cuando** usa "cerrar las demás" **entonces** solo queda `active` la sesión actual; **y** el listado de sesiones muestra navegador/SO resumido y fechas, sin IP.
- **AC-IDA-34** (RN-IDA-08, Q-104) **Dado** un JWT con `nbf`/`iat` 30 s en el futuro o vencido hace 30 s **entonces** se acepta; **y** con `nbf`/`iat` 120 s en el futuro **entonces** `401 token_invalid`.
- **AC-IDA-35** (RN-IDA-14) **Dado** una sesión activa cuyo JWT de acceso ya venció **cuando** hace logout **entonces** `204` y la sesión queda `revoked` en el servidor.
- **AC-IDA-36** (§12) **Dado** que Google no responde, tarda más que el timeout o devuelve `429` al canjear el código o al bajar sus claves (sin claves en caché válidas) **cuando** se completa el callback **entonces** `google_unavailable` recuperable, sin usuario ni sesión, y nunca se acepta el token sin verificar.
- **AC-IDA-37** (RN-IDA-15) **Dado** inicios de login de 10 IPs de cliente distintas que pasan por el mismo BFF en un minuto **entonces** ninguno recibe `429` (el cupo es por IP de cliente, no por la del BFF).
- **AC-IDA-38** (RN-IDA-25, Q-118) **Dado** una sesión `revoked` o `expired` hace más de 90 días **cuando** corre la purga **entonces** la sesión y sus refresh tokens dejan de existir; una de 89 días no se toca y el usuario nunca se borra.

## 14. Interfaz de usuario
- **Ingresar** (`(auth)/login`): botón único "Ingresar con Google". Estados: cargando/redirigiendo; cancelado en Google; `email_not_verified` ("tu email de Google no está verificado"); `not_invited` ("pedile a un administrador de tu empresa que te invite"); `user_inactive`; `identity_conflict` ("no pudimos verificar tu cuenta; contactá al soporte"); `rate_limited` ("esperá unos minutos"); `google_unavailable` con reintento.
- **Sesión vencida** en cualquier pantalla: el BFF intenta un refresh; si falla, vuelve a "Ingresar" conservando solo la ruta interna.
- **Sin empresas** (Q-109): pantalla "no pertenecés a ninguna empresa" con "Cerrar sesión".
- **Mi perfil** (Configuración): nombre, email y avatar de Google en solo lectura; sin idioma (Q-115).
- **Seguridad** (Configuración): sesiones propias activas (navegador/SO, inicio, último uso; la actual marcada) con "Cerrar esta sesión" / "Cerrar las demás" (Q-113); sin contraseña.
- **Menú de usuario:** "Cerrar sesión". Estados generales: carga/vacío/error según `07 §2`.

## 15. Riesgos y supuestos
- Riesgo: XSS que robe tokens → mitigación RN-IDA-12 (tokens fuera de JS); CSRF por usar cookie → RN-IDA-13.
- Riesgo: robo de refresh token → rotación + detección de reuso (RN-IDA-10) + corte inmediato (RN-IDA-20).
- Riesgo: falso positivo de reuso entre pestañas que expulse al operador en caja → RN-IDA-10, AC-IDA-28.
- Riesgo: crear usuarios sin control → sin registro público, gate por invitación (RN-IDA-05), bootstrap solo por comando (RN-IDA-23).
- Riesgo: toma de cuenta por email reciclado → `sub` manda, `identity_conflict` (RN-IDA-21).
- Riesgo: el chequeo de sesión por request agrega una lectura a cada request → presupuesto en `design.md` (RNF-IDA-02).
- Riesgo: cobro en la empresa equivocada con varias pestañas → Q-119 (SPEC-02/ADR-0004).
- Supuesto: Google es suficiente como único IdP para los pilotos (Q-001, Q-101 decidido).
- Supuesto: SPEC-02 implementa el puerto de invitaciones y el selector de memberships antes de cerrar H1 (Q-108); hasta entonces hay stubs.
- **Propuesta original descartada:** §6.1 de la propuesta entregaba el JWT al frontend para mandarlo en cada request (expuesto a JS) y §8 exigía "JWT en todos los endpoints". Se reemplaza por cookie `httpOnly` gestionada por el BFF de Next.js, con tokens nunca accesibles desde JavaScript (Q-102 decidido 2026-10-31), y el ERP usa API keys (Q-011).
- **Para el architect (ADR-0004):** *(resueltos el 2026-10-31 en `context/decisions/ADR-0004-sesion-y-tokens-en-navegador.md`, Propuesto, puntos 1–15, y en `design.md`)*
  1. Quién termina el callback OIDC (BFF o Django) y el flujo exacto (authorization code; PKCE además del client secret).
  2. Diseño de cookies: qué viaja (tokens o un identificador opaco de sesión), nombres/prefijo `__Host-`, `SameSite` (el retorno desde Google exige que la cookie del intento sobreviva a la navegación cruzada), `Path`, `Max-Age` alineado a la vida absoluta de 30 días, límites de tamaño.
  3. Concurrencia del refresh (Q-103): serialización en el BFF (con varias instancias de Next.js necesita un candado compartido) **o** ventana de gracia (duración y qué se devuelve dentro de ella), cumpliendo AC-IDA-28 sin debilitar AC-IDA-15.
  4. Chequeo de sesión por request (RN-IDA-20): cómo se hace, presupuesto de latencia y garantía de que ninguna caché demore una revocación; cuándo se actualiza `last_used_at`.
  5. JWT: algoritmo (lista fija), gestión y rotación de la clave de firma (`kid`, solapamiento), claims (usuario, sesión, `iss`, `aud`, `exp`, `iat`, `nbf`), separación del client secret (RN-IDA-16).
  6. Mecanismo CSRF para mutaciones autenticadas por cookie (en BFF y/o Django).
  7. Header de organización activa: nombre, dónde persiste la selección en la sesión del servidor del BFF y comportamiento con varias pestañas (Q-119, junto con SPEC-02).
  8. Ampliación de `07 §3.2`: el BFF deja de ser "solo adjunta la cookie": setea, rota y borra la cookie, hace el refresh, aplica CSRF y adjunta el header de organización (actualizar ese documento).
  9. Rate limiting detrás del BFF/proxy: obtener la IP real del cliente desde un proxy de confianza (AC-IDA-37); clave por sesión para refresh.
  10. Librerías de OIDC/JWT (C-13: ADR y versiones fijadas); caché de claves de Google y refresco ante `kid` desconocido; timeout hacia Google (AC-IDA-36).
  11. Contrato de los puertos con SPEC-02 (invitaciones en plural por Q-120 provisional, misma transacción y bloqueo al aceptar; selector de memberships), stubs hasta que exista SPEC-02, y en qué app vive el comando de bootstrap (Q-106, Q-123).
  12. Vencimiento: estado `expired` derivado de las marcas de tiempo o materializado por tarea; tarea periódica de purga a 90 días (RF-IDA-10).
  13. Nuevo login en un navegador que ya tenía sesión: si la anterior se revoca (motivo "reemplazada") o queda hasta vencer.
  14. Entornos: client ID de Google separado por entorno, feature flag del login real y, según Q-122, el proveedor OIDC falso solo para test/local con chequeo de arranque.
  15. Cómo llegan los códigos de error del callback a la pantalla "Ingresar" (redirección con código, sin filtrar detalles).
- Pendiente de otros documentos: ajustar `07 §3.2` (punto 8; texto propuesto en `design.md §13`) y `ROADMAP.md` (01 y 02 se cierran juntas en H1, Q-108).

## 16. Preguntas abiertas
Ver `specs/01-identity-access/clarifications.md`. **Bloqueantes abiertas: ninguna.** Decididas el 2026-10-31: Q-101…Q-118.
Decididas por defecto en el diseño (confirmables antes de Approved): Q-119, Q-120, Q-121, Q-122, Q-123.
Abiertas sin bloquear (nuevas, diseño): Q-124 (owner de organización nueva que ya tiene usuario), Q-125 (datos de la
persona en el evento de login rechazado).
Base transversal: Q-001, Q-011, Q-012, Q-013 (`specs/00-platform/clarifications.md`).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

| AC | Tarea(s) | Test(s) |
|---|---|---|
| AC-IDA-01 | — | `test_AC_IDA_01_…` |

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial | Primera redacción de SPEC-01 (zona roja auth); toma Q-001/Q-011/Q-012/Q-013 y corrige el manejo de JWT de la propuesta |
| 0.2.0 | 2026-10-31 | Estado → Clarified. Se registran las decisiones del usuario sobre Q-101…Q-118; RN-IDA-01/02/05/06/07/08/09/10/11/12/14/15/17/18 con los valores decididos (duraciones 15 min / 7 días / 30 días / 60 s; rate limit 10/min por IP y 30/min por sesión); nuevas RN-IDA-20…25, RF-IDA-10 y AC-IDA-26…38; error `google_unavailable`; orden de evaluación del callback; matriz de permisos completa (anónimo, sin membership, operador de plataforma); casos límite revisados; Q-119…Q-123 agregadas como no bloqueantes; lista de puntos para ADR-0004 | Paso 2 SDD (clarifier); decisiones del usuario del 2026-10-31 y coordinación acordada con SPEC-02 (sin rol/organización en el JWT; organización activa por header; `/api/me` con selector de SPEC-02) |
| 0.3.0 | 2026-10-31 | Estado → Designed. Se agregan `design.md` y ADR-0004 (Propuesto) que resuelve los 15 puntos de §15. Q-119…Q-123 pasan de "abiertas, provisional" a "decididas por defecto, confirmables antes de Approved" con **el mismo valor** que ya usaban las RN (sin cambio de reglas); notas de estado en RN-IDA-01/05/06/09/23, §11 (contratos finales en `design.md §6`), §12, §15, §16. Nuevas Q-124 y Q-125 (no bloqueantes, abiertas) | Paso 3 SDD (architect) |

---
**Hecho:** spec Designed 0.3.0 (25 RN, 10 RF, 7 RNF, 38 AC sin cambios de reglas); `design.md` con cobertura RN/RF/RNF completa; ADR-0004 Propuesto.
**Pendiente:** confirmación del dueño de Q-119…Q-123 y respuesta a Q-124/Q-125; coordinación con SPEC-02 (`X-Organization-Id`, `MembershipSummary`, bootstrap) y SPEC-00 (modelos globales en el test C-01, `AUTH_USER_MODEL` desde el inicio); aplicar `07 §3.2` y `ROADMAP.md`.
**Siguiente rol:** dueño — gate **Approved** (no lo pasa ningún agente); luego task-planner (`/tasks 01-identity-access`).
