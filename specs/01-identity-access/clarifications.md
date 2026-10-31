# Aclaraciones — Módulo 01-identity-access

> Rango reservado para este módulo: **Q-101…Q-199**. Redactado por el spec-writer el 2026-10-31; lo completa el
> clarifier. Las decisiones transversales de base están en `specs/00-platform/clarifications.md` (Q-001, Q-011,
> Q-012, Q-013) y **no** se editan desde acá.

## 1. Preguntas
| ID | Pregunta | Por qué importa | Opciones | Recomendación | ¿Bloquea? | Decisión (fecha) | Afecta |
|---|---|---|---|---|---|---|---|
| Q-101 | ¿Se confirma Q-012: solo Google, sin contraseñas propias, y alta de personas **solo por invitación**? (en 00 figura como recomendación, no como decisión) | Es la puerta de entrada; define toda la superficie de ataque | a) Solo Google + invitación · b) Sumar email/contraseña · c) Sumar otro IdP | a) | **Sí** | | RN-IDA-01, 05 |
| Q-102 | ¿Se confirma Q-013 / ADR-0004: tokens en cookie `httpOnly` gestionada por el BFF de Next.js, nunca accesibles por JS? | Define el contrato de login/refresh/logout y la protección CSRF; la propuesta §6.1 hace lo contrario | a) Cookie `httpOnly` vía BFF · b) Token en memoria/localStorage del cliente | a); ampliar `07 §3.2` (el BFF también setea, rota y borra la cookie) | **Sí** | | RN-IDA-12, 13, §11 |
| Q-103 | Modelo de sesión: ¿JWT de acceso corto + sesión revocable en servidor (refresh rotado con detección de reuso), o JWT puro sin estado? ¿Logout/desactivación cortan el acceso **en el acto** (chequeo de sesión/usuario activo por request) o recién al vencer el access token? | 07 §5.3 pide "sesiones activas / revocar sesión", imposible con JWT sin estado; dos pestañas refrescando a la vez pueden disparar falso reuso | a) Sesión en servidor + chequeo por request · b) Sesión en servidor, corte al vencer el access · c) Sin estado | a), con refresh serializado en el BFF o ventana de gracia corta para el reuso | **Sí** | | RN-IDA-07, 10, 11, §10, §12 |
| Q-104 | Duraciones: JWT de acceso, inactividad de sesión, vida absoluta, tolerancia de reloj | Seguridad vs. comodidad del operador en caja | — | Acceso 15 min · inactividad 7 días · absoluta 30 días · tolerancia 60 s | No | | RN-IDA-08, 11 |
| Q-105 | ¿Qué cuentas de Google se admiten: cualquiera con email verificado, o solo de ciertos dominios Workspace (`hd`)? | Pilotos pueden usar Gmail personal | a) Cualquiera; el control es la invitación · b) Lista de dominios por organización | a) | No | | RN-IDA-02, 05 |
| Q-106 | ¿Cómo nace el **primer** usuario owner (no hay registro público ni nadie que invite)? | Sin esto nadie puede entrar; es un punto de escalamiento de privilegios | a) Comando de gestión en el servidor que crea org + invitación owner para un email · b) Endpoint HTTP protegido · c) Admin de Django | a), sin endpoint HTTP, auditado | **Sí** | | RF-IDA-08, RN-IDA-05 |
| Q-107 | ¿Cómo se compara el email de la invitación con el de Google? | Evita aceptar a otra persona o rechazar a la correcta | a) Exacto tras recortar espacios y pasar a minúsculas · b) Además normalizar puntos/alias `+` de Gmail | a); con otro email → `not_invited` | No | | RN-IDA-05 |
| Q-108 | ¿Dónde vive la entidad Invitación y cómo se rompe la dependencia circular 01→02 (ROADMAP: 02 depende de 01, pero el login de 01 necesita invitaciones de 02)? | Orden de implementación en H1 y frontera de módulos | a) Invitación en SPEC-02; 01 define un puerto que 02 implementa (stub hasta entonces) · b) Invitación en SPEC-01 | a); 01 y 02 se cierran juntos en H1 | **Sí** | | RN-IDA-05, 06, §9, §11 |
| Q-109 | Una persona con usuario activo pero **sin memberships activas** (la sacaron de todas sus empresas): ¿puede iniciar sesión? | UX y superficie de acceso | a) Sí; `/api/me` sin empresas y pantalla "no pertenecés a ninguna empresa" · b) Rechazar login | a) | No | | RN-IDA-05, §14 |
| Q-110 | ¿Qué pasa si cambia el email de la cuenta de Google (mismo `sub`), o llega un `sub` nuevo con un email ya registrado? | Toma de cuenta por reciclado de email | — | `sub` manda; el email se actualiza en el login si está verificado y no colisiona (auditado); `sub` nuevo con email existente → rechazo `identity_conflict` + alerta | No | | RN-IDA-04, 17 |
| Q-111 | Umbrales de rate limiting de auth; ¿los `429` se auditan o solo se loguean? | Fuerza bruta / abuso sin bloquear a una caja legítima | — | Inicio y callback: 10/min por IP · refresh: 30/min por sesión · `429` solo a logs y métricas | No | | RN-IDA-15, 17 |
| Q-112 | 07 §5.1 dice que la empresa elegida "persiste en la sesión": ¿dónde se guarda? | Afecta el modelo de sesión y SPEC-02 | a) Guardada en la sesión del servidor, el backend valida membership siempre · b) Header por request elegido por el frontend · c) Claim en el JWT | a) o b); **nunca** c) (RN-IDA-09) — decidir junto con SPEC-02 | No | | RN-IDA-09, SPEC-02 |
| Q-113 | ¿Entra al MVP la pantalla "Seguridad" (listar y revocar sesiones propias, "cerrar las demás")? ¿Límite de sesiones concurrentes? ¿Qué dato del dispositivo se muestra? | 07 §5.3 la asigna a este módulo; la IP es dato personal | — | Sí; sin límite de sesiones; mostrar navegador/SO resumido y fechas, sin guardar IP completa | No | | RF-IDA-07, AC-IDA-25, §9 |
| Q-114 | ¿Qué devuelve `GET /api/me`? ¿Incluye las memberships (empresa, rol) para armar el selector? | Contrato entre 01, 02 y el shell | a) Solo identidad · b) Identidad + memberships activas vía selector de SPEC-02 | b) | No | | RF-IDA-06, §11 |
| Q-115 | "Mi perfil": ¿algún campo editable? 07 §5.3 menciona "idioma" pero 07 §6 dice "sin internacionalización" | Alcance de UI y datos guardados | — | Solo lectura desde Google (nombre, email, avatar); sin idioma | No | | RNF-IDA-05, §14 |
| Q-116 | ¿Existe un rol de **plataforma** (el operador del Hub, Q-001) que desactive usuarios o vea sesiones ajenas? ¿Admin de Django en producción? | Q-010 solo define roles por organización | — | Sin rol global en la API del MVP; desactivar/reactivar por comando de gestión auditado; admin de Django no expuesto en producción | No | | §4, RF-IDA-08, RN-IDA-07 |
| Q-117 | C-08 exige registrar "en qué organización"; los eventos de identidad no tienen una. ¿Se admite organización vacía? | Contrato con SPEC-10 | — | Organización nula para eventos globales; si el login acepta una invitación, se registra con la organización de esa invitación | No | | RN-IDA-17, SPEC-10 |
| Q-118 | Retención y borrado de datos de usuario y sesiones (Ley 25.326, relacionado con Q-021) | Cumplimiento | — | Desactivación lógica de usuarios; purga de sesiones vencidas/revocadas a los 90 días; borrado definitivo a definir con asesoría | No | | RNF-IDA-05 |

## 2. Matriz de permisos (borrador, a validar por el clarifier)
| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|
| Iniciar sesión con Google | ✔ | ✔ | ✔ | ✔ | ✘ |
| Refrescar / cerrar la propia sesión | ✔ | ✔ | ✔ | ✔ | ✘ |
| `GET /api/me` (propio) | ✔ | ✔ | ✔ | ✔ | ✘ |
| Listar / revocar sesiones propias | ✔ | ✔ | ✔ | ✔ | ✘ (Q-113) |
| Sesiones de otro usuario | ✘ | ✘ | ✘ | ✘ | ✘ (Q-116) |
| Desactivar / reactivar usuario | ✘ | ✘ | ✘ | ✘ | ✘ (Q-116) |

## 3. Checklist de casos límite (marcar o justificar "no aplica")
- [x] **Concurrencia:** callbacks simultáneos de la misma invitación; refresh desde dos pestañas (Q-103).
- [x] **Reintentos y repetición:** callback repetido (`state` de un solo uso), logout repetido (idempotente), reuso de refresh.
- [ ] **Orden:** invitación revocada entre inicio y callback — cubierto en §12; validar con SPEC-02.
- [x] **Fallas parciales:** falla al aceptar invitación tras validar Google (AC-IDA-05).
- [x] **Proveedor caído / lento / 429:** Google caído → rechazo recuperable; claves rotadas → refresco de JWKS.
- [ ] **Permisos:** persona sin memberships (Q-109); rol cambiado a mitad de sesión → no afecta al JWT (RN-IDA-09), validar con SPEC-02.
- [x] **Aislamiento:** sesión ajena por ID → `404` (AC-IDA-25); entidades de identidad son globales (spec §9).
- [x] **Estados terminales:** sesión `revoked`/`expired` no se reactiva.
- [x] **Montos:** no aplica (el módulo no maneja dinero).
- [x] **Vencimientos:** access token, inactividad, vida absoluta, `login_attempts` (Q-104).
- [ ] **Desactivación/borrado:** usuario desactivado con access token vigente (Q-103); retención (Q-118).
- [x] **Zona horaria:** UTC en BD (RNF-IDA-07).
- [ ] **Volumen:** listado de sesiones propias — paginación a definir en diseño si Q-113 entra.
- [x] **Datos vacíos / inválidos / muy largos / caracteres especiales:** `return_path` externo, emails con mayúsculas (Q-107).
- [ ] **Privacidad:** datos de Google y del dispositivo guardados (Q-113, Q-115, Q-118).
- [x] **Observabilidad:** RNF-IDA-03/04; logs sin tokens (AC-IDA-23).

## 4. Resumen para decisión
**Bloqueantes abiertas:** Q-101, Q-102, Q-103, Q-106, Q-108.
**Recomendaciones aceptadas:** ninguna todavía (pendiente de revisión del usuario).
