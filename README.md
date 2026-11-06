# Centro de Pagos Universal

Payment Hub multi-tenant: conectá tus cuentas de Mercado Pago (y luego Payway y Clover) y operá cobros, conciliación y reportes desde un solo lugar.

**Estado (2026-11-06):** `00-platform` en cierre — 35 de 41 tareas mergeadas (`✅`) y 6 pendientes (`☐`). La
verificación del módulo está **Con hallazgos** (28 AC cubiertos, 5 parciales, 1 sin test). `01-identity-access` y `02-tenancy-rbac` están `Approved` pero todavía sin `tasks.md`; la spec `04` y el
spike S-001 siguen pendientes. No hay funcionalidad de negocio implementada.

| Carpeta | Para qué |
|---|---|
| `propuesta/` | Documentos originales (solo lectura). |
| `context/` | Contexto durable: brief, constitución, glosario, notas de API, decisiones (ADR), worklog (ODD) y estado actual. |
| `specs/` | Artefactos SDD por módulo + plantillas + roadmap. **Fuente de verdad.** |
| `.agents/` | Proceso y roles de los agentes (agnóstico de herramienta). |
| `.claude/` | Ejecución en Claude Code: subagentes, comandos, skills, permisos. |
| `backend/` · `frontend/` · `infra/` | Código de plataforma ya implementado (Django/DRF, Next.js, Docker). |

## Por dónde empezar

1. `context/11-estado-actual.md` — dónde estamos y qué sigue.
2. `AGENTS.md` — reglas operativas, estados, reviewer, comandos y cierre de sesión.
3. `specs/ROADMAP.md` y `specs/00-platform/verification.md`.
4. `python scripts/check_spec_state.py` — detecta drift entre documentos y git.
5. `specs/00-platform/clarifications.md` — preguntas abiertas.

Para una sesión nueva: `/reconcile 00-platform` si hay drift; al terminar, `/handoff`.
