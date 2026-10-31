---
id: SPEC-01
modulo: identity-access
estado: Draft
track: S
version: 0.1.0
depende_de: [SPEC-00]
actualizado: 2026-10-31
---

# Módulo de Identidad y Acceso

> **Zona roja (auth).** Todo cambio pasa por Carril S y `reviewer`. Preguntas abiertas en
> `specs/01-identity-access/clarifications.md` (rango Q-101…Q-199).

## 1. Contexto y problema
Toda persona que usa el Hub (owner, admin, operator, viewer) entra con su cuenta de Google; no hay contraseñas propias ni
registro público (Q-001, Q-012). Hace falta saber **quién** hace cada request de forma confiable, que la credencial del
navegador no pueda robarse con un XSS (Q-013, ADR-0004 pendiente), que una sesión se pueda cerrar y vencer, y que nadie
sin invitación termine con un usuario creado. La propuesta original manda el JWT al JavaScript del frontend y exige
"JWT en todos los endpoints": ambas cosas se corrigen acá (ver §15).

## 2. Objetivo
Permitir que una persona invitada inicie sesión con Google y obtenga una sesión del Hub segura, vencible y revocable,
identificada en cada request del backend, sin que ningún token sea accesible desde el JavaScript del navegador.

## 3. Alcance
### 3.1 Incluido
- Entidad Usuario (identidad global, vinculada a una cuenta de Google).
- Login con Google por OAuth 2.0 / OpenID Connect y validación del token de identidad de Google.
- Emisión y validación del JWT de acceso propio del Hub; refresh, expiración y logout.
- Sesión en el navegador vía cookie `httpOnly` gestionada por el servidor de Next.js (**recomendación a confirmar**, Q-102).
- Lo que toca a identidad de la invitación por email (Q-012): aceptar o rechazar el primer login según exista invitación vigente.
- Rate limiting de los endpoints de autenticación (umbrales en Q-111).
- `GET /api/me` (identidad de la persona autenticada).
- Pantallas "Ingresar", "Mi perfil" y "Seguridad" (`context/07-frontend-ui-guidelines.md §5.3`).
- Definición de qué eventos de identidad se auditan (el almacenamiento es de SPEC-10).
### 3.2 Fuera de alcance
- Organizaciones, memberships, roles, matriz de permisos, selector de empresa como autorización (SPEC-02).
- Crear, enviar, reenviar, revocar o vencer invitaciones; su política de expiración; envío de emails (SPEC-02).
- API keys y autenticación máquina-a-máquina del ERP (SPEC-11, Q-011).
- Almacenamiento, consulta y retención del log de auditoría (SPEC-10).
- Mecanismo genérico de rate limiting, logging estructurado, CI (SPEC-00); acá solo se fijan los umbrales de auth.
- Otros proveedores de identidad (GitHub, Microsoft…), usuario/contraseña, MFA propia, registro público, "olvidé mi contraseña".
- Impersonación, borrado de cuenta autoservicio, edición de datos del perfil más allá de lo que trae Google (Q-115).
- Autenticación de webhooks de proveedores (firma, SPEC-07).

## 4. Actores y permisos
Las acciones de identidad no dependen del rol en una organización: aplican a toda persona autenticada, tenga o no
memberships (Q-109). El rol se resuelve en SPEC-02.

| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|
| Iniciar sesión con Google | ✔ | ✔ | ✔ | ✔ | ✘ (usa API key, SPEC-11) |
| Refrescar / cerrar la propia sesión | ✔ | ✔ | ✔ | ✔ | ✘ |
| `GET /api/me` (solo de sí mismo) | ✔ | ✔ | ✔ | ✔ | ✘ (ver SPEC-11) |
| Listar / revocar sus propias sesiones (Q-113) | ✔ | ✔ | ✔ | ✔ | ✘ |
| Ver o revocar sesiones de **otro** usuario | ✘ | ✘ | ✘ | ✘ | ✘ (Q-116) |
| Desactivar / reactivar un usuario (global) | ✘ | ✘ | ✘ | ✘ | ✘ (Q-116) |

## 5. Glosario del módulo
- **Usuario (User):** identidad global de una persona en el Hub; uno por cuenta de Google (`sub`). Puede tener varias memberships.
- **Token de identidad de Google (ID token):** JWT emitido por Google en el flujo OIDC; se valida y se descarta, nunca se reenvía.
- **JWT de acceso:** token propio del Hub, de vida corta, que identifica al usuario y a la sesión ante el backend.
- **Sesión:** registro del lado servidor de un login (Q-103); agrupa los refresh tokens rotados y puede revocarse.
- **Refresh token:** credencial de un solo uso que permite obtener un nuevo JWT de acceso sin volver a Google.
- **BFF:** capa servidor de Next.js (Route Handlers) que guarda la cookie y la traduce a `Authorization` (`07 §3.2`).

## 6. Reglas de negocio
- **RN-IDA-01** Las personas se autentican **solo** con Google (OIDC). No existen contraseñas propias ni registro público (Q-001, Q-012; confirmar Q-101).
- **RN-IDA-02** El token de identidad de Google se acepta solo si: la firma valida contra las claves públicas vigentes de Google, `iss` es Google, `aud` es el client ID del Hub, no está vencido, y `state` y `nonce` coinciden con los generados al iniciar ese login. Cualquier falla → rechazo `google_auth_failed`, sin crear usuario ni sesión.
- **RN-IDA-03** Si el claim `email_verified` no es verdadero, el login se rechaza con `email_not_verified`, sin crear usuario ni sesión.
- **RN-IDA-04** El identificador estable de la persona es el `sub` de Google; el email es un atributo (cambios y colisiones: Q-110).
- **RN-IDA-05** Un login se acepta solo si **(a)** existe un usuario activo con ese `sub`, o **(b)** no existe y hay una invitación pendiente y vigente para el email verificado (coincidencia: Q-107; fuente de la invitación: Q-108). En otro caso → `not_invited` y no se crea nada.
- **RN-IDA-06** En el caso (b), la creación del usuario y la aceptación de la invitación ocurren de forma atómica: o quedan ambas, o ninguna.
- **RN-IDA-07** Un usuario inactivo no puede iniciar sesión (`user_inactive`) ni refrescar; al desactivarse, todas sus sesiones se revocan. Qué tan rápido deja de valer un JWT de acceso ya emitido: Q-103.
- **RN-IDA-08** El Hub emite su **propio** JWT de acceso; nunca usa ni reenvía el token de Google como credencial. El JWT se valida en cada request: firma, algoritmo dentro de una lista fija permitida (nunca `none`), `iss`, `aud`, `exp` y `iat`/`nbf` con tolerancia de reloj acotada (Q-104). Falla → `401` (`token_expired` si solo venció; `token_invalid` en cualquier otro caso).
- **RN-IDA-09** El JWT de acceso solo transporta identidad (usuario y sesión) y metadatos de validez: **no** lleva roles, organización activa ni permisos. La autorización se resuelve en cada request desde memberships (C-01, `08 §8`).
- **RN-IDA-10** El refresh token es de un solo uso y se rota en cada refresh; en BD solo se guarda su hash. Presentar uno ya usado revoca la sesión completa y se audita como posible robo (modelo de sesión: Q-103).
- **RN-IDA-11** Duración: JWT de acceso corto; sesión con vencimiento por inactividad y vida máxima absoluta; vencida, la persona vuelve a Google (valores: Q-104).
- **RN-IDA-12** Ningún token (de Google, de acceso o de refresh) es legible por JavaScript del navegador: viajan en cookie `httpOnly`, `Secure`, `SameSite` gestionada por el BFF; el backend entrega tokens solo al BFF (recomendación Q-013/ADR-0004, confirmar Q-102).
- **RN-IDA-13** Toda operación que cambia estado y se autentica por cookie está protegida contra CSRF; la redirección posterior al login solo admite rutas internas relativas (sin redirección abierta).
- **RN-IDA-14** Logout revoca la sesión en el servidor (su refresh token deja de servir) y borra la cookie. Es idempotente: hacerlo sin sesión válida responde éxito sin efectos.
- **RN-IDA-15** Inicio de login, callback y refresh tienen rate limiting; al excederse → `429` con `Retry-After`, sin llamar a Google (umbrales: Q-111).
- **RN-IDA-16** El client secret de Google y la clave de firma del JWT son secretos distintos entre sí y de cualquier otro propósito (`08 §8`); nunca aparecen en código, logs, errores ni respuestas (C-06).
- **RN-IDA-17** Se auditan (C-08, vía SPEC-10) con actor, resultado, motivo, fecha UTC y organización cuando aplique (Q-117): login exitoso; login rechazado (`google_auth_failed`, `email_not_verified`, `not_invited`, `user_inactive`, `identity_conflict`); usuario creado por invitación o bootstrap; logout; sesión revocada (por usuario, por desactivación o por reuso de refresh); reuso de refresh detectado; usuario desactivado/reactivado; cambio de email de Google (Q-110). Los `429` van a logs operativos, no a auditoría salvo decisión en Q-111.
- **RN-IDA-18** `GET /api/me` devuelve solo datos de la persona autenticada; no acepta identificador de usuario.
- **RN-IDA-19** La sesión de persona (JWT) y la API key del ERP (SPEC-11) son mecanismos separados: este módulo no acepta API keys como sesión.

## 7. Requisitos funcionales
- **RF-IDA-01** Iniciar login: genera `state`, `nonce` (y lo que el diseño requiera para el flujo de código) atados a ese intento y redirige a Google. (RN-IDA-02, 13, 15)
- **RF-IDA-02** Callback de Google: valida el resultado, aplica las reglas de acceso, crea usuario si corresponde y abre una sesión. (RN-IDA-02…06)
- **RF-IDA-03** Validación del JWT de acceso en cada request autenticada del backend, adjuntando la identidad al contexto de la request. (RN-IDA-07…09)
- **RF-IDA-04** Refresh con rotación y detección de reuso. (RN-IDA-10, 11, 15)
- **RF-IDA-05** Logout de la sesión actual. (RN-IDA-14)
- **RF-IDA-06** `GET /api/me`. (RN-IDA-18; contenido: Q-114)
- **RF-IDA-07** Listar y revocar sesiones propias (pantalla "Seguridad"), sujeto a Q-113. (RN-IDA-14)
- **RF-IDA-08** Operación administrativa sin endpoint público para crear el primer owner (Q-106) y para desactivar/reactivar usuarios (Q-116). (RN-IDA-07)
- **RF-IDA-09** Emisión de los eventos de auditoría de RN-IDA-17 hacia SPEC-10.

## 8. Requisitos no funcionales
- **RNF-IDA-01** Seguridad: validación de JWT sin llamada externa por request; las claves públicas de Google se cachean y se refrescan ante un `kid` desconocido.
- **RNF-IDA-02** Rendimiento: validar el JWT de acceso agrega ≤ 20 ms p95 a la request (sin contar el chequeo de Q-103 si se adopta).
- **RNF-IDA-03** Observabilidad (C-16): logs estructurados de login/refresh/logout con `request_id`, `user_id` (si existe), resultado y motivo; **nunca** tokens, códigos de autorización, cookies, `state`/`nonce` ni client secret.
- **RNF-IDA-04** Métricas: logins exitosos y rechazados por motivo, `429` por endpoint, reusos de refresh detectados, sesiones activas.
- **RNF-IDA-05** Privacidad: del perfil de Google se guarda solo `sub`, email, nombre visible y, opcionalmente, URL del avatar (Q-115); retención: Q-118.
- **RNF-IDA-06** Reversibilidad (C-17): las migraciones de usuario y sesión son reversibles; la activación del login real puede ir detrás de feature flag.
- **RNF-IDA-07** Fechas en UTC en BD; la UI las muestra en `America/Argentina/*`.

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| `users` | id (UUID), google_sub, email, display_name, avatar_url?, is_active, last_login_at, created_at, deactivated_at? | `google_sub` único; `email` único sin distinguir mayúsculas; sin contraseña utilizable |
| `auth_sessions` | id (UUID), user, created_at, last_used_at, idle_expires_at, absolute_expires_at, revoked_at?, revoke_reason?, client_hint? (Q-113) | revocada o vencida no vuelve a `active` |
| `refresh_tokens` | id, session, token_hash, issued_at, used_at?, replaced_by? | solo hash; un solo uso; reuso ⇒ sesión revocada |
| `login_attempts` (transitorio) | state, nonce, return_path, created_at, expires_at | un solo uso; vida corta; `return_path` relativo |
| Invitación | *(de SPEC-02, Q-108)* — este módulo solo la consulta y la acepta | — |

Ninguna de estas entidades lleva `organization_id`: son globales a la plataforma (excepción acotada a C-01, que aplica a entidades de negocio).

## 10. Estados y transiciones
**Sesión** (Q-103):

| Desde | Evento | Hacia | Disparador |
|---|---|---|---|
| — | login aceptado | `active` | callback |
| `active` | refresh válido | `active` (token rotado) | BFF |
| `active` | logout | `revoked` | usuario |
| `active` | revocación desde "Seguridad" | `revoked` | usuario (Q-113) |
| `active` | reuso de refresh token | `revoked` | sistema |
| `active` | usuario desactivado | `revoked` | operación administrativa (Q-116) |
| `active` | vence inactividad o vida absoluta | `expired` | sistema |

Terminales: `revoked`, `expired`. **Usuario:** `active` ⇄ `inactive` (Q-116).

## 11. Contratos
Rutas tentativas; nombres finales, quién termina el callback (BFF o Django) y el flujo exacto se fijan en `design.md` y ADR-0004.

| Operación | Ruta tentativa | Respuesta | Errores |
|---|---|---|---|
| Iniciar login | `GET /api/auth/google/start` | redirección a Google | `rate_limited` |
| Callback | `GET /api/auth/google/callback` | sesión abierta (cookie vía BFF) + redirección a ruta interna | `google_auth_failed`, `email_not_verified`, `not_invited`, `user_inactive`, `identity_conflict`, `rate_limited` |
| Refresh | `POST /api/auth/refresh` | nuevo par de tokens (solo al BFF) | `session_revoked`, `token_invalid`, `rate_limited` |
| Logout | `POST /api/auth/logout` | `204` | — (idempotente) |
| Yo | `GET /api/me` | id, email, nombre, avatar (+ memberships según Q-114) | `unauthenticated`, `token_expired`, `token_invalid` |
| Sesiones (Q-113) | `GET /api/auth/sessions` · `POST /api/auth/sessions/{id}/revoke` | lista propia · `204` | `not_found` (sesión ajena = inexistente) |

Interfaces internas: puerto de invitaciones `find_valid_invitation(email)` / `accept_invitation(invitation, user)` implementado por SPEC-02 (Q-108); puerto de auditoría de SPEC-10; selector de memberships de SPEC-02 para `/api/me` (Q-114).

## 12. Casos límite y excepciones
- Doble clic en "Ingresar con Google" o callback repetido: el `state` es de un solo uso; el segundo callback falla sin crear una segunda sesión.
- Callback con `state` ajeno, vencido o ausente (CSRF de login): rechazo `google_auth_failed`.
- Dos pestañas refrescan a la vez con el mismo refresh token: puede leerse como reuso y revocar la sesión; el diseño debe definir una ventana de gracia o serializar el refresh en el BFF (Q-103).
- Persona invitada que entra con otra cuenta de Google (otro email): `not_invited` (Q-107).
- Invitación vencida o revocada entre el inicio del login y el callback: `not_invited`.
- Dos callbacks simultáneos de la misma persona invitada: un solo usuario creado (restricción única de `google_sub`/email).
- Usuario desactivado con JWT de acceso vigente: depende de Q-103 (inmediato vs. al vencer el access token).
- Google caído o lento al validar: rechazo con error recuperable; nunca se acepta un token sin verificar.
- Rotación de claves de Google (`kid` desconocido): se refrescan las claves una vez antes de rechazar.
- Reloj del servidor desfasado: tolerancia acotada (Q-104); fuera de ella, `token_invalid`.
- `return_path` absoluto o hacia otro dominio: se ignora y se redirige a "Inicio".
- Persona con login válido pero sin memberships activas: Q-109.

## 13. Criterios de aceptación
- **AC-IDA-01** (RN-IDA-05) **Dado** un usuario activo con `sub` S **cuando** completa el callback con un token de Google válido de S **entonces** se crea una sesión `active`, la cookie queda seteada y se audita `login_succeeded`.
- **AC-IDA-02** (RN-IDA-05, 06) **Dado** que no existe usuario y hay invitación vigente para `ana@x.com` **cuando** entra con Google verificado `ana@x.com` **entonces** se crea un usuario con ese `sub`, la invitación queda aceptada y existe sesión `active`.
- **AC-IDA-03** (RN-IDA-05) **Dado** un email sin usuario ni invitación vigente **cuando** completa el callback **entonces** responde `not_invited`, no se crea usuario ni sesión y se audita el rechazo.
- **AC-IDA-04** (RN-IDA-05) **Dado** una invitación vencida para el email **cuando** completa el callback **entonces** `not_invited` y no se crea usuario.
- **AC-IDA-05** (RN-IDA-06) **Dado** una invitación vigente **cuando** falla la aceptación de la invitación durante el callback **entonces** no queda usuario creado ni sesión.
- **AC-IDA-06** (RN-IDA-03) **Dado** un token de Google válido con `email_verified=false` **cuando** completa el callback **entonces** `email_not_verified`, sin usuario ni sesión, y se audita.
- **AC-IDA-07** (RN-IDA-02) **Dado** un token de Google con firma inválida, `aud` de otro cliente, `iss` ajeno o vencido **cuando** completa el callback **entonces** `google_auth_failed` en cada caso, sin usuario ni sesión.
- **AC-IDA-08** (RN-IDA-02, 13) **Dado** un callback cuyo `state` no corresponde a un intento vigente, o cuyo `nonce` no coincide **entonces** `google_auth_failed`; **y** repetir un callback ya usado no crea otra sesión.
- **AC-IDA-09** (RN-IDA-07) **Dado** un usuario inactivo **cuando** completa el callback o intenta refrescar **entonces** `user_inactive` / `session_revoked` y no obtiene tokens.
- **AC-IDA-10** (RN-IDA-08) **Dado** un JWT de acceso vencido **cuando** llama a `GET /api/me` **entonces** `401 token_expired`.
- **AC-IDA-11** (RN-IDA-08) **Dado** un JWT con firma alterada, firmado con otra clave, con `alg=none` o con un algoritmo fuera de la lista **cuando** llama a cualquier endpoint autenticado **entonces** `401 token_invalid`.
- **AC-IDA-12** (RN-IDA-08) **Dado** un JWT con `iss` o `aud` distintos de los del Hub **entonces** `401 token_invalid`; **y** un token de Google presentado como JWT de acceso también es `401`.
- **AC-IDA-13** (RN-IDA-09) **Dado** un JWT de acceso emitido **cuando** se decodifica **entonces** no contiene rol, organización ni permisos; solo identidad de usuario/sesión y claims de validez.
- **AC-IDA-14** (RN-IDA-10) **Dado** una sesión activa **cuando** se refresca **entonces** se obtiene un nuevo par de tokens y el refresh anterior queda usado; en BD no existe el refresh en claro.
- **AC-IDA-15** (RN-IDA-10) **Dado** un refresh token ya usado **cuando** se presenta de nuevo **entonces** `session_revoked`, la sesión pasa a `revoked`, el refresh vigente de esa sesión tampoco sirve y se audita `refresh_reuse_detected`.
- **AC-IDA-16** (RN-IDA-11) **Dado** una sesión que superó su inactividad o su vida absoluta **cuando** intenta refrescar **entonces** `session_revoked` y la sesión queda `expired`.
- **AC-IDA-17** (RN-IDA-14) **Dado** una sesión activa **cuando** hace logout **entonces** `204`, la cookie se borra, el refresh deja de servir y se audita; un segundo logout responde `204` sin efectos.
- **AC-IDA-18** (RN-IDA-12) **Dado** un login exitoso **cuando** se inspecciona la respuesta al navegador **entonces** ningún token aparece en el cuerpo ni en cookies sin `httpOnly`; la cookie de sesión tiene `httpOnly`, `Secure` y `SameSite`.
- **AC-IDA-19** (RN-IDA-13) **Dado** un `return_path` absoluto o de otro dominio **cuando** termina el login **entonces** se redirige a la ruta interna por defecto; **y** una mutación autenticada por cookie sin la protección CSRF exigida es rechazada.
- **AC-IDA-20** (RN-IDA-15) **Dado** el umbral de Q-111 superado en inicio de login, callback o refresh **entonces** `429` con `Retry-After` y no hay llamada a Google.
- **AC-IDA-21** (RN-IDA-18) **Dado** una persona autenticada **cuando** llama a `GET /api/me` **entonces** recibe solo sus datos; sin sesión → `401 unauthenticated`.
- **AC-IDA-22** (RN-IDA-19) **Dado** una API key de ERP válida **cuando** se presenta en `GET /api/me` o en refresh **entonces** no se acepta como sesión de persona (`401`).
- **AC-IDA-23** (RN-IDA-16, RNF-IDA-03) **Dado** un login, refresh, logout y un rechazo **cuando** se capturan los logs y los errores **entonces** no contienen tokens, códigos, cookies, `state`/`nonce`, client secret ni clave de firma.
- **AC-IDA-24** (RN-IDA-17) **Dado** cada evento de la lista de RN-IDA-17 **cuando** ocurre **entonces** se emite un evento de auditoría con actor, resultado, motivo y fecha UTC.
- **AC-IDA-25** (Permisos §4, RF-IDA-07) **Dado** el usuario A **cuando** intenta revocar una sesión del usuario B **entonces** `404` y la sesión de B sigue `active` (sujeto a Q-113).

## 14. Interfaz de usuario
- **Ingresar** (`(auth)/login`): botón único "Ingresar con Google". Estados: cargando/redirigiendo; cancelado en Google; `email_not_verified` ("tu email de Google no está verificado"); `not_invited` ("pedile a un administrador de tu empresa que te invite"); `user_inactive`; `rate_limited` ("esperá unos minutos"); error de Google con reintento.
- **Sesión vencida** en cualquier pantalla: el BFF intenta un refresh; si falla, vuelve a "Ingresar" conservando solo la ruta interna.
- **Mi perfil** (Configuración): nombre, email y avatar de Google en solo lectura (Q-115).
- **Seguridad** (Configuración): sesiones propias con "Cerrar esta sesión" / "Cerrar las demás" (Q-113); sin contraseña.
- **Menú de usuario:** "Cerrar sesión". Estados generales: carga/vacío/error según `07 §2`.

## 15. Riesgos y supuestos
- Riesgo: XSS que robe tokens → mitigación RN-IDA-12 (tokens fuera de JS); CSRF por usar cookie → RN-IDA-13.
- Riesgo: robo de refresh token → rotación + detección de reuso (RN-IDA-10).
- Riesgo: crear usuarios sin control → sin registro público, gate por invitación (RN-IDA-05).
- Supuesto: Google es suficiente como único IdP para los pilotos (Q-001, Q-101).
- Corrección a la propuesta: §6.1 entrega el JWT al frontend para usarlo en cada request (expuesto a JS) y §8 exige JWT en todos los endpoints; acá se reemplaza por cookie `httpOnly` vía BFF (Q-102) y el ERP usa API keys (Q-011).
- Para el architect: la propuesta sugiere librerías de login social; en zona roja requieren ADR (C-13). El BFF de `07 §3.2` ("solo adjunta la cookie") necesita ampliarse para setear/rotar/borrar la cookie y proteger CSRF (ADR-0004).

## 16. Preguntas abiertas
Ver `specs/01-identity-access/clarifications.md`. **Bloqueantes:** Q-101, Q-102, Q-103, Q-106, Q-108. No bloqueantes con
recomendación por defecto: Q-104, Q-105, Q-107, Q-109…Q-118. Base transversal: Q-001, Q-011, Q-012, Q-013
(`specs/00-platform/clarifications.md`).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

| AC | Tarea(s) | Test(s) |
|---|---|---|
| AC-IDA-01 | — | `test_AC_IDA_01_…` |

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial | Primera redacción de SPEC-01 (zona roja auth); toma Q-001/Q-011/Q-012/Q-013 y corrige el manejo de JWT de la propuesta |

---
**Hecho:** spec Draft con 19 RN, 9 RF, 7 RNF, 25 AC; `clarifications.md` con Q-101…Q-118.
**Pendiente:** 5 bloqueantes (Q-101, Q-102, Q-103, Q-106, Q-108); ADR-0004; ajustar `07 §3.2` (BFF) y `ROADMAP.md` (01↔02) si se aceptan las recomendaciones.
**Siguiente rol:** clarifier (`/clarify 01-identity-access`).
