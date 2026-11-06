---
actualizado: 2026-11-06
ultimo_commit: 1cc858e
ultimo_pr: "#47"
modulo_activo: 00-platform
fase: cierre (Implemented pendiente)
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-06)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.12 | 35 ✅ · 6 ☐ (41) | 35 de 41 tareas | Verificación **Con hallazgos** |
| 01-identity-access | Approved | sin `tasks.md` | 0 % | Depende de 00 |
| 02-tenancy-rbac | Approved | sin `tasks.md` | 0 % | Se cierra junto con 01 (Q-108) |
| 03-integrations-engine | Draft | — | 0 % | Falta cerrar el contrato del motor |
| 04-integration-management | Por redactar | — | 0 % | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | — | 0 % | Depende del spike S-001 |
| 06-charges | Draft | — | 0 % | Núcleo del dinero |
| 07–14 | Por redactar / Futuro | — | 0 % | Ver `specs/ROADMAP.md` |

- **00-platform:** 35 tareas mergeadas (PR #4–#47) y 6 pendientes: `T-PLT-07, 29, 37, 38, 40, 41`. `T-PLT-07` tiene
  el PR #48 abierto. El pipeline tiene 9 de los 11 checks, en verde sobre `1cc858e`: faltan `build` (T-PLT-37, con el
  smoke de T-PLT-38 como paso) y `zona-roja` (T-PLT-07). `env.example` ya está en `main` (T-PLT-39, Q-048 cerrada).
- **Verificación:** `specs/00-platform/verification.md` da **Con hallazgos**: 28 AC ✔, 5 ⚠ (`AC-PLT-01`, `20`, `25`,
  `29`, `32`), 1 ✘ (`AC-PLT-24`). Ningún AC se marcó ✔ sin test.
- **Dependabot:** 7 PR abiertos desde el 2026-11-03 (#25–#31), sin triaje: un grupo de parches (#25) y seis saltos de
  versión mayor (Django 6.1, redis 8, Tailwind 4, mypy 2, django-stubs-ext 6, @types/node 26). #26 (mypy) falla en
  `typecheck`. Sus checks son de cuando se abrieron: 8 jobs, sin `migrations`.
- **01 y 02:** specs `Approved` pero **sin `tasks.md`**: no se puede implementar todavía.
- **04:** sin redactar; es el bloqueo de `06-charges`.
- **S-001 (Mercado Pago sandbox):** **sin ejecutar**. Es el mayor riesgo abierto del roadmap.
- **Skills:** antes de esta sesión no existían; ahora están `sdd-verification` y `reviewer-verdict`.
- **Agente de estado:** `project-steward` (nuevo), comandos `/reconcile` y `/handoff`.

## 2. Qué está terminado y NO se debe rehacer

- Tareas mergeadas de 00: `T-PLT-01..06`, `08..28`, `30..36`, `39` (detalle y evidencia en
  `specs/00-platform/tasks.md`).
- No reabrir una tarea `✅` sin evidencia nueva (test que falla, bug reproducible o cambio de spec aprobado).
- No re-especificar 00, 01 ni 02: están `Approved`. Un cambio de comportamiento va por “Historial de cambios”.
- No reescribir los documentos de proceso que ya existen (`context/08`, `ADR-0009`, `ADR-0010`); se extienden.

## 3. Qué sigue, en orden

1. **Cerrar T-PLT-07** (PR #48) → AC-PLT-32. Trae Q-063 y Q-064, que decide el dueño y todavía no están en `main`: si
   siguen abiertas, el PR queda para el dueño.
2. **Cerrar el camino crítico de 00** en este orden:
   - `T-PLT-37` → AC-PLT-25 y parte de AC-PLT-20 y AC-PLT-29 (job `build`).
   - `T-PLT-38` → AC-PLT-01 y el resto de AC-PLT-29 (smoke).
   - `T-PLT-29` → pre-commit de eslint/prettier (RF-PLT-12).
   - `T-PLT-40` → AC-PLT-24 y el cierre de AC-PLT-20 (ruleset; lo mergea el dueño).
   - `T-PLT-41` → comandos de desarrollo (ya documentados en `AGENTS.md`; falta el cierre formal).
   - Acciones del dueño: mover las claves de spikes de su `.env` a `spikes/.env` y correr la verificación manual de
     AC-PLT-01 (`verification.md §4`).
   - Triaje de Dependabot (#25–#31): los saltos mayores tocan versiones fijadas por Q-029 y Q-059.
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

- **Hecho:** reconciliación de 00 con git sobre `1cc858e` (35 ✅ · 6 ☐), matriz de `verification.md` rehecha
  (28 ✔ / 5 ⚠ / 1 ✘), trazabilidad de Q-048 y nota de `.next/server/pages/**` en `design.md §3.3.3` (spec 1.0.12).
- **Merges de la sesión:** #42, #43, #44, #45, #46 y #47. Worklog: `context/worklog/2026-11-06-reconcile-00.md`.
- **Pendiente / dudas:** Q-063 y Q-064 (dueño, llegan con #48), Q-028 (SPEC-12), S-001 sin ejecutar, triaje de
  Dependabot.
- **Siguiente rol sugerido:** `reviewer` sobre #48; después `backend-dev` en T-PLT-37.
