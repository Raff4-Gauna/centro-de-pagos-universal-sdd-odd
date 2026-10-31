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

## Convenciones
- Docs y specs en **español**; identificadores de código, commits y nombres de archivos en **inglés** (salvo las specs `.sdd.md`).
- IDs trazables: `RN-<MOD>-NN` regla · `RF-<MOD>-NN` requisito · `AC-<MOD>-NN` criterio · `Q-NNN` pregunta · `T-<MOD>-NN` tarea · `ADR-NNNN` decisión.
- Cada test que verifica un criterio lleva el ID en su nombre: `test_AC_CHG_03_duplicate_webhook_is_noop`.
- Commits: Conventional Commits (`feat(charges): …`, `fix(mp): …`). Ramas: `spec/NN-slug`, `task/T-CHG-03-slug`, `log/YYYY-MM-DD-slug`.
- Capas por app Django: `api/` (fino) → `services/` (casos de uso y transacciones) → `selectors/` (lecturas filtradas por tenant) → `models.py`. Lógica pura en `domain/`.

## Control de versiones (resumen; detalle en `context/08-control-de-versiones-ci-cd.md`)
- Commit atómico por AC/tarea en verde (tests + lint pasando), Conventional Commits, nunca código roto en `main`.
- PR por tarea, `reviewer` obligatorio en zona roja, merge por squash.
- Release = `git tag`; rollback = redeployar el tag anterior. Migraciones siempre reversibles (`C-17`).
- El agente commitea solo, sin esperar que se lo pidan, en el momento en que su propio checklist de "terminado"
  (tests+lint en verde) se cumple — ver la tabla de cadencia en `context/08-control-de-versiones-ci-cd.md §2.2`.

## Comandos de desarrollo
> Se completan al cerrar la spec `00-platform` (todavía no hay código). El pipeline de CI que van a correr esos
> comandos ya está definido en `context/08-control-de-versiones-ci-cd.md §3` (lint → tamaño de archivo → secretos
> → type-check → arquitectura → tests → cobertura → migraciones → build → deploy a staging automático / producción
> manual).
