---
actualizado: 2026-11-07
ultimo_commit: c5c3136
ultimo_pr: "#65"
modulo_activo: 01-identity-access
fase: implementación (00 en cierre, Implemented pendiente)
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-07)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.22 | 42 ✅ (42) | 42 de 42 tareas | Verificación **Con hallazgos**; ruleset activo |
| 01-identity-access | Approved 1.0.2 | 1 ✅ · 1 🟡 · 30 ☐ (32) | 6 % | Depende de 00; diseño aprobado |
| 02-tenancy-rbac | Approved 1.0.2 | 36 ☐ (36) | 0 % | Se cierra junto con 01 (Q-108); diseño aprobado |
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
- **Dependabot:** #62 mergeado (DRF 3.18.3, psycopg 3.3.7). #26 a #31 cerrados por decisión del dueño (2026-11-07): los
  saltos mayores se ignoran y cada uno se decide por spec. psycopg 3.3.8 revierte un cambio de TLS de 3.3.7: tomarlo
  antes de apuntar a una base con TLS.
- **01 y 02:** specs y diseños aprobados, con los ajustes que indica la cabecera del diseño de 02; ADR-0001 y ADR-0002
  aceptados; `tasks.md` creados (2026-11-06). Sin bloqueos: ADR-0004 y ADR-0011 aceptados y Q-228 decidida el 2026-11-07.
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
3. **Implementar 01 y 02:** cerrar la cola abierta (ver §6) y seguir por olas en `specs/01-identity-access/tasks.md`.
4. **Redactar la spec 04** (bloquea a 06).
5. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
6. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
   `context/12-solid-y-diseno.md` y los agentes existentes.

**Además:** los PR que cambien `.github/workflows/` los mergea el dueño (Q-063).

**Pendiente técnico:**
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

- **Hecho:** decisiones del dueño registradas (#61, #64): diseños de 01 y 02, ADR-0001, 0002, 0004 y 0011, Q-124, Q-125,
  Q-228. `tasks.md` de 01 y 02. `T-IDA-00` (#63) y `T-IDA-01` (#65) mergeadas, parches de #62, y Dependabot sin saltos
  mayores.
- **Merges de la sesión:** #61 a #65.
- **`T-IDA-01` está mergeada y su fila sigue en 🟡:** el squash de #65 salió sin el ID. Lo concilia #74.
- **Cola abierta, en este orden:**
  1. **#74**, RECHAZADO sobre `2882241`. `squashed_without_id` debe exigir 40 hex (`re.fullmatch`) y ascendencia con
     `git merge-base --is-ancestor <sha> HEAD`, con un test por caso. El test con `HEAD` pasa a SHA completo. Actualizar
     `tasks.md:499`, y sumar `## Resultado` al worklog.
  2. **#66** (`T-IDA-26`): rechazo corregido en `ac47698`, falta re-revisión. Avisar al reviewer de dos límites: una fuga
     que dependa de la query no se detecta, y un destino inesperado imprime su path.
  3. **#75** (`T-IDA-02`) y **#76** (`T-IDA-05`, +623 líneas: aceptar o dividir): sin revisar.
  4. **`T-IDA-04` y `T-IDA-09`:** en curso al cerrar, en sus worktrees, sin PR.
  5. **Dependabot:** #70 (Django 5.2.19, tomarlo pronto), #68, #72, #73, y #67 (toca `.github/actions/`, mirarlo aparte).
- **Pendiente / dudas:** ignorar Python en `docker` de `.github/dependabot.yml`, porque lo trató como menor (#69).
  `--write` sin `--spec` sale con 2, porque 01 no tiene marcadores; rompe el paso 6 de `/reconcile`. En 00:
  `design.md:95` no lista `smoke_pages.py`, y faltan las menciones de "línea 257". Q-028, S-001 sin ejecutar, AC-PLT-01.
- **Siguiente rol sugerido:** implementador en #74; después `reviewer` en #66.
