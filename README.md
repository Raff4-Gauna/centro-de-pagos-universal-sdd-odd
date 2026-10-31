# Centro de Pagos Universal

Payment Hub multi-tenant: conectá tus cuentas de Mercado Pago (y luego Payway y Clover) y operá cobros, conciliación y reportes desde un solo lugar.

Estado: **planificación** (no hay código todavía).

| Carpeta | Para qué |
|---|---|
| `propuesta/` | Documentos originales (solo lectura). |
| `context/` | Contexto durable: brief, constitución, glosario, notas de API, decisiones (ADR), worklog (ODD). |
| `specs/` | Artefactos SDD por módulo + plantillas + roadmap. **Fuente de verdad.** |
| `.agents/` | Proceso y roles de los agentes (agnóstico de herramienta). |
| `.claude/` | Ejecución en Claude Code: subagentes, comandos, permisos. |
| `backend/` · `frontend/` · `infra/` | Código (recién después de specs aprobadas). |

Empezá por `specs/ROADMAP.md` y `specs/00-platform/clarifications.md`.
