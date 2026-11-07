---
actualizado: 2026-11-12
ultimo_commit: 4b75be5
ultimo_pr: "#78"
modulo_activo: 01-identity-access
fase: implementación (00 en cierre, Implemented pendiente)
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-12)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.22 | 42 ✅ (42) | 42 de 42 tareas | Verificación **Con hallazgos**; ruleset activo |
| 01-identity-access | Approved 1.0.2 | 7 ✅ · 25 ☐ (32) | 22 % | Depende de 00; diseño aprobado |
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
3. **Implementar 01 y 02:** ola 2 de 01 (`T-IDA-03`, `T-IDA-08`, después `T-IDA-06`) y ola 0 de 02 (`T-TEN-01`),
   siguiendo las olas de cada `tasks.md`.
4. **Redactar la spec 04** (bloquea a 06).
5. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
6. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
   `context/12-solid-y-diseno.md` y los agentes existentes.

**Además:** los PR que cambien `.github/workflows/` los mergea el dueño (Q-063).

**Pendiente técnico:** el smoke ya no cuenta un 3xx como página revisada y tiene URL de ejemplo para `[id]`
(`T-IDA-26`, #66). Falta documentarlo en `specs/00-platform/design.md:95` y en `verification.md` de 00.

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

- **Hecho:** ola 0 y ola 1 de 01 mergeadas: `T-IDA-00` (#63), `01` (#65), `26` (#66), `05` (#76), `02` (#75), `04` (#79)
  y `09` (#78). #74 enlaza el squash de #65, que salió sin el ID, y `pr.sh` ahora pasa el título del PR como asunto.
- **Merges de las sesiones del 2026-11-07 al 12:** #61 a #66, #74 a #76, #78 y #79.
- **En curso:** `T-IDA-03`, `T-IDA-08` y `T-TEN-01`, en paralelo, cada una en su worktree.
- **Notas que van a las fichas cuando arranque cada tarea:**
  - `T-IDA-10`: `title` de `rate_limited` en español en `apps/common/api/problems.py`; pasar `IDENTITY_JWT_*` e
    `IDENTITY_BFF_CREDENTIALS` en `infra/docker-compose.yml`.
  - `T-IDA-11`/`13`: nivel propio del logger `audit` en la primera tarea que llame a `record`.
  - `T-IDA-14`/`15`: tests de servicio de AC-IDA-15, 16 y 28; `used_at` y `now` del mismo reloj.
  - `T-IDA-20`: `IDENTITY_BFF_CREDENTIALS` distinta de `IDENTITY_JWT_SIGNING_KEY` y de `DJANGO_SECRET_KEY` (design §7.5).
  - `T-IDA-28`: probar que `return_to` no se refleje en la página.
- **Dependabot:** #70 (Django 5.2.19, tomarlo pronto), #68, #72, #73, #80, #81, y #67 (toca `.github/actions/`).
- **Pendiente / dudas:** ignorar Python en `docker` de `.github/dependabot.yml` (#69). `--write` sin `--spec` sale con 2
  porque 01 no tiene marcadores; rompe el paso 6 de `/reconcile`. Q-028, S-001 sin ejecutar, AC-PLT-01.
- **Siguiente rol sugerido:** `reviewer` en los PR de `T-IDA-03`, `T-IDA-08` y `T-TEN-01`; después `backend-dev` en
  `T-IDA-06`.
