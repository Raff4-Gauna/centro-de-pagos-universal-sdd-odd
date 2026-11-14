# ADR-0004 — Sesión y tokens en el navegador: BFF de Next.js con cookies `httpOnly`, sesión revocable en servidor y JWT propio

- **Estado:** Aceptado (dueño, 2026-11-07)
- **Fecha:** 2026-10-31
- **Specs afectadas:** SPEC-01 (principal), SPEC-02 (header de organización activa, puertos, bootstrap), SPEC-00
  (settings, throttling, logging, test de arquitectura), SPEC-10 (puerto de auditoría), SPEC-11 (separación de la API
  key). Constitución: C-06, C-08, C-13, C-16, C-17. Diseño: `specs/01-identity-access/design.md`.

## Contexto
- Decidido por el usuario (2026-10-31): solo Google (Q-101); tokens **nunca** accesibles desde JavaScript, en cookie
  `httpOnly` gestionada por el BFF de Next.js (Q-102, base Q-013); sesión revocable en servidor con **chequeo por
  request** (Q-103); duraciones 15 min / 7 d / 30 d / 60 s (Q-104); rate limit 10/min por IP y 30/min por sesión
  (Q-111); organización activa por header, nunca en el JWT (Q-112).
- La propuesta original (§6.1) entregaba el JWT al frontend: queda descartada.
- Django está expuesto a internet de todos modos (webhooks de proveedores, ERP con API key), así que "solo el BFF"
  no se puede garantizar solo con la topología de red.
- El usuario pidió simplicidad (07 §3): nada de infraestructura que no haga falta en un MVP de pocas organizaciones.
- La spec §15 deja 15 puntos para este ADR. Valores por defecto, confirmados por el dueño el 2026-11-06: Q-119 b),
  Q-120 a), Q-121 b), Q-122 b), Q-123 (el comando crea toda organización nueva, idempotente y auditado; dueña SPEC-02).

## Opciones (las de fondo; los detalles se deciden punto por punto abajo)
1. **Django termina todo el OIDC y setea cookies.** Pros: un solo componente. Contras: Django pasa a autenticar por
   cookie (CSRF en Django, cookies en otro origen o reescrituras de dominio); contradice Q-102 (el BFF gestiona la cookie).
2. **El BFF termina todo el OIDC** (canjea el código, valida el ID token, llama a Django para "crear sesión").
   Contras: el client secret y la validación de Google viven en Node; las reglas de acceso quedarían repartidas
   entre dos servicios o Django confiaría en lo que el BFF dice de Google (frontera débil).
3. **Elegida: el BFF termina el navegador y Django termina OIDC.** El BFF recibe el redirect de Google y reenvía
   `code`/`state`/binding a un endpoint de Django **solo-BFF**; Django canjea, valida y decide; devuelve los tokens solo
   al BFF, que los pone en cookies. Pros: reglas y secretos de Google en un solo lugar (Django), cookies en el mismo
   origen que la app, Django sigue autenticando solo por `Authorization`. Contras: un salto más en el login (aceptable).

Para la concurrencia del refresh: (a) candado compartido en el BFF (Redis desde Next.js, tokens en un *store* del
BFF) vs (b) **ventana de gracia en Django** (elegida, ver punto 3).

## Decisión (los 15 puntos de la spec §15)

### 1. Quién termina el callback y flujo exacto
Authorization Code + **PKCE S256 además del client secret** (cliente confidencial), `scope=openid email profile`,
`state` (32 bytes), `nonce` (32 bytes), `prompt=select_account` (cajas compartidas), sin `access_type=offline` (no se
piden refresh tokens de Google). `redirect_uri` = Route Handler del BFF `GET /api/auth/google/callback`. Django
guarda en `login_attempts` los **hash** de `state`, `nonce` y binding, y el `code_verifier` (vida 10 min, se borra al
consumir con `DELETE … RETURNING`). El **binding** (32 bytes en la cookie `__Host-cpu_login`) ata el intento al
navegador que lo inició: sin él, un atacante podría hacer que la víctima complete un callback con la cuenta del
atacante (login CSRF). El BFF reutiliza el binding existente si hay otro intento vivo en el mismo navegador (doble
clic, dos pestañas). Django valida el ID token **aunque** venga directo del token endpoint por TLS (RN-IDA-02 exige
firma).

### 2. Cookies
Viajan **los tokens** (no un identificador opaco con *store* en el BFF: evitaría poco y obligaría a un Redis compartido
para Next.js). Todas `Secure`, `Path=/`, prefijo `__Host-` (sin `Domain`; impide que un subdominio las pise):
`__Host-cpu_at` (JWT, `HttpOnly`, `Max-Age = expires_in − 60`), `__Host-cpu_rt` (refresh opaco, `HttpOnly`,
`Max-Age = idle_expires_at − now`, renovado en cada refresh y nunca más allá de la vida absoluta de 30 días),
`__Host-cpu_csrf` (no `HttpOnly`, ver punto 6), `__Host-cpu_login` (`HttpOnly`, 600 s), `__Host-cpu_org` (punto 7).
**`SameSite=Lax`** en todas: la cookie del intento tiene que viajar en la navegación GET top-level que vuelve de
Google, y con `Strict` el aterrizaje tras el redirect y los enlaces de los emails de invitación llegarían sin sesión.
Tamaños: JWT ≈ 450 B, refresh ≈ 90 B; muy por debajo de 4 KB.

### 3. Concurrencia del refresh
**Ventana de gracia de 30 s en Django**, más coalescencia en memoria por instancia del BFF (una promesa por hash de
refresh token). Django bloquea el refresh token y la sesión con `SELECT … FOR UPDATE`; si el token ya se usó hace
≤ 30 s **y** su sucesor es el token vivo de la sesión, responde un JWT de acceso nuevo con `refresh_token = null`
(no rota, no audita) y el BFF actualiza solo la cookie de acceso: la cookie de refresh del navegador ya quedó con el
sucesor por la respuesta de la pestaña que rotó. Fuera de esa condición, es **reuso**: revoca la sesión entera,
audita `refresh_reuse_detected` y alerta. Cumple AC-IDA-28 sin candado compartido y sin debilitar AC-IDA-15. Costo
aceptado: quien robe un refresh y lo use dentro de los 30 s posteriores a un uso legítimo obtiene solo un JWT de
15 min, cortable por revocación (punto 4).

**Enmienda (2026-11-14, decisión del dueño):** la clave de coalescencia del BFF es
`sha256(refresh token + IP del cliente + User-Agent)`, no solo el hash del token. Así, un token robado que se presenta
mientras corre un refresh legítimo no recibe el par rotado por compartir la promesa. Las pestañas de un mismo
navegador comparten IP y User-Agent y siguen haciendo un solo refresh; si la IP o el User-Agent difieren, cada pedido
va a Django y decide la ventana de gracia de arriba. Implementado en `frontend/src/lib/server/refresh.ts` (T-IDA-23).

### 4. Chequeo de sesión por request
`HubJWTAuthentication` (DRF) verifica el JWT localmente y luego ejecuta **un** `SELECT` por PK de `auth_sessions` con
`JOIN users`: `status='active'`, `idle_expires_at > now`, `absolute_expires_at > now`, `is_active`. Presupuesto:
≤ 5 ms p95 el chequeo, ≤ 20 ms p95 toda la autenticación. **Ninguna caché** del estado de sesión o usuario; lee del
primario. **Sin escrituras por request:** `last_used_at` e `idle_expires_at` se actualizan en el refresh (cada
≤ 15 min de uso activo), lo que alcanza para la inactividad de 7 días y para "último uso" en "Seguridad".

### 5. JWT de acceso
**ES256** (ECDSA P-256), allowlist de un solo algoritmo `["ES256"]` (nunca `none` ni HS*). Header
`{alg, kid, typ: "at+jwt"}`; claims exactos `{iss, aud, sub (user UUID), sid (session UUID), iat, nbf, exp = iat + 900}`.
Se eligió asimétrico para que un verificador futuro no pueda emitir; se descartó EdDSA porque su identificador en JOSE
está siendo reemplazado por identificadores totalmente especificados y no hace falta esa ambigüedad. Claves por env:
`IDENTITY_JWT_SIGNING_KID` + `IDENTITY_JWT_SIGNING_KEY` (privada activa) y `IDENTITY_JWT_VERIFICATION_KEYS`
(`{kid: pública}`, incluye la activa y la anterior durante el solapamiento). Rotación en tres despliegues (agregar
pública → cambiar firmante → quitar la vieja tras ≥ 16 min). `kid` desconocido → `token_invalid` sin llamada de red.
Ante compromiso se quita la clave en el acto: el BFF refresca ante `token_invalid` y los refresh opacos siguen
sirviendo. La clave de firma, el client secret de Google, la credencial BFF y `DJANGO_SECRET_KEY` son secretos
distintos; un *system check* falla si dos coinciden (RN-IDA-16).

### 6. CSRF
En el **BFF**, para todo `POST/PUT/PATCH/DELETE`: `Origin` exactamente igual a `HUB_APP_ORIGIN` (si falta,
`Sec-Fetch-Site: same-origin`; si faltan ambos, rechazo) **y** *double-submit*: `X-CSRF-Token` igual a la cookie
`__Host-cpu_csrf` (comparación en tiempo constante; rotada en cada login). El prefijo `__Host-` evita la inyección de
cookie desde subdominios, que es la debilidad clásica del double-submit sin firma, así que no se agrega HMAC. Sin CORS
en el BFF; mutaciones solo por Route Handlers (no Server Actions). Django no aplica CSRF porque nunca autentica por
cookie (`SessionAuthentication` fuera de DRF).

### 7. Header de organización activa
Nombre **`X-Organization-Id`** (UUID), confirmado por `specs/02-tenancy-rbac/design.md`. Q-119 **b)**: cada pestaña manda
la empresa que muestra desde su propio estado; el BFF la reenvía validando el formato y **nunca** la inyecta. La
"persistencia en la sesión del servidor del BFF" (Q-112) es la cookie `HttpOnly` `__Host-cpu_org`, que solo el
servidor lee y escribe (`PUT /api/session/active-organization`), y que sirve como valor inicial de pestañas nuevas y
recargas (el layout la lee en el servidor). Así una pestaña nunca opera sobre una empresa distinta de la que muestra.
No autoriza nada: Django revalida la membership en cada request (SPEC-02). Se borra en el logout.

### 8. Ampliación de `07 §3.2`
El BFF deja de ser "solo adjunta la cookie". Pasa a: terminar el navegador del login, setear/rotar/borrar las
cookies, hacer el refresh transparente (y reintentar una vez ante `token_expired`/`token_invalid`), aplicar CSRF,
reenviar `X-Organization-Id` y guardar la preferencia de empresa, e informar la IP del cliente a los endpoints de
login. Sigue sin lógica de negocio ni transformación de respuestas. Texto de reemplazo propuesto:
`specs/01-identity-access/design.md §13`.

### 9. Rate limit e IP real
El BFF calcula la IP del cliente desde `X-Forwarded-For` contando `HUB_TRUSTED_PROXY_HOPS` saltos desde la derecha
(los que agrega el proxy de borde) y la manda en `X-Hub-Client-IP` **solo** a los endpoints `auth/bff/*`. Django la
usa **solo** si la request trae una credencial BFF válida (`X-Hub-Bff-Credential`, lista vigente+anterior para
rotar); si no, usa `REMOTE_ADDR`. Throttles de DRF (mecanismo base de SPEC-00) sobre Redis: `login_start_ip` y
`login_complete_ip` a 10/min cada uno (clave = `sha256(ip)` truncado) y `refresh_session` a 30/min (clave = `sid`
embebido en el refresh token `rt1.<sid>.<secreto>`, sin consultar la BD). El throttle corre antes de la vista, o sea
antes de llamar a Google. El proxy catch-all no manda la credencial BFF, así que nunca puede alcanzar un endpoint que
emite tokens (además de la denylist de `auth/bff/**` y la respuesta `404` sin credencial).

### 10. Librerías (C-13; versiones verificadas en PyPI/npm el 2026-10-31)
- **`PyJWT[crypto]==2.15.1`**: emisión/verificación del JWT del Hub y verificación del ID token de Google.
  `PyJWKClient(jwks_uri, cache_jwk_set=True, lifespan=3600, timeout=5)` cachea el JWKS por proceso y, ante un `kid`
  desconocido, refresca una vez con *cooldown* (30 s por defecto, contra abuso con `kid` aleatorios). Si el JWKS no se
  puede bajar y no hay caché → `google_unavailable` (nunca se acepta sin verificar). `leeway=60` aplica a `exp`, `nbf`
  e `iat` futuro. `require=[exp, iat, nbf, iss, aud, sub, sid]` para el JWT propio; `issuer` del ID token =
  `{"https://accounts.google.com", "accounts.google.com"}`, `algorithms=["RS256"]`.
- **`cryptography==50.0.2`** (backend de PyJWT; si SPEC-00 ya lo fija, se usa la misma versión del lock).
- **`httpx==0.28.1`** para el canje del código (`Timeout(8.0, connect=3.0)`, sin reintentos: el código es de un solo
  uso). Si SPEC-00/03 ya fijó un cliente HTTP, se usa ese y esta línea se descarta.
- **Frontend: ninguna dependencia nueva** (`node:crypto`, `next/server`, `cookies()`). Con Next.js 16 el archivo de
  borde es `proxy.ts` (renombre de `middleware.ts`) y corre en Node.js.
- Descartadas: Authlib (su cliente Django guarda `state` en la sesión de Django, que no usamos), `google-auth`
  (solo cubre el ID token y arrastra `requests`), `ua-parser` (alcanza una función pura), Redis en Next.js.

### 11. Puertos con SPEC-02, stubs y comando de bootstrap
`InvitationPort.find_valid_invitations(email_normalizado, now) -> list[InvitationRef]` (plural, Q-120 a) **bloquea**
las filas (`SELECT … FOR UPDATE`) dentro de la transacción del caller; `accept_invitations(invitations, user_id, now)`
acepta todas o lanza (`InvitationsNoLongerValid` → `not_invited`; cualquier otra → error), sin commitear. Orden dentro
de una sola `transaction.atomic()`: insertar usuario → buscar y bloquear invitaciones → aceptar → abrir sesión →
auditar. Insertar primero hace que un segundo callback concurrente espere el índice único de `google_sub`, reciba
`IntegrityError`, reintente una vez y entre por el caso (a) (AC-IDA-02). `MembershipSelectorPort.list_active_memberships(user_id)`
para `/api/me`. Stubs por settings (`NullInvitationPort`, `EmptyMembershipSelector`, `LogAuditPort`) hasta que existan
SPEC-02/SPEC-10; identity no importa `tenancy` (resolución por dotted path). El comando **`tenancy_create_org`
vive en `apps/tenancy`** (SPEC-02 es dueña de crear organizaciones e invitaciones; Q-123: sirve para toda
organización nueva, idempotente, auditado). Los comandos `deactivate_user`/`reactivate_user` viven en `apps/identity`.

### 12. Vencimiento y purga
`status` **materializado** (`active`/`revoked`/`expired`) con `ended_at`, y además **chequeo derivado** por marcas de
tiempo en cada request y refresh (nunca se confía solo en el estado materializado). El refresh que encuentra una
sesión vencida la marca `expired` en el acto (AC-IDA-16). Una tarea Celery beat **horaria** e idempotente materializa
el resto (`ended_at = idle_expires_at`, que por constraint nunca supera la vida absoluta), borra intentos de login
vencidos y purga sesiones con `ended_at` de hace más de 90 días (refresh tokens en cascada), en lotes. Transiciones
solo por `UPDATE … WHERE status='active'`: una sesión terminal no vuelve.

### 13. Nuevo login en un navegador que ya tenía sesión
La anterior se **revoca** (`revoke_reason = superseded`, auditado como `session_revoked`, actor `system`): el BFF, al
completar un login, si había un `__Host-cpu_rt` distinto, llama *best effort* a `auth/bff/logout` con
`reason=superseded`. Evita sesiones huérfanas en cajas compartidas. Si el BFF falla después de que Django creó la
sesión y antes de responder, intenta el mismo logout con el refresh nuevo; si eso también falla, la sesión huérfana
vence por inactividad y la persona la ve y la puede cerrar en "Seguridad".

### 14. Entornos, flag y proveedor falso (Q-122 b)
Client ID/secret y redirect URI de Google **por entorno**; staging usa Google real. Flag
`FEATURE_IDENTITY_GOOGLE_LOGIN` (de `apps/common`, apagado por defecto en producción hasta verificar):
`login/start` y `login/complete` responden `503 login_disabled`; refresh, logout y sesiones existentes siguen
funcionando. Proveedor OIDC falso (`IDENTITY_OIDC_PROVIDER=fake`, vistas `apps/identity/dev_oidc/`) solo con
`APP_ENV ∈ {local, test}`: `IdentityConfig.ready()` lanza `ImproperlyConfigured` (el proceso **no arranca**) si está
activo en otro entorno, y en staging/producción además se exige el issuer y los endpoints exactos de Google; las URLs
de `dev_oidc` solo se montan con el proveedor falso. Los tests de pytest no usan el proveedor falso HTTP: sustituyen el
gateway por un fake en memoria.

### 15. Errores del callback hacia "Ingresar"
El BFF siempre termina en `302 /login?error=<code>` con `code` de una **allowlist** (`login_cancelled`,
`google_auth_failed`, `google_unavailable`, `email_not_verified`, `not_invited`, `user_inactive`, `identity_conflict`,
`rate_limited`, `login_disabled`, `session_expired`, `internal_error`); cualquier otro valor se muestra como genérico.
Nunca detalles, tokens ni `state` en la URL. `error=access_denied` de Google se informa como `login_cancelled` (no se
audita: no es un rechazo del Hub). Respuestas de auth con `Cache-Control: no-store` y el callback con
`Referrer-Policy: no-referrer`; el access log del borde no registra la query del callback.

## Consecuencias
- **Se gana:** ningún token al alcance de JavaScript; revocación efectiva en la request siguiente; reglas de acceso y
  secretos de Google en un solo servicio; BFF sin estado compartido (escala horizontal sin Redis en Next.js); rotación
  de la clave JWT sin desloguear a nadie; cero dependencias nuevas en el frontend y tres en el backend.
- **Se paga:** una lectura de BD por request autenticada; un salto más en el login; ventana de gracia de 30 s como
  superficie acotada; el BFF deja de ser un *pass-through* puro (más código en `lib/bff/`, todo testeable sin red).
- **Riesgo residual:** si se pierde la respuesta del refresh que rotó y llega solo la de gracia, el navegador queda con
  un refresh usado y el próximo refresh se toma como reuso (re-login). Raro; se mide.
- **Pendiente, sin bloquear la aceptación:** con SPEC-00, la lista de modelos globales exentos del test C-01, los throttles generales por usuario y que
  el access log del borde no registre la query del callback; aplicar el texto de `07 §3.2` (design §13). Q-124 y Q-125
  quedaron decididas el 2026-11-06 (`specs/01-identity-access/clarifications.md`).

## Historial de cambios
| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-11-14 | §3: la clave de coalescencia del refresh en el BFF suma la IP del cliente y el User-Agent al hash del token | Decisión del dueño al revisar T-IDA-23 (PR #99): un token robado presentado durante un refresh legítimo no debe recibir el par rotado |
