---
actualizado: 2026-11-06
ultimo_commit: 7329a7a
ultimo_pr: "#60"
modulo_activo: 01-identity-access
fase: implementación (00 en cierre, Implemented pendiente)
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-06)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.21 | 42 ✅ (42) | 42 de 42 tareas | Verificación **Con hallazgos**; ruleset activo |
| 01-identity-access | Approved 1.0.1 | 32 ☐ (32) | 0 % | Depende de 00; diseño aprobado |
| 02-tenancy-rbac | Approved 1.0.1 | 36 ☐ (36) | 0 % | Se cierra junto con 01 (Q-108); diseño aprobado |
| 03-integrations-engine | Draft | — | 0 % | Falta cerrar el contrato del motor |
| 04-integration-management | Por redactar | — | 0 % | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | — | 0 % | Depende del spike S-001 |
| 06-charges | Draft | — | 0 % | Núcleo del dinero |
| 07–14 | Por redactar / Futuro | — | 0 % | Ver `specs/ROADMAP.md` |

- **00-platform:** las 42 tareas mergeadas (PR #4–#56). El pipeline está completo: 10 jobs de `ci.yml`, con el smoke
  como último paso de `build`, en verde sobre `82cd31c` (run `42271234974`), más `zona-roja`, que solo corre en PR.
- **`main` está protegida:** ruleset `26732747` activo desde el 2026-11-06, aplicado por Claude con autorización puntual
  del dueño; cambiar ruleset y ajustes sigue siendo solo suyo. `verify_repo_protection.py` da `OK`.
- **Verificación:** `specs/00-platform/verification.md` da **Con hallazgos**: 33 AC ✔, 1 ⚠ (`AC-PLT-01`). Ningún AC se marcó ✔ sin test. Lo que falta para cada uno está en §7 de ese documento.
- **Requisito vigente para hosting (Q-065):** el puerto del backend no se expone a internet y el HTTPS queda a cargo
  del frente. **Webhooks:** ruta de entrada sin definir; abrir un `Q-xxx` al redactar ese módulo.
- **Q-063, ampliada por el dueño:** todo PR que agregue o cambie un archivo de `.github/workflows/` lo mergea él, no
  solo los de `zona-roja.yml`. #48 (Q-063), #52 (scope drift) y #55 (Q-057) los mergeó Claude con autorización
  puntual del dueño, citada en cada PR.
- **Dependabot:** #62 reemplaza a #25 (parches de DRF y psycopg). Seis saltos de versión mayor sin triaje, #26 a #31
  (Django 6.1, redis 8, Tailwind 4, mypy 2, django-stubs-ext 6, @types/node 26). #26 (mypy) falla en `typecheck`.
- **01 y 02:** specs y diseños aprobados, con los ajustes que indica la cabecera del diseño de 02; ADR-0001 y ADR-0002
  aceptados; `tasks.md` creados (2026-11-06). Se pueden implementar en cuanto esa rama esté en `main`, salvo `T-IDA-04`
  y `T-IDA-08`, que esperan que el dueño acepte ADR-0004.
- **04:** sin redactar; es el bloqueo de `06-charges`.
- **S-001 (Mercado Pago sandbox):** **sin ejecutar**. Es el mayor riesgo abierto del roadmap.
- **Skills:** antes de esta sesión no existían; ahora están `sdd-verification` y `reviewer-verdict`.
- **Agente de estado:** `project-steward` (nuevo), comandos `/reconcile` y `/handoff`.

## 2. Qué está terminado y NO se debe rehacer

- Tareas mergeadas de 00: `T-PLT-01..42` (detalle y evidencia en
  `specs/00-platform/tasks.md`).
- No reabrir una tarea `✅` sin evidencia nueva (test que falla, bug reproducible o cambio de spec aprobado).
- No re-especificar 00, 01 ni 02: están `Approved`. Un cambio de comportamiento va por “Historial de cambios”.
- No reescribir los documentos de proceso que ya existen (`context/08`, `ADR-0009`, `ADR-0010`); se extienden.

## 3. Qué sigue, en orden

1. **Verificación manual de AC-PLT-01** (`verification.md §4`). Antes, el dueño mueve las claves de spikes de su
   `.env` a `spikes/.env`.
2. **Repetir la verificación** de 00 y marcar las filas `🧪`. Solo el dueño puede pasar la spec a `Verified`.
3. **Implementar 01 y 02:** ola 0 de `specs/01-identity-access/tasks.md` (`T-IDA-00`, `T-IDA-01`) y seguir por olas.
4. **Redactar la spec 04** (bloquea a 06).
5. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
6. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
   `context/12-solid-y-diseno.md` y los agentes existentes.

**Además:** triaje de Dependabot (#25–#31), sin orden fijo: los saltos mayores tocan versiones fijadas por Q-029 y
Q-059. Los PR que cambien `.github/workflows/` los mergea el dueño (Q-063).

**Pendiente técnico:**
- `check_migrations_roundtrip --allow-data-loss` no mira a qué BD apunta: lo cierra `T-IDA-00`, antes de la primera
  migración de SPEC-01.
- `scripts/smoke_stack.py` necesita el mecanismo de URL de ejemplo para rutas `[id]` y no debe contar un 3xx como
  página revisada (línea 257): lo cierra `T-IDA-26`, antes de la primera ruta protegida (`T-IDA-28`).

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

- **Hecho:** reconciliación final de 00 con git sobre `82cd31c` (42 ✅) y `verification.md` al día (33 ✔ / 1 ⚠). Ruleset aplicado y probado en vivo (#58, #59).
- **Merges de la sesión:** #48, #50 a #56. Worklog: `context/worklog/2026-11-06-reconcile-00c.md`.
- **Pendiente / dudas:** Q-028 (SPEC-12), S-001 sin ejecutar, triaje de Dependabot.
- **Siguiente rol sugerido:** el dueño corre AC-PLT-01; después `qa-verifier` repite la verificación de 00.
