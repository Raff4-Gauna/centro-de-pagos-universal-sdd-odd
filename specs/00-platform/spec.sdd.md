---
id: SPEC-00
modulo: platform
estado: Approved
track: S
version: 1.0.5
depende_de: []
actualizado: 2026-11-02
---

# Módulo de Plataforma (fundaciones)

## 1. Contexto y problema
Todavía no hay una línea de código. Si cada módulo arma su propio entorno, logging, settings o chequeos, las reglas
`C-01`, `C-09`, `C-11`, `C-13`–`C-17` quedan como intención y no como algo que el build hace cumplir. Esta spec
convierte `context/08-control-de-versiones-ci-cd.md` (y `ADR-0009`/`ADR-0010`) en reglas y criterios verificables:
entorno reproducible en contenedores, configuración segura, observabilidad y un pipeline de CI que bloquea lo que
viola la constitución desde el primer commit. No implementa ninguna regla de negocio.

## 2. Objetivo
Permitir que cualquier persona o agente levante el Hub completo con un comando y que **ningún cambio que viole
C-01/C-09/C-14/C-15/C-16/C-17 o filtre un secreto pueda llegar a `main`**, porque un chequeo automático lo bloquea.

## 3. Alcance
### 3.1 Incluido
- Estructura del repo (`backend/`, `frontend/`, `infra/`, `scripts/`, `.github/workflows/`) según los README de cada carpeta.
- Docker Compose de desarrollo: PostgreSQL, Redis, backend Django/DRF, worker Celery, beat, frontend Next.js.
- Settings por entorno (`base`/`dev`/`test`/`prod`) con validación al arrancar; `.env.example` commiteado.
- Logging estructurado JSON a stdout con `request_id`/`task_id` propagado frontend → BFF → backend → Celery.
- Healthchecks `/healthz` (liveness) y `/readyz` (readiness).
- Pipeline de GitHub Actions, **pasos 1 a 9** de `08 §3` (lint → tamaño → secretos → type-check → arquitectura →
  tests → cobertura → migraciones → build), y pre-commit local (`08 §3.1`).
- Test de arquitectura `C-01`/`C-09` y chequeo de migraciones reversibles `C-17`, probados con casos sintéticos.
- Contrato OpenAPI generado y versionado en `specs/_contracts/openapi.yaml` + tipos del frontend (ADR-0005, Q-035).
- Protección de la rama `main` del repo **público** `Raff4-Gauna/centro-de-pagos-universal-sdd-odd` (ruleset +
  check de zona roja + ajustes de seguridad del repo, Q-042) y su script de verificación.
- Mecanismo de throttling de DRF (Q-038) y chequeo de CI contra `float` en dinero (Q-047).
- Frontend base: **esqueleto** del shell `(dashboard)` y componentes/infra comunes de `07 §1–§3` (Q-045).
- Sección "Comandos de desarrollo" de `AGENTS.md` y `infra/scripts/README.md` (bitácora de scripts puntuales, `08 §5`).

### 3.2 Fuera de alcance
- **Paso 10 del pipeline** (deploy a staging/producción), proxy (nginx/Caddy), registry de imágenes y backups:
  dependen del hosting, sin elegir (Q-020, Q-049).
- Túnel ngrok/cloudflared (Q-020): lo configura el primer módulo o spike que reciba webhooks (S-001/05/07).
- Login, JWT, cookie de sesión, adjuntar `Authorization` en el BFF, protección de rutas (`01-identity-access`).
- Organizaciones, memberships, roles, sucursales, managers tenant-aware reales y datos del selector (`02`, Q-044).
- Modelo de usuario (`AUTH_USER_MODEL`) (`01`, Q-053). Auditoría (`10`). Cualquier proveedor o adaptador (`03`+).
- Pantallas reales de Inicio, Configuración y demás (cada módulo en su §14). Límites concretos de rate limiting (01/07/11).
- Feature flags por organización (02); 00 solo provee el helper por variable de entorno (Q-052).
- Cualquier tabla de negocio. Esta spec no toca zonas rojas de negocio, pero sus tareas de contrato OpenAPI,
  chequeo de migraciones y tests de arquitectura se tratan como **zona roja** (Q-051).

## 4. Actores y permisos
| Acción | owner | admin | operator | viewer | sistema/ERP | anónimo |
|---|---|---|---|---|---|---|
| `GET /healthz`, `GET /readyz`, health del BFF | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Ver el esqueleto del shell (sin datos) | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ provisorio (no hay login hasta 01) |
| Reenvío del BFF hacia el backend | ✔ | ✔ | ✔ | ✔ | ✘ (directo al backend) | ✔ provisorio (solo endpoints públicos en 00) |
| Encolar tarea de diagnóstico / Swagger UI | solo en `dev`/`test`, inexistente en `prod` (Q-056) | = | = | = | = | = |
| Llamar al backend directo desde el navegador | ✘ (CORS cerrado, Q-050) | ✘ | ✘ | ✘ | n/a | ✘ |

Actores técnicos: **desarrollador/agente** (corre Compose y pre-commit), **CI** (GitHub Actions, sin secretos),
**reviewer** (agente de solo lectura; su veredicto en zona roja es un comentario del PR que cita el SHA, Q-042),
**dueño del repo** (mergea, etiqueta y es el único que cambia ajustes; el agente abre los PR y puede mergear solo
con certeza total —pipeline completo en verde en el último commit, veredicto del reviewer sin bloqueantes, DoD
completo, squash—; ante cualquier duda mergea el dueño: Q-057) y **colaborador
externo** (repo público: puede forkear, abrir PR y comentar, nada más). Matriz completa en
`clarifications.md §H`.

## 5. Glosario del módulo
**BFF**: Route Handlers de Next.js (`app/api/`) que reenvían al backend sin lógica (`07 §3.2`). **request_id**:
identificador de correlación de una request, propagado entre componentes. **Liveness / readiness**: "el proceso
vive" / "puede atender (BD y Redis disponibles)". **Check requerido**: job de CI cuyo verde es condición de merge.
**BD descartable**: base creada para un job/entorno local que puede destruirse sin pérdida. **Ruleset**: conjunto
de reglas de GitHub que protege `main`. **Veredicto del reviewer**: comentario del PR, publicado con una cuenta con
permiso de escritura, que dice aprobado/rechazado y cita el SHA revisado.

## 6. Reglas de negocio (reglas de plataforma)
- **RN-PLT-01** El entorno de desarrollo completo corre en contenedores y se levanta con un único comando documentado; en el host solo se requieren Docker y las herramientas de pre-commit.
- **RN-PLT-02** La configuración llega solo por variables de entorno, validada con `pydantic-settings` (Q-040). Si falta una variable obligatoria o tiene formato inválido, el proceso **no arranca** y el error nombra la variable **sin imprimir ningún valor**. En `prod` son obligatorias `SECRET_KEY`, `ALLOWED_HOSTS`, URL de BD y URL de Redis, y `DEBUG` debe ser `False`.
- **RN-PLT-03** `.env` nunca se commitea. `.env.example` está commiteado, con valores ficticios, y lista **todas** las variables de plataforma que leen los settings.
- **RN-PLT-04** Las credenciales de proveedores **no** son configuración de plataforma: los settings del Hub no leen variables de credenciales de proveedores (Q-006, C-06, ADR-0003). Las variables de spikes viven **separadas** de las de plataforma (sección "solo spikes" de `.env.example` o `spikes/.env.example`, a elegir en design) y los settings nunca las leen (Q-048).
- **RN-PLT-05** Los logs operativos se emiten solo a stdout, en JSON, un evento por línea, con `timestamp` (ISO-8601 en UTC), `level`, `request_id` o `task_id`, `component`, `message` y `organization_id` cuando aplica (C-16, 08 §6), con `structlog` sobre `logging` estándar para Django, DRF, Celery y librerías (Q-034). Prohibido `print` y escribir logs a archivo.
- **RN-PLT-06** Ningún log incluye `Authorization`, `Cookie`, `Set-Cookie`, tokens, credenciales, query strings ni cuerpos crudos de request/response (C-06). El log de acceso registra método, **plantilla de ruta** (nunca el path crudo), status y `duration_ms` (Q-041).
- **RN-PLT-07** Toda request tiene un `request_id` **UUIDv4** que viaja en el header `X-Request-ID`: el BFF lo genera si falta, se propaga frontend → BFF → backend → tareas Celery (como header de la tarea) y se devuelve en la respuesta. Un valor entrante que no es un UUID válido se descarta y se genera uno nuevo (Q-041).
- **RN-PLT-08** Ningún archivo de código (`.py`, `.ts`, `.tsx`, `.jsx`) supera **400 líneas físicas** (401 falla), **tests incluidos** (C-14, ADR-0009). Lo verifica `scripts/check_file_size.py` (raíz del repo) en pre-commit y en CI; solo excluye migraciones, fixtures y archivos generados (`frontend/src/types/`, `next-env.d.ts`), con la lista explícita en el script (Q-043; `context/legacy-source/`: Q-055).
- **RN-PLT-09** La frontera del adaptador (C-09: nada fuera de `providers/` importa de `providers/*`) y la tenencia (C-01: sin `Model.objects` crudo en `services/`) se verifican con tests de arquitectura en CI **desde el primer commit**, aunque todavía no existan apps de negocio.
- **RN-PLT-10** Toda migración es reversible y se prueba aplicar → revertir → reaplicar en una BD descartable; no puede faltar una migración; esquema y datos van en migraciones separadas; los nombres son descriptivos (C-17, 08 §5).
- **RN-PLT-11** El pipeline ejecuta los pasos 1–9 de `08 §3` en ese orden, cada uno bloqueante, con fail-fast: el build (paso 9) solo corre si pasaron todos los anteriores. Herramientas (Q-031, Q-033): `ruff` (lint + format), `eslint` + `prettier`, `mypy` (+ stubs de Django y DRF), `tsc --noEmit` (`strict`), `pytest` + `pytest-django`, `vitest` + Testing Library.
- **RN-PLT-12** A `main` solo se llega por PR con todos los checks requeridos en verde y merge por squash. Un ruleset sobre `main` impide push directo, force-push y borrado, exige **0 aprobaciones** (un solo desarrollador no puede aprobarse a sí mismo) y **no tiene actores con bypass** (C-15, Q-042). Un PR con label `zona-roja`, o que toca rutas de zona roja (lista en design), solo pasa el check `zona-roja` si tiene el label y un veredicto "aprobado" del `reviewer` publicado por una cuenta con permiso de escritura que cita el SHA del último commit del PR.
- **RN-PLT-13** El escaneo de secretos (`gitleaks`) es bloqueante en pre-commit (archivos staged) y en CI (commits del PR), con allowlist acotada a placeholders `<ver .env: …>` (C-06, 08 §3.3, Q-037). Además están activos el secret scanning y la push protection de GitHub.
- **RN-PLT-14** Las dependencias están fijadas con lockfile commiteado — backend `uv` (`pyproject.toml` + `uv.lock`), frontend `pnpm` (`pnpm-lock.yaml`) — y CI/imágenes instalan solo desde el lockfile congelado (C-13, Q-030). Versiones mayores según Q-029; imágenes base por tag exacto (idealmente digest). `pip-audit` y `pnpm audit` bloquean severidad alta/crítica, con excepciones con fecha de vencimiento; Dependabot semanal (Q-037).
- **RN-PLT-15** El contrato de la API es el OpenAPI que genera `drf-spectacular`, commiteado en `specs/_contracts/openapi.yaml`; los tipos del frontend se generan con `openapi-typescript` desde ese archivo; un contrato o tipos desactualizados hacen fallar CI (ADR-0005, Q-035). La API queda en `/api/` sin versión en la URL (versión en `info.version`) y los errores usan un sobre único `application/problem+json` (RFC 9457) con `code` estable y `request_id`, sin trazas ni secretos (Q-036).
- **RN-PLT-16** El frontend no contiene reglas de negocio; el BFF es pass-through y en 00 no agrega autenticación (07 §3.2). El navegador habla **solo** con el BFF (mismo origen; CORS del backend cerrado); la URL del backend solo existe del lado servidor de Next y ningún secreto ni URL interna lleva prefijo `NEXT_PUBLIC_` (Q-050).
- **RN-PLT-17** `/healthz` no depende de servicios externos y devuelve estado y SHA corto de la versión; `/readyz` verifica BD y Redis. Ninguno expone otros detalles internos (versiones de dependencias, hosts, trazas) (Q-039).
- **RN-PLT-18** El repo es **público** (Q-042): nada sensible entra nunca al repo, en ningún commit. Los workflows corren sin secretos, con `GITHUB_TOKEN` de solo lectura por defecto (permisos extra solo por job y justificados) y **nunca** usan `pull_request_target`; los PR de forks corren sin secretos. Antes de cambiar la visibilidad a público, gitleaks sobre **todo el historial** da 0 hallazgos y se resuelve Q-054.
- **RN-PLT-19** La API tiene un mecanismo de throttling de DRF con caché en Redis que responde `429` con `Retry-After`; en 00 solo hay un límite global por defecto, generoso, para anónimos (valor en design); los límites concretos de login, webhooks y API keys los fijan 01, 07 y 11 (Q-038).
- **RN-PLT-20** CI rechaza `FloatField` en modelos y `float(` en `apps/**/{domain,services,selectors,api}/` (fuera de `providers/`), salvo entradas de una allowlist explícita y comentada (C-02, Q-047).

## 7. Requisitos funcionales
- **RF-PLT-01** Crear la estructura de carpetas de `backend/README.md`, `frontend/README.md` y `infra/README.md` (sin apps de negocio), `scripts/` en la raíz, `.gitattributes` y `infra/scripts/README.md`. (RN-PLT-01, RN-PLT-08)
- **RF-PLT-02** `docker compose` con servicios `db`, `redis`, `backend`, `worker`, `beat`, `frontend`; healthcheck por servicio, arranque ordenado por salud, volúmenes nombrados, una sola réplica de `beat`, `migrate` fuera del entrypoint de `worker`/`beat`, y un comando documentado para recrear la BD. (RN-PLT-01)
- **RF-PLT-03** Settings `base`/`dev`/`test`/`prod` con `pydantic-settings`, `USE_TZ=True`, `TIME_ZONE="America/Argentina/Buenos_Aires"`, `LANGUAGE_CODE="es-ar"` (Q-040, Q-046). (RN-PLT-02)
- **RF-PLT-04** `.env.example` (variables de spikes separadas) + test de paridad entre las variables que leen los settings y la parte de plataforma del archivo. (RN-PLT-03, RN-PLT-04)
- **RF-PLT-05** Logger `structlog` único configurado para Django, DRF, Celery y librerías; middleware de request y hooks de tarea Celery que agregan los campos de RN-PLT-05 y la redacción de RN-PLT-06. (RN-PLT-05..07)
- **RF-PLT-06** BFF en `frontend/src/app/api/` que reenvía al backend y genera/propaga `X-Request-ID`. (RN-PLT-07, RN-PLT-16)
- **RF-PLT-07** `GET /healthz` y `GET /readyz` en backend y un health del frontend/BFF; smoke del paso 9 con `docker compose up --wait` + `/readyz` = 200. (RN-PLT-17)
- **RF-PLT-08** `scripts/check_file_size.py` con exclusiones explícitas, invocable desde pre-commit y CI. (RN-PLT-08)
- **RF-PLT-09** Tests de arquitectura en `backend/tests/architecture/` para C-01 y C-09, con módulos sintéticos de prueba que demuestran que el test detecta violaciones. (RN-PLT-09)
- **RF-PLT-10** Chequeo de migraciones: `makemigrations --check --dry-run`; aplicar/revertir/reaplicar todas las apps en BD descartable; rechazar operaciones irreversibles, mezcla de `RunPython` con operaciones de esquema y nombres `auto_`. (RN-PLT-10)
- **RF-PLT-11** Workflow de GitHub Actions en PR y push a `main` con los pasos 1–9, cada uno como check requerido, sin secretos, con `GITHUB_TOKEN` de solo lectura por defecto y sin `pull_request_target`; más el check `zona-roja` y un chequeo de la configuración de los workflows. (RN-PLT-11, RN-PLT-12, RN-PLT-18)
- **RF-PLT-12** Configuración de pre-commit: `ruff`, `eslint`/`prettier`, tamaño de archivo, `gitleaks`, fin de línea LF. (RN-PLT-08, RN-PLT-13)
- **RF-PLT-13** Configuración del repo público: ruleset sobre `main` (RN-PLT-12), merge solo squash, secret scanning + push protection, aprobación del dueño para workflows de colaboradores externos nuevos; script que consulta la API de GitHub y verifica esa configuración; procedimiento previo al cambio de visibilidad (gitleaks sobre todo el historial + Q-054). (RN-PLT-12, RN-PLT-13, RN-PLT-18)
- **RF-PLT-14** Generación de `openapi.yaml` (`drf-spectacular`, por comando) y de `frontend/src/types/` (`openapi-typescript`), con chequeo de diff en CI; manejador de errores de DRF con sobre `problem+json`. (RN-PLT-15)
- **RF-PLT-15** Frontend base: `design-tokens.ts`, tema MUI v9 + Tailwind (`preflight: false`, prefijo `tw-`), `PageSkeleton`, `EmptyState`, aviso de error con "Reintentar", `query-client.ts`, `api-client.ts` tipado y esqueleto del layout `(dashboard)` (Q-045). (RN-PLT-16)
- **RF-PLT-16** Completar "Comandos de desarrollo" en `AGENTS.md` (levantar, resetear BD, tests, lint, regenerar contrato). (RN-PLT-01)
- **RF-PLT-17** Throttling de DRF con caché en Redis, respuesta `429` + `Retry-After` y un límite global por defecto para anónimos. (RN-PLT-19)
- **RF-PLT-18** Chequeo de CI contra `float` en dinero con allowlist explícita y comentada. (RN-PLT-20)
- **RF-PLT-19** Helper mínimo de feature flags por variable de entorno en `apps/common`, apagado por defecto (C-17, Q-052).

## 8. Requisitos no funcionales
- **RNF-PLT-01** Seguridad de imágenes: multi-stage, usuario no root, sin dependencias de dev, sin `.env` ni `.git` dentro (`.dockerignore`).
- **RNF-PLT-02** Settings `prod` pasan `manage.py check --deploy` sin advertencias; `DEBUG=True` en `prod` impide arrancar.
- **RNF-PLT-03** Observabilidad: el log de cada request incluye `duration_ms` y status; el de cada tarea, duración y resultado.
- **RNF-PLT-04** Pre-commit solo corre chequeos rápidos (sin tests completos ni migraciones, `08 §3.1`).
- **RNF-PLT-05** Portabilidad: funciona en Windows 11 + Docker Desktop (engine Linux) y en runners Linux de GitHub Actions; LF forzado vía `.gitattributes`; hot-reload operativo con bind mounts de Windows.
- **RNF-PLT-06** CI no requiere credenciales de proveedores ni red externa para tests.
- **RNF-PLT-07** Reproducibilidad: dos builds del mismo commit instalan las mismas versiones.
- **RNF-PLT-08** Cobertura (Q-032): backend **≥ 85 %** de líneas y ramas; frontend **≥ 70 %** en `lib/`, `hooks/` y `modules/` (excluye `app/` y tipos generados). Bajar un umbral exige fila en el Historial de esta spec.
- **RNF-PLT-09** Type-check (Q-033): `mypy` `strict` en `apps/*/domain/` y `apps/common/`, `check_untyped_defs` en el resto; `tsc` con `strict: true`.

## 9. Modelo conceptual de datos
No aplica: 00 no crea tablas de negocio ni modelos propios (Q-044, Q-053). Las únicas migraciones que maneja son
las de apps sintéticas de test usadas para probar el chequeo de C-17.

## 10. Estados y transiciones
No aplica.

## 11. Contratos
- `GET /healthz` → `200` con cuerpo mínimo: estado y SHA corto de la versión. Sin auth.
- `GET /readyz` → `200` si BD y Redis responden; `503` si alguno falla, sin detalle interno. Sin auth.
- Esquema OpenAPI: archivo `specs/_contracts/openapi.yaml` (fuente de verdad), generado por comando con `drf-spectacular`; si además se sirve por HTTP, en qué entornos: Q-056 (recomendado: solo `dev`).
- API bajo `/api/` sin versión en la URL; versión en `info.version` del OpenAPI (revisar `/api/v1/` antes de SPEC-11).
- Errores: `application/problem+json` (RFC 9457) con `type`, `title`, `status`, `code` estable y `request_id`; nunca trazas, hosts ni secretos.
- Header `X-Request-ID` (UUIDv4) en request y response. `429` con `Retry-After` al exceder el throttle.
- Pipeline: nombres de jobs estables (son los checks requeridos de RN-PLT-12), incluido `zona-roja`.

## 12. Casos límite y excepciones
- Archivos con CRLF (editados en Windows) en scripts o entrypoints → fallan en contenedores Linux; `.gitattributes` y pre-commit lo impiden.
- Bind mounts de Windows no propagan eventos de archivo → hot-reload por polling (riesgo §15).
- Ruta del repo con caracteres no ASCII (`Programación-2026`) → los scripts no deben asumir ASCII en paths.
- Redis o PostgreSQL caídos al arrancar → backend vivo (`/healthz` 200) pero no listo (`/readyz` 503); el worker reintenta conexión con backoff, logueando cada intento, sin crashear en bucle silencioso; si no se recupera queda `unhealthy`.
- `X-Request-ID` entrante enorme, con saltos de línea o que no es UUID → se descarta y se genera uno nuevo.
- Placeholders `<ver .env: NOMBRE>` en docs → no son secretos; el escáner no debe marcarlos (allowlist acotada).
- Tipos generados desde OpenAPI superan 400 líneas → excluidos de `check_file_size`.
- `context/legacy-source/` tiene `.py` de más de 400 líneas y con `print` → excluido de los chequeos de código según Q-055 (recomendado).
- Dos PR que cambian el contrato a la vez → conflicto en `openapi.yaml`; se resuelve regenerando, nunca editando a mano.
- Dos PR que agregan migraciones a la misma app → dos hojas; CI falla y se resuelve rebaseando/renumerando.
- `worker` y `beat` arrancan a la vez que `backend` → ninguno corre `migrate` en su entrypoint (evita la carrera).
- La URL de webhook por integración (Q-015) contiene un ID no adivinable → el log de acceso registra la plantilla de ruta, no el path crudo.
- No hay apps con `services/` ni `providers/` todavía → los tests de arquitectura se prueban contra módulos sintéticos.
- Repo público: un tercero comenta "aprobado" en un PR de zona roja → el check lo ignora (sin permiso de escritura); un push después del veredicto → el veredicto ya no cita el último SHA y el check vuelve a fallar.
- Un PR de fork → CI corre sin secretos y sin permisos de escritura; el primer aporte de un externo espera la aprobación del dueño para correr.
- GitHub Actions caído → no se puede mergear (aceptado: sin bypass). PyPI/npm/Docker Hub caídos o con límite de descargas → el job falla y se reintenta.
- La API de GitHub falla o cambia su respuesta → el script de verificación de protección termina en error, nunca en éxito.
- Healthchecks de Compose cada pocos segundos → no deben tapar los logs útiles (nivel de esas líneas en design).
- Fechas: BD en UTC, logs en ISO-8601 UTC, runners en UTC; un test que dependa de la hora usa reloj fijo.

## 13. Criterios de aceptación
- **AC-PLT-01** (RN-PLT-01) **Dado** un clon limpio con `.env` copiado de `.env.example` **cuando** se ejecuta el comando documentado de arranque **entonces** los seis servicios quedan `healthy` y `GET /healthz` responde 200.
- **AC-PLT-02** (RN-PLT-17) **Dado** el stack levantado **cuando** se consulta `/readyz` **entonces** responde 200; **y** con Redis detenido responde 503 sin hosts, versiones ni trazas en el cuerpo, mientras `/healthz` sigue en 200 con estado y SHA corto.
- **AC-PLT-03** (RN-PLT-02) **Dado** settings `prod` sin una variable obligatoria **cuando** arranca el proceso **entonces** falla con un error que nombra la variable y no contiene el valor de ninguna otra variable.
- **AC-PLT-04** (RNF-PLT-02) **Dado** settings `prod` válidos **cuando** corre `check --deploy` **entonces** no hay advertencias; **y** con `DEBUG=True` el arranque falla.
- **AC-PLT-05** (RN-PLT-03) **Dado** que los settings leen una variable que no figura en la parte de plataforma de `.env.example` **cuando** corre el test de paridad **entonces** falla nombrando la variable.
- **AC-PLT-06** (RN-PLT-04) **Dado** el código de `config/` y `apps/` **cuando** corre el test de configuración **entonces** ninguna lectura de entorno corresponde a credenciales de proveedores ni a variables de la sección de spikes (lista de patrones en design).
- **AC-PLT-07** (RN-PLT-05) **Dado** una request al backend **cuando** se captura stdout **entonces** hay una línea JSON válida con todos los campos obligatorios (`timestamp` ISO-8601 UTC) y `duration_ms`, y el `request_id` es igual al header `X-Request-ID` de la respuesta.
- **AC-PLT-08** (RN-PLT-06) **Dado** una request con `Authorization: Bearer <valor>`, `Cookie` y query string a una ruta con parámetro de path **cuando** se captura stdout **entonces** ninguno de esos valores aparece en ningún log, y el log de acceso muestra la plantilla de ruta y no el path crudo.
- **AC-PLT-09** (RN-PLT-07) **Dado** un `X-Request-ID` UUIDv4 válido **cuando** llega al backend **entonces** se conserva en log y respuesta; **y** uno inválido (no UUID o con salto de línea) se reemplaza por un UUIDv4 nuevo.
- **AC-PLT-10** (RN-PLT-07) **Dado** una request del navegador al BFF sin `X-Request-ID` **cuando** el BFF la reenvía **entonces** el backend loguea el mismo `request_id` que el BFF generó y devolvió.
- **AC-PLT-11** (RN-PLT-05, RN-PLT-07) **Dado** una request que encola una tarea de diagnóstico (en qué entornos existe: Q-056) **cuando** el worker la ejecuta **entonces** el log de la tarea es JSON e incluye `task_id` y el `request_id` de la request de origen.
- **AC-PLT-12** (RN-PLT-05) **Dado** un `print(...)` en código de `backend/apps/` **cuando** corre el lint **entonces** falla (`ruff`, regla `T20`).
- **AC-PLT-13** (RN-PLT-08) **Dado** un `.py`/`.ts`/`.tsx`/`.jsx` de 401 líneas, incluido un archivo de tests **cuando** corre `scripts/check_file_size.py` en pre-commit o CI **entonces** falla nombrando el archivo; **y** uno de exactamente 400 líneas, una migración o un archivo generado excluido (`frontend/src/types/…`) no lo hacen fallar.
- **AC-PLT-14** (RN-PLT-09) **Dado** un módulo sintético en `apps/charges/services/` que importa `apps.integrations.providers.mercadopago` **cuando** corre el test de arquitectura **entonces** falla; **y** el mismo import dentro de `providers/mercadopago/` no falla.
- **AC-PLT-15** (RN-PLT-09) **Dado** un módulo sintético en `services/` que usa `Model.objects` **cuando** corre el test de arquitectura **entonces** falla.
- **AC-PLT-16** (RN-PLT-10) **Dado** un cambio de modelo sin migración **cuando** corre el paso 8 **entonces** falla por `makemigrations --check`.
- **AC-PLT-17** (RN-PLT-10) **Dado** una migración con `RunPython` sin `reverse_code` (o `RunSQL` sin `reverse_sql`) **cuando** corre el chequeo **entonces** falla; **y** una migración reversible pasa aplicar → revertir → reaplicar en BD descartable.
- **AC-PLT-18** (RN-PLT-10) **Dado** una migración llamada `NNNN_auto_<fecha>` o que mezcla `RunPython` con operaciones de esquema **cuando** corre el chequeo **entonces** falla.
- **AC-PLT-19** (RN-PLT-13) **Dado** un secreto de prueba con formato de token en el diff **cuando** corren pre-commit y el paso 3 de CI **entonces** ambos fallan; **y** un placeholder `<ver .env: MP_ACCESS_TOKEN>` no falla.
- **AC-PLT-20** (RN-PLT-11) **Dado** un PR con un error de lint **cuando** corre el pipeline **entonces** el paso 1 falla y el build (paso 9) no se ejecuta.
- **AC-PLT-21** (RN-PLT-11, RNF-PLT-09) **Dado** un error de tipos en backend o frontend **cuando** corre el paso 4 **entonces** falla (`mypy` con `django-stubs`/`djangorestframework-stubs` en backend; `tsc --noEmit` con `strict` en frontend); **y** una función sin anotar en `apps/common/` o en un `domain/` también hace fallar `mypy` (modo `strict`).
- **AC-PLT-22** (RN-PLT-11, RNF-PLT-08) **Dado** una cobertura de backend menor a 85 % (líneas o ramas) o de frontend menor a 70 % en `lib/`, `hooks/` y `modules/` **cuando** corre el paso 7 **entonces** falla.
- **AC-PLT-23** (RN-PLT-15) **Dado** un cambio en la API sin regenerar `openapi.yaml`, o tipos del frontend desactualizados respecto de él **cuando** corre CI **entonces** falla mostrando el diff.
- **AC-PLT-24** (RN-PLT-12, RN-PLT-13, RN-PLT-18) **Dado** el repo público en GitHub **cuando** corre el script de verificación de protección **entonces** confirma: ruleset activo sobre `main` con PR obligatorio y 0 aprobaciones, checks requeridos = jobs del pipeline + `zona-roja`, solo squash, sin force-push ni borrado, sin actores con bypass, secret scanning y push protection activos; **y** si algo difiere, falla nombrando la diferencia; **y** un PR con un check rojo figura como no mergeable.
- **AC-PLT-25** (RN-PLT-14, RNF-PLT-01) **Dado** el paso 9 **cuando** construye las imágenes **entonces** instalan desde lockfile congelado (`uv.lock`, `pnpm-lock.yaml`), quedan etiquetadas con el SHA del commit y el proceso principal no corre como root.
- **AC-PLT-26** (RN-PLT-14) **Dado** una dependencia fijada con una vulnerabilidad conocida de severidad alta o crítica y sin excepción vigente **cuando** corre la auditoría (`pip-audit` / `pnpm audit`) **entonces** falla; **y** con una excepción vencida también falla.
- **AC-PLT-27** (RNF-PLT-05) **Dado** un `.sh` o `Dockerfile` con fin de línea CRLF **cuando** corre pre-commit **entonces** falla o lo normaliza a LF.
- **AC-PLT-28** (RN-PLT-16) **Dado** la ruta `(dashboard)` **cuando** se renderiza en test de componente **entonces** muestra barra superior con el lugar del selector empresa/sucursal y navegación a Inicio y Configuración; Inicio muestra `EmptyState` (nunca vacío), y un error de carga muestra un aviso con "Reintentar".
- **AC-PLT-29** (RN-PLT-16) **Dado** el build del frontend **cuando** se inspecciona el bundle del cliente **entonces** no contiene la URL interna del backend ni variables no `NEXT_PUBLIC_`.
- **AC-PLT-30** (RN-PLT-19) **Dado** el throttle global por defecto para anónimos **cuando** un cliente lo excede **entonces** el backend responde `429` con header `Retry-After` y sobre `problem+json`.
- **AC-PLT-31** (RN-PLT-20) **Dado** un `FloatField` en un modelo o `float(` en `apps/**/{domain,services,selectors,api}/` fuera de la allowlist **cuando** corre CI **entonces** falla; **y** el mismo `float(` dentro de `providers/` o en una entrada de la allowlist no falla.
- **AC-PLT-32** (RN-PLT-12) **Dado** un PR con label `zona-roja` o que toca rutas de zona roja **cuando** corre el check `zona-roja` **entonces** falla salvo que tenga el label y un veredicto "aprobado" publicado por una cuenta con permiso de escritura que cite el SHA del último commit; un veredicto de una cuenta sin permiso de escritura, o sobre un SHA anterior, no lo satisface.
- **AC-PLT-33** (RN-PLT-18) **Dado** un workflow en `.github/workflows/` que usa `pull_request_target` o que deja al `GITHUB_TOKEN` con permisos de escritura por defecto **cuando** corre el chequeo de configuración de workflows **entonces** falla nombrando el archivo.
- **AC-PLT-34** (RN-PLT-15) **Dado** un error no controlado en una vista de DRF **cuando** responde el backend **entonces** el cuerpo es `application/problem+json` con `code` y `request_id`, sin traza, hosts ni secretos.

## 14. Interfaz de usuario
Solo el **esqueleto** del shell de `07 §5`: layout `(dashboard)` con barra superior (lugar del selector
empresa/sucursal, deshabilitado y sin datos hasta 02), menú de usuario vacío (01), navegación a **Inicio** y
**Configuración**. Inicio: `EmptyState` con texto neutro. Configuración: secciones de `07 §5.3` deshabilitadas con
el módulo que las implementa. Estados: carga = `PageSkeleton`; vacío = `EmptyState`; error = aviso con "Reintentar"
(`07 §2`); sin permiso = no aplica hasta 01/02 (Q-045).

## 15. Riesgos y supuestos
- Decisión: el repo es **público** (Q-042) para tener protección de `main` sin costo. Riesgo: cualquier secreto o dato personal que entre en un commit queda expuesto para siempre (forks, caché, bots). Mitigación: gitleaks bloqueante en pre-commit y CI, secret scanning + push protection de GitHub, pasada sobre todo el historial antes de publicar, y Q-054 resuelta antes del cambio de visibilidad.
- Riesgo: con 0 aprobaciones y un solo humano, el control de C-15 descansa en los checks requeridos y en el check `zona-roja`; nada técnico impide que alguien con la cuenta del dueño mergee (Q-057).
- Riesgo: workflows mal configurados en un repo público (p. ej. `pull_request_target` o permisos de escritura) permitirían que un PR externo ejecute código con privilegios. Mitigación: RN-PLT-18 y AC-PLT-33.
- Riesgo: hot-reload lento o inexistente con bind mounts en Windows. Mitigación: polling en dev; documentarlo.
- Riesgo: el chequeo de migraciones da falsa confianza (una migración reversible puede perder datos al revertir). Mitigación: expand/contract (`08 §7`) en revisión.
- Riesgo: el pipeline se vuelve lento. Mitigación: fail-fast, caché de dependencias, pre-commit solo con lo rápido.
- Riesgo: si se corre `migrate` con el usuario por defecto de Django antes de 01, cambiar `AUTH_USER_MODEL` exige recrear la BD (Q-053). Supuesto: hasta 01 toda BD es descartable.

## 16. Preguntas abiertas
Detalle en `specs/00-platform/clarifications.md` §G. **Bloqueantes para *Clarified*: ninguna** (Q-042 decidida por
el usuario el 2026-10-31: repo público; Q-029..Q-053 decididas con su recomendación). *Designed* exige que el
architect escriba **ADR-0005** con la decisión de Q-035.

*Designed* (0.3.0): `design.md` + `ADR-0005` (Propuesto) escritos. Cerradas en `/design`: Q-055 y Q-056 (default
recomendado), Q-057 (decidida por el usuario: el agente mergea solo con certeza total).

Abiertas que no bloquean *Designed*:
- **Q-048** (parte del usuario): permitir a los agentes leer `.env.example` o renombrarlo — bloquea solo la tarea de RF-PLT-04.
- **Q-054** (decide el usuario): qué del contenido ya commiteado puede quedar público — **bloquea el cambio de visibilidad** (tarea de RF-PLT-13).
- **Q-058**: rutas del propio gate de CI como zona roja (recomendado: sí; aplicado provisoriamente en design).
- **Q-059** (decide el usuario): actualizar versiones de Q-029 ya superadas — conviene responderla antes de *Approved*.
- **Q-060**: prerrequisitos del host para pre-commit (recomendado: Node 24 + pnpm en el host).

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial (reemplaza el placeholder) | `/spec 00-platform` |
| 0.2.0 | 2026-10-31 | Estado → *Clarified*. Repo público: RN-PLT-12/13 reescritas, nueva RN-PLT-18, RF-PLT-11/13 ampliados, AC-PLT-24 ampliado, nuevos AC-PLT-32/33. RN/RF/AC con los valores decididos de Q-029..Q-053 (UUIDv4, 400 líneas con tests incluidos, uv/pnpm, structlog, pydantic-settings, mypy, cobertura 85/70, `problem+json`). Throttling y chequeo de C-02 pasan de "sujeto a" a RN-PLT-19/20 con AC-PLT-30/31 definitivos; nuevo RF-PLT-19 (feature flags, Q-052), RNF-PLT-08/09, AC-PLT-34. Matriz de permisos y casos límite completados (`clarifications.md §H–§I`). §15 sin el supuesto de repo privado. Nuevas Q-054..Q-057, ninguna bloquea *Clarified* | `/clarify 00-platform`: el usuario decidió Q-042 (repo público) y aceptó las recomendaciones de Q-012, Q-013, Q-027 y Q-029..Q-053 |
| 0.3.0 | 2026-10-31 | Estado → *Designed*. `design.md` (cobertura RN/RF/RNF sin huecos, Compose, pipeline, pre-commit, gobierno del repo, dependencias con versión exacta verificada) y `ADR-0005` (Propuesto). §4 y §16 actualizados: Q-055/Q-056 cerradas con su recomendación, Q-057 decidida por el usuario (el agente mergea solo con certeza total; si no, el dueño). Nuevas Q-058..Q-060 (no bloquean). Sin cambios en RN/RF/AC | `/design 00-platform`; decisión del usuario sobre Q-057 |
| 1.0.0 | 2026-10-31 | Estado → **Approved** por el dueño. Decididas Q-058 (las rutas del gate de CI son zona roja: reviewer obligatorio), Q-059 (Celery 5.6.3 + redis-py 6.4.0; MUI v9; Tailwind 3.4, DRF 3.16, Node 24 sin cambios) y Q-060 (default). Las versiones exactas de MUI v9 y su ecosistema se fijan y verifican en la primera tarea de frontend | Gate humano *Approved* (2026-10-31) |
| 1.0.1 | 2026-10-31 | RF-PLT-15: "tema MUI v7" → "tema MUI v9" | Alinear con Q-059 (decidida al aprobar); sin cambio de comportamiento |
| 1.0.2 | 2026-11-01 | Revisión de Q-059: DRF 3.16.1 → 3.18.2 (stubs de DRF/Django siguen en 3.16.9/5.2.9; `design.md §8`). Sin cambios en RN/RF/AC | Decisión del dueño (2026-11-01) por 3 advisories altas de DRF 3.16.1 detectadas por el auditor de dependencias |
| 1.0.3 | 2026-11-02 | Ajuste de diseño en `design.md §3.2.3` (redacción de logs, T-PLT-14): la redacción corre después de `format_exc_info`; claves agregadas (`location`, `proxy-authorization`, `auth`, `private_key`, `session`, `jwt`); reglas de texto (URL con credenciales, query, `clave[:=]valor`, Bearer/Basic); corte a 8 KB y regex de tiempo lineal; `captureWarnings`; `django.db.backends` en INFO; línea fija ante un error de render. Sin cambios en RN/RF/AC | Revisión de T-PLT-14 (B-1 ReDoS, B-2 diseño desalineado, N-1/N-2/N-3) y pendientes de las revisiones de T-PLT-12/13 |
| 1.0.4 | 2026-11-02 | Ajuste de diseño en `design.md §3.6` (pre-commit y gitleaks, T-PLT-04): regla propia `mercadopago-access-token` en `.gitleaks.toml` (`APP_USR-`/`TEST-`, además de `useDefault = true`) y repos de pre-commit fijados por SHA del commit en vez de tag. Sin cambios en RN/RF/AC | Revisión de T-PLT-04: las reglas por defecto de gitleaks no detectaban los tokens de Mercado Pago (hueco de C-06); el pin por SHA sigue el criterio de RN-PLT-14 |
| 1.0.5 | 2026-11-02 | Ajuste de diseño en `design.md §3.5`, `§3.6` y `§3.7.2` (escaneo de secretos, T-PLT-04): el job `secrets` usa `--ignore-gitleaks-allow` y `--log-opts="--diff-merges=first-parent --text <rango>"` y falla con un `.gitleaksignore` trackeado (cualquier caja) o con archivos trackeados en las rutas que la allowlist por defecto nunca escanea (salvo `.gitleaks.toml`, ruta roja); el hook, `--ignore-gitleaks-allow`; la allowlist de placeholders queda anclada (`^…$`); `**/.gitleaksignore` pasa a ruta de zona roja; el gate real es CI (el hook se saltea con `--no-verify` y con `-diff`). Nueva **Q-062** (decidida por defecto, opción b): se acepta la allowlist global de rutas que trae `useDefault`. **RN-PLT-13 se interpreta como "allowlist propia acotada a placeholders"**: las exclusiones por ruta de las reglas por defecto de gitleaks no cuentan como allowlist del repo. Sin cambios en RN/RF/AC | Revisión de `3d50418` (T-PLT-04): 5 evasiones del job `secrets` reproducidas con gitleaks v8.30.1 (B-1 a B-5) y la allowlist heredada (B-6) |
