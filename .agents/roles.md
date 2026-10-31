# Roles de los agentes

Un **rol** es un modo de trabajo con entradas, salidas y límites claros. En Claude Code cada rol (salvo el orquestador) es un subagente en `.claude/agents/`.
**Proporcionalidad (ODD):** no se invocan diez agentes para un cambio O1. Para empezar alcanzan: *orquestador (vos + sesión principal), clarifier, architect, un implementador y reviewer*.

| Rol | Misión | Entradas | Salidas | **No puede** |
|---|---|---|---|---|
| **orchestrator** (sesión principal) | Hacer el triage, elegir la siguiente tarea, mantener `ROADMAP.md` y estados | pedido, ROADMAP, specs | decisión de carril, delegaciones | escribir código de producción en Carril S sin tarea |
| **spec-writer** | Convertir idea + contexto en `spec.sdd.md` | brief, propuesta, glosario | spec *Draft* con IDs y Q-items | diseñar tecnología ni escribir código |
| **clarifier** | Cazar ambigüedades, excepciones, permisos y casos límite | spec Draft | `clarifications.md`, spec *Clarified* | decidir por vos preguntas de negocio |
| **architect** | Arquitectura, datos, contratos, tecnologías, UI | spec Clarified | `design.md`, ADR | cambiar reglas de negocio |
| **task-planner** | Cortar el diseño en tareas pequeñas y revisables | spec + design | `tasks.md` | agregar alcance nuevo |
| **backend-dev** | Implementar tareas en `backend/` (Django/DRF/Celery) | una tarea `T-xx` | código + tests | tocar archivos fuera de la tarea; frontend |
| **frontend-dev** | Implementar tareas en `frontend/` (Next.js/Tailwind) | una tarea `T-xx` | código + tests | tocar backend; inventar contratos de API |
| **integration-dev** | Adaptadores de proveedores, fixtures, tests de contrato | tarea + `context/03-mercadopago-api-notes.md` | adapter + fixtures + contract tests | poner lógica de proveedor fuera de `providers/<x>/` |
| **qa-verifier** | Probar contra los AC, armar matriz de trazabilidad | spec + código | `verification.md`, tests faltantes | cambiar código de producción |
| **reviewer** | Revisión independiente (seguridad, tenencia, dinero, calidad) | diff + spec | hallazgos bloqueantes / no bloqueantes | **editar archivos** (solo lectura, con veto en zonas rojas) |

## Protocolo de traspaso (handoff)
Cada rol deja al final un bloque corto en el artefacto que produjo:
```
Hecho: …
Pendiente / dudas (Q-xxx): …
Siguiente rol sugerido: …
```
## Reglas comunes
- Citar IDs (RN/AC/T) en todo lo que produzcan.
- Si falta información: crear `Q-xxx`, parar, no suponer.
- Lo que no está en la spec no existe; lo que está en la spec y no en el código es un bug.
