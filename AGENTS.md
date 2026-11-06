# AGENTS.md — Centro de Pagos Universal

> Manual operativo para cualquier agente (Claude Code, Codex, Cursor…) y para humanos.
> Jerarquía si hay conflicto: **Constitución (`context/01-constitution.md`) > spec Aprobada > este archivo > código existente.**

## Qué es esto
Hub de pagos multi-tenant: una organización conecta sus cuentas de proveedores (primero Mercado Pago) y cobra, concilia y reporta desde una sola interfaz.
Stack: Django + DRF + PostgreSQL + Celery/Redis (backend) · Next.js + Tailwind (frontend) · Docker.

## Leer antes de tocar nada
1. `context/00-project-brief.md` — qué y por qué.
2. `context/01-constitution.md` — reglas no negociables (C-xx).
3. `context/02-glossary.md` — vocabulario (Branch ≠ Store, Charge ≠ Payment…).
4. `.agents/workflows/sdd-odd.md` — cómo se trabaja (triage, carriles, gates).
5. La spec del módulo en `specs/NN-modulo/` (y su `tasks.md` si existe).
6. Si la tarea toca pantallas: `context/07-frontend-ui-guidelines.md` (Material UI + Tailwind, esquemas de carga,
   arquitectura cliente/servidor, shell de navegación e Inicio/Configuración §5). Si toca Payway o Clover:
   `context/05-payway-api-notes.md` / `context/06-clover-api-notes.md` / `context/10-clover-cuenta-sandbox-real.md`
   (y recordar que ninguno de los dos pasa de "Futuro" sin el spike S-002).
7. Si la tarea toca código (no solo specs): `context/08-control-de-versiones-ci-cd.md` — tamaño de archivo,
   cadencia de commits, pipeline de CI, tests, logs y rollback. No es opcional ni "para después".
8. Antes de elegir la próxima tarea: `context/11-estado-actual.md` — tablero vivo (dónde estamos y qué sigue).
9. Si vas a diseñar o revisar código: `context/12-solid-y-diseno.md` y `ADR-0011` — SOLID por fronteras.

## Regla de oro
No se escribe código de producción sin:
- **Carril S:** una tarea (`tasks.md`) que cite criterios de aceptación (`AC-…`) de una spec en estado `Approved`; **o**
- **Carril O:** una entrada de worklog creada ANTES de empezar (intención + cómo se verificará).

## Triage (siempre lo primero)
Si el cambio toca una **zona roja** → Carril S. Si es nuevo módulo/regla de negocio/contrato → Carril S. Si hay ambigüedad → Carril S.
Si no → Carril O. Detalle en `.agents/workflows/sdd-odd.md`.

**Zonas rojas:** dinero (montos, comisiones, devoluciones) · estados de cobro · webhooks e idempotencia · credenciales/cifrado · auth, roles y permisos · aislamiento por `organization_id` · migraciones de BD · contratos públicos (API/eventos) · adaptadores de proveedores.

## Prohibido (sin excepción)
- `float` para dinero. Siempre `Decimal` / `DecimalField(max_digits=12, decimal_places=2)`.
- Consultas de negocio sin filtro por organización (usar los managers/selectors tenant-aware).
- Marcar un cobro como pagado por pedido del frontend, redirect o navegador. Solo confirmación servidor-a-servidor.
- Secretos en código, logs, mensajes de error, respuestas de API o commits.
- Código específico de un proveedor fuera de `backend/apps/integrations/providers/<proveedor>/`.
- Inventar reglas de negocio. Si falta una regla: agregar un `Q-xxx` en `clarifications.md`, **parar y preguntar**.
- Salirse del scope de la tarea (archivos no listados). Si hace falta → reportar "scope drift" y volver al planner.
- Modificar una spec `Approved` sin entrada en su "Historial de cambios".
- Un archivo de código (`.py`/`.ts`/`.tsx`/`.jsx`) de más de **~400 líneas** (`C-14`). Se divide por capa/
  responsabilidad en vez de extenderlo; ver `context/08-control-de-versiones-ci-cd.md §1`.
- Dejar un commit o un merge a `main` con tests o lint en rojo (`C-15`).
- Inventar una abstracción (interfaz, fábrica, capa) sin una segunda implementación o un caso real que la justifique.
  SOLID es un criterio de fronteras, no una licencia para agregar código (`ADR-0011`).

## Convenciones
- Docs y specs en **español**; identificadores de código, commits y nombres de archivos en **inglés** (salvo las specs `.sdd.md`).
- IDs trazables: `RN-<MOD>-NN` regla · `RF-<MOD>-NN` requisito · `AC-<MOD>-NN` criterio · `Q-NNN` pregunta · `T-<MOD>-NN` tarea · `ADR-NNNN` decisión.
- Cada test que verifica un criterio lleva el ID en su nombre: `test_AC_CHG_03_duplicate_webhook_is_noop`.
- Commits: Conventional Commits (`feat(charges): …`, `fix(mp): …`). Ramas: `spec/NN-slug`, `task/T-CHG-03-slug`, `log/YYYY-MM-DD-slug`.
- Capas por app Django: `api/` (fino) → `services/` (casos de uso y transacciones) → `selectors/` (lecturas filtradas por tenant) → `models.py`. Lógica pura en `domain/`.
- **Diseño (SOLID):** un caso de uso por servicio; proveedor nuevo = carpeta nueva + registro; todo adaptador
  cumple `BaseAdapter`; protocolos por capacidad; el núcleo depende de puertos, los SDKs viven solo en
  `providers/<x>/`. Detalle y checklist en `context/12-solid-y-diseno.md`.

## Estado del proyecto y tablero (obligatorio)

La fuente de verdad del estado es **git + tests ejecutados**, no la memoria de una sesión.

| Símbolo | Significado | Evidencia exigida |
|---|---|---|
| ☐ | Pendiente | — |
| 🔄 | En curso | rama `task/…` |
| 🟡 | En revisión | PR abierto |
| ✅ | Mergeada | PR + SHA de merge |
| 🧪 | Verificada | fila `✔` en `verification.md` |
| ⛔ | Bloqueada | `Q-xxx` que la bloquea |

- El tablero vivo es `context/11-estado-actual.md`. El detalle por tarea está en `specs/NN-modulo/tasks.md`.
- `specs/NN-modulo/verification.md` es la matriz AC→test del módulo.
- **Drift:** si un commit con `T-XX-NN` no actualizó su fila, o una tarea `✅` no tiene PR/SHA, es un defecto de
  proceso. Lo detecta `python scripts/check_spec_state.py`.
- El rol `project-steward` audita y corrige documentos; **no escribe código**. Se invoca con `/reconcile NN-modulo`.
- Al cerrar una sesión se corre `/handoff`: actualiza el tablero, corre el chequeo y deja el bloque
  Hecho / Pendiente / Siguiente.

## Reviewer: aprobación y merge

La aprobación **no** es un "approve" nativo de GitHub: el repo trabaja con **0 aprobaciones nativas** por diseño.

Una revisión se considera aprobada cuando:
1. El subagente `reviewer` (solo lectura, sin Write/Edit) revisó el diff completo del PR.
2. Dejó un **comentario en el PR** con el veredicto y el **SHA del último commit revisado**.
3. Claude aplicó el label **`zona-roja`** (obligatorio cuando la tarea es de zona roja).
4. El check requerido del pipeline está en verde sobre **ese mismo SHA**.

Reglas:
- Un **push nuevo invalida el veredicto**: hay que volver a revisar y citar el SHA nuevo.
- `reviewer` no edita archivos ni mergea. Quien escribe no revisa.
- Formato del veredicto (`design.md §3.7.3`, también en `.claude/skills/reviewer-verdict/SKILL.md`): tres líneas
  propias, fuera de bloques de código: `<!-- reviewer-verdict -->`, `Veredicto del reviewer: APROBADO | RECHAZADO`
  (un solo estado) y `SHA: <40 hex del último commit>`, seguidas de la tabla de hallazgos bloqueantes/no bloqueantes
  con `archivo:línea` y regla (`C-xx`/`RN-xx`).
- **Merge (Q-057):** **Claude se encarga del CI y de GitHub**: publica las ramas, abre los PR, aplica el label,
  corrige lo que falle en el pipeline y mergea (decisión del dueño, 2026-10-31, ampliada el 2026-11-02 y el
  2026-11-06). Se mergea solo con certeza total: pipeline completo en verde en el último commit, veredicto sin
  bloqueantes, DoD completo y squash (`--match-head-commit <sha>`). Hasta T-PLT-40, "pipeline completo" son todos los
  checks de todos los workflows que corren en ese commit (lectura propuesta por Claude, pendiente de que el dueño la
  corrija o confirme). Ante cualquier duda (`design.md §3.7.4`: check inestable, re-run manual, scope drift, `Q-xxx`
  abierta, advertencias nuevas, entre otras) el PR queda para el dueño.
- **Solo el dueño** cambia ruleset, visibilidad y ajustes del repo; esos PR los mergea él.
- El veredicto se guarda como comentario, no como revisión nativa. Eso es intencional y no se "corrige" con un
  approve de la UI.

## Control de versiones (resumen; detalle en `context/08-control-de-versiones-ci-cd.md`)
- Commit atómico por AC/tarea en verde (tests + lint pasando), Conventional Commits, nunca código roto en `main`.
- PR por tarea, `reviewer` obligatorio en zona roja, merge por squash.
- Release = `git tag`; rollback = redeployar el tag anterior. Migraciones siempre reversibles (`C-17`).
- El agente commitea solo, sin esperar que se lo pidan, en el momento en que su propio checklist de "terminado"
  (tests+lint en verde) se cumple — ver la tabla de cadencia en `context/08-control-de-versiones-ci-cd.md §2.2`.
- El commit que mergea una tarea actualiza `tasks.md` (estado + evidencia) y, si corresponde, `verification.md`.

## Comandos de desarrollo

Desde la raíz del repo (PowerShell o bash). `DC` = `docker compose -f infra/docker-compose.yml --env-file .env`.

| Para | Comando |
|---|---|
| Primera vez | `copy env.example .env` · `pre-commit install` · `corepack enable` · `pnpm --dir frontend install` |
| Levantar todo | `DC up -d --build --wait` |
| Logs / bajar | `DC logs -f backend worker` · `DC down` |
| Recrear la BD | `DC down -v` y volver a levantar (BD descartable hasta SPEC-01, Q-053) |
| Tests backend | `DC exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend pytest` |
| Tests frontend | `pnpm --dir frontend test` · `DC exec frontend pnpm test` |
| Tests de scripts | `pytest -c scripts/pytest.ini scripts/tests` |
| Lint rápido | `pre-commit run --all-files` · `ruff check .` · `ruff format --check .` |
| Tipos | `DC exec backend mypy . ../scripts` · `pnpm --dir frontend typecheck` |
| Regenerar contrato | `DC exec backend python manage.py export_openapi` → `pnpm --dir frontend openapi:types` |
| Migraciones | `DC exec backend sh -c "python manage.py makemigrations --check --dry-run && python manage.py lint_migrations"` · ida y vuelta **solo contra una BD descartable, nunca la de desarrollo** (revierte a `zero` y borra tablas y datos): `DC exec -e DATABASE_URL=postgres://<usuario>:<clave>@db:5432/hub_roundtrip backend python manage.py check_migrations_roundtrip --allow-data-loss` (BD `hub_roundtrip` creada antes y borrada después) o el job `migrations` de CI |
| Reiniciar worker/beat | `DC restart worker beat` |
| Estado del proyecto | `python scripts/check_spec_state.py` (agregar `--write` para regenerar la conciliación) |
| Verificar protección (dueño) | `python scripts/verify_repo_protection.py` con `GH_TOKEN` de admin (pendiente, T-PLT-40) |

Notas:
- Los comandos de `build` y `smoke` del pipeline todavía no existen (T-PLT-37/38): no se inventan.
- En Windows, si `5432` está ocupado, usar un override fuera del repo (`infra/README.md`).

## Cierre de sesión (obligatorio si la sesión termina acá)

1. Actualizar `context/11-estado-actual.md` (fecha, último commit, módulo, próxima acción).
2. Actualizar `tasks.md` y `verification.md` si cambió algo.
3. Correr `python scripts/check_spec_state.py` y mostrar el resultado.
4. Dejar el bloque: **Hecho / Pendiente (Q-xxx) / Siguiente rol sugerido**.
5. Commit `docs(platform): session handoff <fecha>` si hubo cambios de documentos.

El comando `/handoff` hace estos pasos. No se toca código de producción en el cierre.
