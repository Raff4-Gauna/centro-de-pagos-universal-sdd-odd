---
id: SPEC-00
modulo: platform
estado: Draft
track: S
version: 0.1.0
depende_de: []
actualizado: 2026-10-31
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
- Protección de la rama `main` del repo `Raff4-Gauna/centro-de-pagos-universal-sdd-odd` (sujeta a Q-042).
- Frontend base: **esqueleto** del shell `(dashboard)` y componentes/infra comunes de `07 §1–§3` (alcance exacto en Q-045).
- Sección "Comandos de desarrollo" de `AGENTS.md` y `infra/scripts/README.md` (bitácora de scripts puntuales, `08 §5`).

### 3.2 Fuera de alcance
- **Paso 10 del pipeline** (deploy a staging/producción), proxy (nginx/Caddy), registry de imágenes y backups:
  dependen del hosting, sin elegir (Q-020, Q-049).
- Túnel ngrok/cloudflared (Q-020): lo configura el primer módulo o spike que reciba webhooks (S-001/05/07).
- Login, JWT, cookie de sesión, adjuntar `Authorization` en el BFF, protección de rutas (`01-identity-access`).
- Organizaciones, memberships, roles, sucursales, managers tenant-aware reales y datos del selector (`02`, Q-044).
- Modelo de usuario (`AUTH_USER_MODEL`) (`01`, Q-053). Auditoría (`10`). Cualquier proveedor o adaptador (`03`+).
- Pantallas reales de Inicio, Configuración y demás (cada módulo en su §14). Límites concretos de rate limiting (01/07/11).
- Cualquier tabla de negocio. Esta spec no toca zonas rojas de negocio (ver Q-051 sobre las que protege).

## 4. Actores y permisos
| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|
| `GET /healthz`, `GET /readyz` | ✔ (anónimo) | ✔ | ✔ | ✔ | ✔ |
| Ver el esqueleto del shell (sin datos) | ✔ (sin control de acceso hasta 01/02) | ✔ | ✔ | ✔ | ✘ |

Actores técnicos: **desarrollador/agente** (corre Compose y pre-commit), **CI** (GitHub Actions), **reviewer**
(agente de solo lectura; cómo queda registrada su aprobación: Q-042).

## 5. Glosario del módulo
**BFF**: Route Handlers de Next.js (`app/api/`) que reenvían al backend sin lógica (`07 §3.2`). **request_id**:
identificador de correlación de una request, propagado entre componentes. **Liveness / readiness**: "el proceso
vive" / "puede atender (BD y Redis disponibles)". **Check requerido**: job de CI cuyo verde es condición de merge.
**BD descartable**: base creada para un job/entorno local que puede destruirse sin pérdida.

## 6. Reglas de negocio (reglas de plataforma)
- **RN-PLT-01** El entorno de desarrollo completo corre en contenedores y se levanta con un único comando documentado; en el host solo se requieren Docker y las herramientas de pre-commit.
- **RN-PLT-02** La configuración llega solo por variables de entorno. Si falta una variable obligatoria o tiene formato inválido, el proceso **no arranca** y el error nombra la variable **sin imprimir ningún valor**.
- **RN-PLT-03** `.env` nunca se commitea. `.env.example` está commiteado, con valores ficticios, y lista **todas** las variables que lee la plataforma.
- **RN-PLT-04** Las credenciales de proveedores **no** son configuración de plataforma: los settings del Hub no leen variables de credenciales de proveedores (Q-006, C-06, ADR-0003). Las variables de spikes se separan (Q-048).
- **RN-PLT-05** Los logs operativos se emiten solo a stdout, en JSON, un evento por línea, con `timestamp`, `level`, `request_id` o `task_id`, `component`, `message` y `organization_id` cuando aplica (C-16, 08 §6). Prohibido `print` y escribir logs a archivo.
- **RN-PLT-06** Ningún log incluye `Authorization`, `Cookie`, `Set-Cookie`, tokens, credenciales, query strings ni cuerpos crudos de request/response (C-06).
- **RN-PLT-07** Toda request tiene un `request_id`, que se propaga frontend → BFF → backend → tareas Celery y se devuelve en la respuesta. Un valor entrante inválido se reemplaza (formato en Q-041).
- **RN-PLT-08** Ningún archivo de código supera el límite de C-14; lo verifica `check_file_size` en pre-commit y en CI (umbral exacto, ubicación y exclusiones: Q-043).
- **RN-PLT-09** La frontera del adaptador (C-09: nada fuera de `providers/` importa de `providers/*`) y la tenencia (C-01: sin `Model.objects` crudo en `services/`) se verifican con tests de arquitectura en CI **desde el primer commit**, aunque todavía no existan apps de negocio.
- **RN-PLT-10** Toda migración es reversible y se prueba aplicar → revertir → reaplicar en una BD descartable; no puede faltar una migración; esquema y datos van en migraciones separadas; los nombres son descriptivos (C-17, 08 §5).
- **RN-PLT-11** El pipeline ejecuta los pasos 1–9 de `08 §3` en ese orden, cada uno bloqueante, con fail-fast: el build (paso 9) solo corre si pasaron todos los anteriores.
- **RN-PLT-12** A `main` solo se llega por PR con todos los checks requeridos en verde, merge por squash, sin push directo ni force-push (C-15; mecanismo sujeto a Q-042).
- **RN-PLT-13** El escaneo de secretos es bloqueante en pre-commit y en CI (C-06, 08 §3.3).
- **RN-PLT-14** Las dependencias están fijadas con lockfile commiteado y CI/imágenes instalan solo desde el lockfile (C-13; herramientas en Q-029/Q-030).
- **RN-PLT-15** El contrato de la API es el OpenAPI generado y commiteado en `specs/_contracts/openapi.yaml`; los tipos del frontend se generan desde ese archivo; un contrato o tipos desactualizados hacen fallar CI (ADR-0005, Q-035).
- **RN-PLT-16** El frontend no contiene reglas de negocio; el BFF es pass-through y en 00 no agrega autenticación (07 §3.2). Ningún secreto ni URL interna se expone con prefijo `NEXT_PUBLIC_`.
- **RN-PLT-17** `/healthz` no depende de servicios externos; `/readyz` verifica BD y Redis. Ninguno expone detalles internos (versiones de dependencias, hosts, trazas).

## 7. Requisitos funcionales
- **RF-PLT-01** Crear la estructura de carpetas de `backend/README.md`, `frontend/README.md` y `infra/README.md` (sin apps de negocio), `scripts/` en la raíz, `.gitattributes` y `infra/scripts/README.md`. (RN-PLT-01, RN-PLT-08)
- **RF-PLT-02** `docker compose` con servicios `db`, `redis`, `backend`, `worker`, `beat`, `frontend`; healthcheck por servicio, arranque ordenado por salud, volúmenes nombrados, y un comando documentado para recrear la BD. (RN-PLT-01)
- **RF-PLT-03** Settings `base`/`dev`/`test`/`prod` con validación tipada al arrancar (Q-040). (RN-PLT-02)
- **RF-PLT-04** `.env.example` + test de paridad entre las variables que leen los settings y las del archivo. (RN-PLT-03, RN-PLT-04)
- **RF-PLT-05** Logger estructurado único (Q-034) configurado para Django, DRF, Celery y librerías; middleware de request y hooks de tarea Celery que agregan los campos de RN-PLT-05 y la redacción de RN-PLT-06. (RN-PLT-05..07)
- **RF-PLT-06** BFF en `frontend/src/app/api/` que reenvía al backend y genera/propaga `X-Request-ID` (Q-041, Q-050). (RN-PLT-07, RN-PLT-16)
- **RF-PLT-07** `GET /healthz` y `GET /readyz` en backend y un health del frontend/BFF (Q-039). (RN-PLT-17)
- **RF-PLT-08** `check_file_size` con exclusiones explícitas (Q-043), invocable desde pre-commit y CI. (RN-PLT-08)
- **RF-PLT-09** Tests de arquitectura en `backend/tests/architecture/` para C-01 y C-09, con módulos sintéticos de prueba que demuestran que el test detecta violaciones. (RN-PLT-09)
- **RF-PLT-10** Chequeo de migraciones: `makemigrations --check --dry-run`; aplicar/revertir/reaplicar todas las apps en BD descartable; rechazar operaciones irreversibles, mezcla de `RunPython` con operaciones de esquema y nombres `auto_`. (RN-PLT-10)
- **RF-PLT-11** Workflow de GitHub Actions en PR y push a `main` con los pasos 1–9, cada uno como check requerido, sin secretos de proveedores. (RN-PLT-11)
- **RF-PLT-12** Configuración de pre-commit: lint, format, tamaño de archivo, escaneo de secretos, fin de línea LF. (RN-PLT-08, RN-PLT-13)
- **RF-PLT-13** Protección de `main` (Q-042) + script que consulta la API de GitHub y verifica la configuración esperada. (RN-PLT-12)
- **RF-PLT-14** Generación de `openapi.yaml` y de `frontend/src/types/`, con chequeo de diff en CI (Q-035). (RN-PLT-15)
- **RF-PLT-15** Frontend base: tokens de diseño, tema MUI + Tailwind (`preflight: false`, prefijo `tw-`), `PageSkeleton`, `EmptyState`, error con "Reintentar", `query-client`, `api-client` tipado y esqueleto del layout `(dashboard)` (Q-045). (RN-PLT-16)
- **RF-PLT-16** Completar "Comandos de desarrollo" en `AGENTS.md` (levantar, resetear BD, tests, lint, regenerar contrato). (RN-PLT-01)
- **RF-PLT-17** *(sujeto a Q-038)* Mecanismo de throttling de DRF con respuesta 429 + `Retry-After`.
- **RF-PLT-18** *(sujeto a Q-047)* Chequeo de CI contra `float` en dinero (C-02).

## 8. Requisitos no funcionales
- **RNF-PLT-01** Seguridad de imágenes: multi-stage, usuario no root, sin dependencias de dev, sin `.env` ni `.git` dentro (`.dockerignore`).
- **RNF-PLT-02** Settings `prod` pasan `manage.py check --deploy` sin advertencias; `DEBUG=True` en `prod` impide arrancar.
- **RNF-PLT-03** Observabilidad: el log de cada request incluye `duration_ms` y status; el de cada tarea, duración y resultado.
- **RNF-PLT-04** Pre-commit solo corre chequeos rápidos (sin tests completos ni migraciones, `08 §3.1`).
- **RNF-PLT-05** Portabilidad: funciona en Windows 11 + Docker Desktop (engine Linux) y en runners Linux de GitHub Actions; LF forzado vía `.gitattributes`; hot-reload operativo con bind mounts de Windows.
- **RNF-PLT-06** CI no requiere credenciales de proveedores ni red externa para tests.
- **RNF-PLT-07** Reproducibilidad: dos builds del mismo commit instalan las mismas versiones.

## 9. Modelo conceptual de datos
No aplica: 00 no crea tablas de negocio ni modelos propios (Q-044, Q-053). Las únicas migraciones que maneja son
las de apps sintéticas de test usadas para probar el chequeo de C-17.

## 10. Estados y transiciones
No aplica.

## 11. Contratos
- `GET /healthz` → `200` con cuerpo mínimo (estado y, según Q-039, versión corta). Sin auth.
- `GET /readyz` → `200` si BD y Redis responden; `503` si alguno falla, sin detalle interno. Sin auth.
- Esquema OpenAPI: archivo `specs/_contracts/openapi.yaml` (fuente de verdad) y endpoint de generación (Q-035).
- Header `X-Request-ID` en request y response (formato Q-041). Sobre de errores de la API: Q-036.
- Pipeline: nombres de jobs estables (son los checks requeridos de RN-PLT-12).

## 12. Casos límite y excepciones
- Archivos con CRLF (editados en Windows) en scripts o entrypoints → fallan en contenedores Linux; `.gitattributes` y pre-commit lo impiden.
- Bind mounts de Windows no propagan eventos de archivo → hot-reload por polling (riesgo §15).
- Ruta del repo con caracteres no ASCII (`Programación-2026`) → los scripts no deben asumir ASCII en paths.
- Redis o PostgreSQL caídos al arrancar → backend vivo (`/healthz` 200) pero no listo (`/readyz` 503); el worker reintenta conexión sin crashear en bucle silencioso.
- `X-Request-ID` entrante enorme, con saltos de línea o no válido → se descarta y se genera uno nuevo.
- Placeholders `<ver .env: NOMBRE>` en docs → no son secretos; el escáner no debe marcarlos (allowlist acotada).
- Tipos generados desde OpenAPI superan 400 líneas → excluidos de `check_file_size` (Q-043).
- Dos PR que cambian el contrato a la vez → conflicto en `openapi.yaml`; se resuelve regenerando, nunca editando a mano.
- La URL de webhook por integración (Q-015) contiene un ID no adivinable → el log de acceso no registra el path crudo (Q-041).
- No hay apps con `services/` ni `providers/` todavía → los tests de arquitectura se prueban contra módulos sintéticos.

## 13. Criterios de aceptación
- **AC-PLT-01** (RN-PLT-01) **Dado** un clon limpio con `.env` copiado de `.env.example` **cuando** se ejecuta el comando documentado de arranque **entonces** los seis servicios quedan `healthy` y `GET /healthz` responde 200.
- **AC-PLT-02** (RN-PLT-17) **Dado** el stack levantado **cuando** se consulta `/readyz` **entonces** responde 200; **y** con Redis detenido responde 503 sin hosts, versiones ni trazas en el cuerpo, mientras `/healthz` sigue en 200.
- **AC-PLT-03** (RN-PLT-02) **Dado** settings `prod` sin una variable obligatoria **cuando** arranca el proceso **entonces** falla con un error que nombra la variable y no contiene el valor de ninguna otra variable.
- **AC-PLT-04** (RNF-PLT-02) **Dado** settings `prod` válidos **cuando** corre `check --deploy` **entonces** no hay advertencias; **y** con `DEBUG=True` el arranque falla.
- **AC-PLT-05** (RN-PLT-03) **Dado** que los settings leen una variable que no figura en `.env.example` **cuando** corre el test de paridad **entonces** falla nombrando la variable.
- **AC-PLT-06** (RN-PLT-04) **Dado** el código de `config/` y `apps/` **cuando** corre el test de configuración **entonces** ninguna lectura de entorno corresponde a credenciales de proveedores (lista de patrones en design).
- **AC-PLT-07** (RN-PLT-05) **Dado** una request al backend **cuando** se captura stdout **entonces** hay una línea JSON válida con todos los campos obligatorios y `duration_ms`, y el `request_id` es igual al header `X-Request-ID` de la respuesta.
- **AC-PLT-08** (RN-PLT-06) **Dado** una request con `Authorization: Bearer <valor>`, `Cookie` y query string **cuando** se captura stdout **entonces** ninguno de esos valores aparece en ningún log.
- **AC-PLT-09** (RN-PLT-07) **Dado** un `X-Request-ID` válido **cuando** llega al backend **entonces** se conserva en log y respuesta; **y** uno inválido (formato incorrecto o con salto de línea) se reemplaza por uno nuevo.
- **AC-PLT-10** (RN-PLT-07) **Dado** una request del navegador al BFF sin `X-Request-ID` **cuando** el BFF la reenvía **entonces** el backend loguea el mismo `request_id` que el BFF generó y devolvió.
- **AC-PLT-11** (RN-PLT-05, RN-PLT-07) **Dado** una request que encola una tarea de diagnóstico **cuando** el worker la ejecuta **entonces** el log de la tarea es JSON e incluye `task_id` y el `request_id` de la request de origen.
- **AC-PLT-12** (RN-PLT-05) **Dado** un `print(...)` en código de `backend/apps/` **cuando** corre el lint **entonces** falla.
- **AC-PLT-13** (RN-PLT-08) **Dado** un `.py`/`.ts`/`.tsx`/`.jsx` que supera el umbral por una línea (según Q-043: 401) **cuando** corre `check_file_size` en pre-commit o CI **entonces** falla nombrando el archivo; **y** uno exactamente en el umbral, una migración o un archivo generado excluido no lo hacen fallar.
- **AC-PLT-14** (RN-PLT-09) **Dado** un módulo sintético en `apps/charges/services/` que importa `apps.integrations.providers.mercadopago` **cuando** corre el test de arquitectura **entonces** falla; **y** el mismo import dentro de `providers/mercadopago/` no falla.
- **AC-PLT-15** (RN-PLT-09) **Dado** un módulo sintético en `services/` que usa `Model.objects` **cuando** corre el test de arquitectura **entonces** falla.
- **AC-PLT-16** (RN-PLT-10) **Dado** un cambio de modelo sin migración **cuando** corre el paso 8 **entonces** falla por `makemigrations --check`.
- **AC-PLT-17** (RN-PLT-10) **Dado** una migración con `RunPython` sin `reverse_code` (o `RunSQL` sin `reverse_sql`) **cuando** corre el chequeo **entonces** falla; **y** una migración reversible pasa aplicar → revertir → reaplicar en BD descartable.
- **AC-PLT-18** (RN-PLT-10) **Dado** una migración llamada `NNNN_auto_<fecha>` o que mezcla `RunPython` con operaciones de esquema **cuando** corre el chequeo **entonces** falla.
- **AC-PLT-19** (RN-PLT-13) **Dado** un secreto de prueba con formato de token en el diff **cuando** corren pre-commit y el paso 3 de CI **entonces** ambos fallan; **y** un placeholder `<ver .env: MP_ACCESS_TOKEN>` no falla.
- **AC-PLT-20** (RN-PLT-11) **Dado** un PR con un error de lint **cuando** corre el pipeline **entonces** el paso 1 falla y el build (paso 9) no se ejecuta.
- **AC-PLT-21** (RN-PLT-11) **Dado** un error de tipos en backend o frontend **cuando** corre el paso 4 **entonces** falla (`mypy` sujeto a Q-033; `tsc --noEmit` siempre).
- **AC-PLT-22** (RN-PLT-11) **Dado** una cobertura por debajo del gate de Q-032 **cuando** corre el paso 7 **entonces** falla.
- **AC-PLT-23** (RN-PLT-15) **Dado** un cambio en la API sin regenerar `openapi.yaml`, o tipos del frontend desactualizados respecto de él **cuando** corre CI **entonces** falla mostrando el diff.
- **AC-PLT-24** (RN-PLT-12) **Dado** el repo en GitHub **cuando** corre el script de verificación de protección **entonces** confirma: PR obligatorio, checks requeridos = jobs del pipeline, squash-only, sin force-push ni borrado de `main`; **y** un PR con un check rojo figura como no mergeable.
- **AC-PLT-25** (RN-PLT-14, RNF-PLT-01) **Dado** el paso 9 **cuando** construye las imágenes **entonces** instalan desde lockfile congelado, quedan etiquetadas con el SHA del commit y el proceso principal no corre como root.
- **AC-PLT-26** (RN-PLT-14) **Dado** una dependencia fijada con una vulnerabilidad conocida de severidad bloqueante (Q-037) **cuando** corre la auditoría **entonces** falla.
- **AC-PLT-27** (RNF-PLT-05) **Dado** un `.sh` o `Dockerfile` con fin de línea CRLF **cuando** corre pre-commit **entonces** falla o lo normaliza a LF.
- **AC-PLT-28** (RN-PLT-16) **Dado** la ruta `(dashboard)` **cuando** se renderiza en test de componente **entonces** muestra barra superior con el lugar del selector empresa/sucursal y navegación a Inicio y Configuración; Inicio muestra `EmptyState` (nunca vacío), y un error de carga muestra un aviso con "Reintentar".
- **AC-PLT-29** (RN-PLT-16) **Dado** el build del frontend **cuando** se inspecciona el bundle del cliente **entonces** no contiene la URL interna del backend ni variables no `NEXT_PUBLIC_`.
- **AC-PLT-30** *(sujeto a Q-038)* **Dado** el throttle por defecto **cuando** se excede **entonces** responde 429 con `Retry-After`.
- **AC-PLT-31** *(sujeto a Q-047)* **Dado** un `FloatField` en un modelo o `float(` en `services/` **cuando** corre CI **entonces** falla.

## 14. Interfaz de usuario
Solo el **esqueleto** del shell de `07 §5`: layout `(dashboard)` con barra superior (lugar del selector
empresa/sucursal, deshabilitado y sin datos hasta 02), menú de usuario vacío (01), navegación a **Inicio** y
**Configuración**. Inicio: `EmptyState` con texto neutro. Configuración: secciones de `07 §5.3` deshabilitadas con
el módulo que las implementa. Estados: carga = `PageSkeleton`; vacío = `EmptyState`; error = aviso con "Reintentar"
(`07 §2`); sin permiso = no aplica hasta 01/02. Alcance exacto en Q-045.

## 15. Riesgos y supuestos
- Supuesto: el repo es privado en una cuenta personal de GitHub. Riesgo: la protección de ramas puede requerir plan pago (Q-042); sin ella C-15 no se verifica automáticamente.
- Riesgo: hot-reload lento o inexistente con bind mounts en Windows. Mitigación: polling en dev; documentarlo.
- Riesgo: el chequeo de migraciones da falsa confianza (una migración reversible puede perder datos al revertir). Mitigación: expand/contract (`08 §7`) en revisión.
- Riesgo: el pipeline se vuelve lento. Mitigación: fail-fast, caché de dependencias, pre-commit solo con lo rápido.
- Riesgo: si se corre `migrate` con el usuario por defecto de Django antes de 01, cambiar `AUTH_USER_MODEL` exige recrear la BD (Q-053). Supuesto: hasta 01 toda BD es descartable.

## 16. Preguntas abiertas
Detalle en `specs/00-platform/clarifications.md` §G. **Bloqueante para *Clarified*: Q-042.** Q-035 bloquea *Designed* (ADR-0005).
- Q-029 versiones fijadas · Q-030 gestor de dependencias y lockfile · Q-031 lint/format/test/hooks · Q-032 gate de cobertura · Q-033 type-check backend.
- Q-034 logger · Q-035 ADR-0005 OpenAPI · Q-036 versionado de URL y sobre de errores · Q-037 secretos y auditoría de dependencias · Q-038 rate limiting.
- Q-039 healthchecks y versión · Q-040 settings y validación · Q-041 `request_id` y log de acceso · **Q-042 protección de `main` y aprobación del reviewer**.
- Q-043 alcance de `check_file_size` · Q-044 base tenant-aware · Q-045 alcance del shell · Q-046 zona horaria/idioma · Q-047 chequeo C-02.
- Q-048 `.env.example` (lectura denegada, variables de spikes) · Q-049 registry de imágenes · Q-050 navegador solo vía BFF · Q-051 partes de 00 en zona roja · Q-052 feature flags · Q-053 modelo de usuario y primeras migraciones.

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-31 | Borrador inicial (reemplaza el placeholder) | `/spec 00-platform` |
