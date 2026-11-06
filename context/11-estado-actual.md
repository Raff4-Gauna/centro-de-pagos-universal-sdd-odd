---
actualizado: 2026-11-05
ultimo_commit: a1eafb9
ultimo_pr: "#40"
modulo_activo: 00-platform
fase: cierre (Implemented pendiente)
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-05)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.9 | 30 ✅ · 10 ☐ · 1 🟡 (41) | ~90 % de lo planificado | Verificación **Con hallazgos** |
| 01-identity-access | Approved | sin `tasks.md` | 0 % | Depende de 00 |
| 02-tenancy-rbac | Approved | sin `tasks.md` | 0 % | Se cierra junto con 01 (Q-108) |
| 03-integrations-engine | Draft | — | 0 % | Falta cerrar el contrato del motor |
| 04-integration-management | Por redactar | — | 0 % | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | — | 0 % | Depende del spike S-001 |
| 06-charges | Draft | — | 0 % | Núcleo del dinero |
| 07–14 | Por redactar / Futuro | — | 0 % | Ver `specs/ROADMAP.md` |

- **00-platform:** 30 tareas mergeadas (PR #4–#40), 10 pendientes, `T-PLT-39` en revisión (`env.example`;
  **Q-048** cerrada: el dueño decidió renombrarlo). El pipeline tiene 9 de los 11 jobs: faltan `build` (T-PLT-37) y `smoke` (T-PLT-38).
- **Verificación:** `specs/00-platform/verification.md` existe y da **Con hallazgos**: 26 AC ✔, 3 ⚠
  (`AC-PLT-01`, `20`, `25`), 5 ✘ (`AC-PLT-17, 24, 29, 32, 33`); `05` y `06` cuentan con T-PLT-39, sin mergear. Ningún AC se marcó ✔ sin test.
- **01 y 02:** specs `Approved` pero **sin `tasks.md`**: no se puede implementar todavía.
- **04:** sin redactar; es el bloqueo de `06-charges`.
- **S-001 (Mercado Pago sandbox):** **sin ejecutar**. Es el mayor riesgo abierto del roadmap.
- **Skills:** antes de esta sesión no existían; ahora están `sdd-verification` y `reviewer-verdict`.
- **Agente de estado:** `project-steward` (nuevo), comandos `/reconcile` y `/handoff`.

## 2. Qué está terminado y NO se debe rehacer

- Tareas mergeadas de 00: `T-PLT-01..04`, `08..23`, `25..28`, `30..35` (detalle y evidencia en
  `specs/00-platform/tasks.md`).
- No reabrir una tarea `✅` sin evidencia nueva (test que falla, bug reproducible o cambio de spec aprobado).
- No re-especificar 00, 01 ni 02: están `Approved`. Un cambio de comportamiento va por “Historial de cambios”.
- No reescribir los documentos de proceso que ya existen (`context/08`, `ADR-0009`, `ADR-0010`); se extienden.

## 3. Qué sigue, en orden

1. **Cerrar T-PLT-39** (`env.example`, Q-048 decidida): revisión y merge. Después, acciones del dueño: mover las
   claves de spikes de su `.env` a `spikes/.env` y correr la verificación manual de AC-PLT-01.
2. **Cerrar el camino crítico de 00** en este orden:
   - `T-PLT-05, 06, 07` → AC-PLT-33 y AC-PLT-32 (checks de workflows y zona roja).
   - `T-PLT-24` → AC-PLT-17 (reversibilidad de migraciones).
   - `T-PLT-36` → AC-PLT-29 (imagen del frontend + Compose).
   - `T-PLT-37, 38` → AC-PLT-25 completo y AC-PLT-01 (build + smoke).
   - `T-PLT-40` → AC-PLT-24 (ruleset).
   - `T-PLT-41` → comandos de desarrollo (ya documentados en `AGENTS.md`; falta el cierre formal).
3. **Repetir la verificación** de 00 y marcar las filas `🧪`. Solo el dueño puede pasar la spec a `Verified`.
4. **Crear `tasks.md` de 01 y 02** (task-planner) y empezar identidad/tenencia.
5. **Redactar la spec 04** (bloquea a 06).
6. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
7. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
   `context/12-solid-y-diseno.md` y los agentes existentes.

## 4. Cómo retomar en 5 minutos

1. Leer `AGENTS.md`, `context/01-constitution.md` y `.agents/workflows/sdd-odd.md`.
2. Correr `python scripts/check_spec_state.py` (sin `--write`): si hay drift, correr `/reconcile 00-platform`.
3. Leer este archivo.
4. Tomar la primera acción de §3 que no esté completa.
5. Anunciar: “Retomo en: <acción>. No rehago: <tareas mergeadas>.”
6. Al terminar, correr `/handoff`.

## 5. Reglas de sesión

- No empezar de cero ni reimplementar lo mergeado.
- Un commit atómico por cambio, Conventional Commits.
- Actualizar `tasks.md` en el mismo PR que cambia el estado.
- Si falta una regla: `Q-xxx` y parar.
- No marcar `Verified` ni `Aprobada` sin OK del dueño.
- No tocar código de producción en una sesión de reconciliación.
- Actualizar este archivo antes de cerrar (`/handoff`).

## 6. Pie de la última sesión

- **Hecho:** reconciliación de 00 (30 ✅), `verification.md` (24 ✔ / 4 ⚠ / 6 ✘), `project-steward`,
  `/reconcile`, `/handoff`, skills `sdd-verification` y `reviewer-verdict`, `check_spec_state.py` + baseline,
  `ADR-0011` y `context/12-solid-y-diseno.md`.
- **Commits de la sesión:** `6273ac4` (tablero + verificación), `8ffbda0` (chequeo de drift), `a1eafb9`
  (agentes, skills y SOLID).
- **Pendiente / dudas:** Q-028 (SPEC-12), Q-059 (versiones), S-001 sin ejecutar.
- **Siguiente rol sugerido:** `backend-dev` en T-PLT-05 + `reviewer`.
