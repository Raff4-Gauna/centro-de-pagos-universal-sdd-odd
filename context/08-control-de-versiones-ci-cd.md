# Control de versiones, CI/CD, testing, logs y rollback

> Agregado 2026-10-31 a pedido explícito del usuario: "buenas prácticas... evitando cualquier tipo de accesos no
> autorizados... desarrollo por instancias, con tests automáticos, rollback, logs, etc.". Este documento es la
> referencia operativa de `C-14` a `C-17` (`context/01-constitution.md`) y de la "Regla de oro" de `AGENTS.md`.
> No reemplaza el flujo SDD/ODD (`.agents/workflows/sdd-odd.md`): lo complementa en la parte de "cómo queda el
> código en el repo", no en "qué se construye".

## 1. Tamaño y modularidad de archivo (C-14)

**Límite duro: ~400 líneas por archivo de código** (`.py`, `.ts`, `.tsx`, `.jsx`; no aplica a fixtures JSON,
migraciones autogeneradas ni `*.md`). No es un número mágico: es la señal de que un archivo está mezclando más de
una responsabilidad. Antes de llegar al límite, dividir por capa:

- **Backend (Django app)**: `api/` (serializers + views finos, sin lógica) → `services/` (casos de uso,
  transacciones, un archivo por caso de uso si crece) → `selectors/` (lecturas filtradas por tenant) →
  `domain/` (lógica pura, sin Django) → `models.py` (si crece, `models/` con un archivo por entidad). Un
  adaptador de proveedor se divide en `client.py` (HTTP), `mapper.py` (DTO ↔ formato del proveedor),
  `webhook.py` (verificación/parseo), `errors.py` — nunca un `adapter.py` único con todo.
- **Frontend (Next.js)**: una pantalla grande se parte en `page.tsx` (orquesta) + componentes en
  `modules/<dominio>/components/` + hooks propios en `modules/<dominio>/hooks/`. Un formulario largo se separa en
  sub-secciones, cada una su propio componente con su propio `zod` schema parcial.
- **Tests**: no cuentan para el límite de producción, pero igual se organizan por caso (`test_<caso>.py`), no un
  archivo gigante de tests por módulo.

Esto no cambia el límite de **~300 líneas de diff por tarea** que ya usa `task-planner` (`.claude/agents/task-planner.md`):
son dos métricas distintas — una mide cuánto cambia una tarea, la otra cuánto mide un archivo en total.

**Verificación automática**: `backend/scripts/check_file_size.py` (o equivalente) recorre los archivos trackeados
por git, excluye migraciones y fixtures, y falla si alguno supera el límite. Corre en pre-commit y en CI (sección 3).

## 2. Control de versiones (C-15)

### 2.1 Modelo de ramas (ya fijado en `AGENTS.md`)
- `spec/NN-slug` — trabajo sobre una spec (pasos 1–4 de SDD).
- `task/T-MOD-NN-slug` — una tarea de implementación.
- `log/YYYY-MM-DD-slug` — Carril O.
- `main` siempre deployable: nunca un commit roto, nunca código sin su spec en estado `Approved` (zona roja) o
  sin worklog previo (Carril O).

### 2.2 Cadencia de commits (decisión explícita, para que el agente no la improvise)
La regla no es "un commit por archivo" ni "un commit al final del día": es **un commit por unidad de trabajo
verificable y en verde**.

| Momento | ¿Se commitea? | Mensaje |
|---|---|---|
| Se escribió el test de un AC y todavía falla (TDD, rojo) | No se commitea solo; queda como parte del próximo commit en verde | — |
| El test de un AC pasa y el código que lo satisface está completo, con lint/format en verde | **Sí**, commit atómico | `feat(charges): crear cobro con idempotencia (AC-CHG-01)` |
| Una tarea `T-xx` completa su DoD (sección 6 de `sdd-odd.md`) | Sí, si no se commiteó ya por AC; además se actualiza `tasks.md` en el mismo commit | `feat(mp): adaptador crea orden QR (T-MP-02)` |
| Fix de un bug con test de regresión | Sí, commit propio, nunca mezclado con una feature | `fix(webhooks): dedupe por hash de payload` |
| Cambio de spec/documentación sin código | Sí, commit propio, prefijo `docs(...)` | `docs(charges): agrega RN-CHG-19 tras Q-030` |
| Varias tareas a medio terminar, nada en verde | **No se commitea** nada a una rama compartida; se puede usar `git commit --amend` o commits locales en la rama de la tarea hasta que algo quede verde, y recién ahí se deja el historial limpio (`git rebase -i` en la rama propia, nunca en `main`) |

El agente que implementa decide el commit en el momento en que su propio paso 5 (`.claude/commands/implement.md`)
dice "corré tests y linters antes de declarar terminado": ese es el gatillo. No se espera a que el humano lo pida.
Reglas duras:
- Nunca se commitea con tests en rojo o lint en rojo.
- Nunca se commitea un secreto (`C-06`); antes de cada commit se corre un escaneo de secretos (sección 3).
- Un PR de tarea se abre contra `main` (o la rama de integración vigente) al terminar la tarea; `reviewer` revisa
  si toca zona roja; se mergea con **squash** para que el historial de `main` sea una línea por tarea/AC.
- Releases (cierre de un hito H1…H5, o un deploy a producción) llevan `git tag vX.Y.Z` — es lo que permite volver
  atrás rápido (`C-17`).

### 2.3 Qué NO hacer
- No usar `git add -A`/`git commit -am` a ciegas: revisar qué se stagea (evita subir `.env`, dumps de BD, un
  archivo de credenciales de prueba fuera de `context/`).
- No forzar push a `main`.
- No reescribir historial ya compartido/mergeado.

## 3. CI/CD (pipeline mínimo desde el primer commit de código, módulo 00-platform)

Orden (falla rápido primero):
1. **Lint + format** (`ruff`/`black` backend, `eslint`/`prettier` frontend).
2. **Tamaño de archivo** (`check_file_size.py`, sección 1).
3. **Escaneo de secretos** (`gitleaks` o equivalente) sobre el diff — bloqueante, no solo advertencia.
4. **Type-check** (`mypy` backend si se adopta, `tsc --noEmit` frontend).
5. **Test de arquitectura** (`C-01`, `C-09`): nada fuera de `providers/` importa de `providers/*`; no hay
   `Model.objects` crudo en `services/`.
6. **Tests unitarios + de contrato** (pytest / vitest-jest), con el nombre `test_AC_<MOD>_NN_...` donde aplica.
7. **Cobertura**: gate general del repo (se fija el número en la spec `00-platform`) y `≥ 90 %` específico para
   `integrations-engine` (`RNF-ENG-03`).
8. **Chequeo de migraciones**: `makemigrations --check --dry-run` (nadie olvida generar una migración) +
   aplicar y revertir (`migrate app zero`/paso anterior) en una base descartable, para garantizar `C-17`.
9. **Build** (imagen Docker backend/frontend) — solo si todo lo anterior pasó.
10. **Deploy** a `staging` automático en cada merge a `main`; a producción **manual** (botón/aprobación), nunca
    automático mientras el proyecto sea operado por pocas organizaciones (ver `Q-020`).

### 3.1 Pre-commit (local, espejo rápido de CI)
`lint + format + tamaño de archivo + escaneo de secretos` corren en pre-commit (hook de git) para que el agente
o la persona vean el problema antes de empujar, no después. El resto (tests completos, cobertura, migraciones)
corre en CI porque es más lento.

## 4. Pirámide de pruebas (detalle operativo de `C-11`)
- **Unitarias / dominio** (`domain/`): rápidas, sin BD ni red, la mayoría de los casos límite de cada `RN-xx`.
- **Contrato de adaptador** (`integrations/providers/<x>/`): contra fixtures grabadas en sandbox (sección 5),
  sin red en CI; marcadas aparte las que sí pegan a la red real (no corren en CI, solo manual/nightly).
- **Integración** (servicio + BD real de test): transiciones de estado, idempotencia, aislamiento por
  organización (`C-01`) — estas son las que más valen en zona roja.
- **E2E humo**: 1–2 flujos de punta a punta (login → integración → cobro → webhook simulado → `paid`) que corren
  en CI contra `FakeAdapter`, no contra proveedores reales.
- **Manual**: la validación funcional del paso 6 de SDD (`qa-verifier` + humano) contra sandbox real antes de
  marcar una spec `Verified`.

## 5. Scripts y tablas: versionado y segmentación

- **Esquema de BD**: 100 % migraciones de Django (`manage.py makemigrations`), nunca SQL suelto aplicado a mano.
  Una migración de **esquema** (estructura) y una de **datos** (backfill) van en archivos separados aunque sean
  del mismo cambio, para poder revertir una sin la otra.
- **Nombres de migración**: el autogenerado de Django + sufijo descriptivo (`0007_add_branch_timezone`), nunca
  "migración final" ni similares.
- **Seeds / datos de referencia** (ej. catálogo de `provider_code`, categorías MCC): `management/commands/` de
  la app correspondiente, versionados con el código, idempotentes (correrlos dos veces no duplica).
- **Scripts puntuales** (una corrida manual, ej. backfill único): `infra/scripts/`, numerados
  (`001-slug.py`, `002-slug.py`), cada uno con un docstring de qué hace, cuándo y quién lo corrió, y una fila en
  `infra/scripts/README.md` (bitácora). Nunca se reutiliza un script puntual como si fuera un comando permanente:
  si hace falta de nuevo, se promueve a `management/commands/`.
- **Fixtures de proveedores** (sandbox, sanitizadas): `backend/apps/integrations/providers/<x>/fixtures/`,
  versionadas junto al adaptador; se regeneran cuando el proveedor cambia su API (se nota en el changelog del
  adaptador, sección 18 de cada spec).

## 6. Logs (detalle operativo de `C-16`)
- Logger estructurado único (`structlog` o `logging` + formateador JSON) configurado en `00-platform`.
- Campos obligatorios: `timestamp`, `level`, `request_id` (o `task_id` para Celery), `component`
  (`charges.service`, `integrations.providers.mercadopago`…), `organization_id` cuando aplica, `message`.
  **Nunca** credenciales, tokens, ni cuerpo crudo de request/response de proveedor (`C-06`, `RNF-ENG-02`).
- El log de auditoría (`C-08`, módulo `10-audit`) es una **tabla**, no un archivo de log: queda append-only en
  BD porque tiene que sobrevivir y ser consultable, no rotar como un log operativo.
- En desarrollo: logs a `stdout` (Docker Compose los junta). En producción: `stdout` también, pero recolectados
  por el proveedor de hosting (definir con `Q-020`); nada de escribir a archivo local dentro del contenedor.

## 7. Rollback (detalle operativo de `C-17`)
- Cada deploy a producción corresponde a un `git tag`. Volver atrás = redeployar el tag anterior (la imagen
  Docker de esa build, no "revertir código y volver a buildear a las apuradas").
- Migraciones reversibles: todo `migrations.py` que agregue una columna/tabla debe poder bajarse; una migración
  que no se pueda revertir limpio (ej. borra una columna con datos) se separa en dos pasos a lo largo de dos
  releases (dejar de usar la columna primero, borrarla en un release posterior) — patrón estándar de
  "expand/contract".
- Antes de migrar producción: backup de BD (automatizado, fuera del alcance de este kit pero obligatorio antes
  de abrir a comercios reales — ver `Q-020`/`Q-021`).
- Zonas rojas nuevas (ej. primera vez que se activa un proveedor nuevo, cambio en la máquina de estados) se
  despliegan detrás de un *feature flag* simple (variable de entorno/config por organización) para poder
  apagarlas sin revertir el deploy entero.
- Los adaptadores son idempotentes por diseño (`RN-ENG-06`, `RN-CHG-05/09/10`): un rollback o un redeploy a mitad
  de una operación no duplica cobros ni pierde eventos, porque el estado se reconcilia por idempotencia y por el
  poller de seguridad.

## 8. Seguridad y accesos no autorizados (resumen operativo; el detalle normativo está en `C-01`/`C-06`/`C-13`)
- Autenticación: Google OAuth + JWT (cookie `httpOnly`, `ADR-0004`) para personas; API keys con scope por
  organización para sistemas (`ADR-0008`, módulo `11`). Nunca compartir un mismo secreto entre dos propósitos.
  Sin usuario/contraseña propios en el MVP (`Q-012`).
- Autorización: todo se filtra por `organization_id` vía managers/selectors tenant-aware (`C-01`); matriz de
  roles por acción vive en la sección 4 de cada spec (ej. `specs/06-charges/spec.sdd.md §4`).
  **Cambio de empresa/sucursal** (pedido del usuario, ver `context/07-frontend-ui-guidelines.md §5`) solo
  permite moverse entre organizaciones de las que el usuario tiene `Membership`: el selector de la UI nunca
  es la fuente de verdad, el backend vuelve a validar el `organization_id` en cada request.
- Credenciales de proveedores: cifradas en reposo (`C-06`, `ADR-0003`), nunca en logs/errores/fixtures.
- Dependencias: versiones fijadas, sin agregar paquetes en zonas rojas sin ADR (`C-13`); `npm audit`/`pip-audit`
  (o equivalente) como parte del pipeline antes de producción.
- Rate limiting y protección básica de API (login, webhooks) se define al redactar `00-platform`/`01-identity-access`;
  se deja anotado acá para no perderlo de vista.

## 9. Historial de cambios
| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-10-31 | Documento inicial | Pedido explícito del usuario: buenas prácticas de archivo, versionado, CI, tests, rollback y logs antes de escribir la primera línea de código |
