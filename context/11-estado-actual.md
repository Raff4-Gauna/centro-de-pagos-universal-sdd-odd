---
actualizado: 2026-11-26
ultimo_commit: 6fd9ed6
ultimo_pr: "#151"
modulo_activo: 01-identity-access + 02-tenancy-rbac
fase: verificación conjunta de 01 y 02 (Q-108); 00 con verificación Con hallazgos
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-26)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.22 | 42 ✅ (42) | 42 de 42 tareas | Verificación **Con hallazgos** (falta AC-PLT-01); ruleset activo |
| 01-identity-access | Approved 1.0.2 | 33 ✅ (33) | 33 de 33 tareas | Falta la verificación conjunta con 02 (Q-108) |
| 02-tenancy-rbac | Approved 1.0.3 | 39 ✅ (39) | 39 de 39 tareas | Falta la verificación conjunta con 01 (Q-108); Q-229 abierta, no bloquea |
| 03-integrations-engine | Draft | — | 0 % | Falta cerrar el contrato del motor |
| 04-integration-management | Por redactar | — | 0 % | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | — | 0 % | Depende del spike S-001 |
| 06-charges | Draft | — | 0 % | Núcleo del dinero |
| 07–14 | Por redactar / Futuro | — | 0 % | Ver `specs/ROADMAP.md` |

- **01 y 02:** todo el código planificado está en `main` (`T-IDA-00..32`, PR #63 a #149; `T-TEN-01..39`, PR #82 a
  #151), conciliado con git el 2026-11-26 (`check_spec_state.py`: sin drift). Ninguna tarea está 🧪 y ninguna spec
  está `Verified`. `specs/01-identity-access/verification.md` es una apertura parcial y 02 no tiene `verification.md`:
  los completa la pasada conjunta.
- **Spec 02 en 1.0.3** (OK del dueño del 2026-11-26, PR #151): RNF-TEN-04 suma `organization.create_repeated` y
  `operator_command.rejected`; AC-TEN-17 recoge Q-243.
- **Seguimientos técnicos** de las revisiones (no bloqueantes, sin tarea): en la sección del mismo nombre de cada
  `tasks.md` de 01 y 02.
- **00-platform:** 42 tareas mergeadas (PR #4–#56); `verification.md` da **Con hallazgos**: 33 AC ✔, 1 ⚠ (`AC-PLT-01`).
- **`main` protegida:** ruleset `26732747` activo; cambiar ruleset y ajustes es solo del dueño.
- **Requisito vigente para hosting (Q-065):** el puerto del backend no se expone a internet y el HTTPS queda a cargo
  del frente. **Webhooks:** ruta de entrada sin definir; abrir un `Q-xxx` al redactar ese módulo.
- **Q-063:** todo PR que agregue o cambie un archivo de `.github/workflows/` lo mergea el dueño.
- **04:** sin redactar; es el bloqueo de `06-charges`. **S-001 (Mercado Pago sandbox):** sin ejecutar; es el mayor
  riesgo abierto del roadmap.

## 2. Qué está terminado y NO se debe rehacer

- Tareas mergeadas: `T-PLT-01..42`, `T-IDA-00..32` y `T-TEN-01..39` (detalle y evidencia en el `tasks.md` de cada
  módulo).
- No reabrir una tarea `✅` sin evidencia nueva (test que falla, bug reproducible o cambio de spec aprobado).
- No re-especificar 00, 01 ni 02: están `Approved`. Un cambio de comportamiento va por “Historial de cambios”.
- No reescribir los documentos de proceso que ya existen (`context/08`, `ADR-0009`, `ADR-0010`); se extienden.

## 3. Qué sigue, en orden

1. **Verificación conjunta de 01 y 02** (`qa-verifier`, Q-108): matriz AC→test de los dos módulos, corridas reales y
   evidencia manual de los E2E (`scripts/e2e_login.py`, `scripts/e2e_tenancy.py`). En la misma pasada, el dueño confirma
   el tope `refresh_ip` (`specs/01-identity-access/tasks.md`, "Ajustes al diseño").
2. **El dueño decide `Verified`** para 01 y 02 juntos. Ningún agente lo marca.
3. **Dependabot abiertos (GitHub, 2026-11-26):** #147 (parches de `uv`), #116 (parches de npm), #73, #68 y #67
   (toca `.github/actions/`). #80 y #81 se cerraron el 2026-11-17 sin merge (sus grupos siguen en #147 y #116).
   psycopg 3.3.8 revierte un cambio de TLS de 3.3.7: tomarlo antes de apuntar a una base con TLS (mirar si #147 lo trae).
4. **Redactar la spec 04** (bloquea a 06).
5. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
6. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
   `context/12-solid-y-diseno.md` y los agentes existentes.

**Sigue pendiente de 00:** la corrida manual de AC-PLT-01 por el dueño (`specs/00-platform/verification.md §4`) y
repetir esa verificación.

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

- **Hecho:** reconciliación de 01 y 02 con git sobre `6fd9ed6`: 33 ✅ en 01 y 39 ✅ en 02, con PR y SHA de squash;
  conciliación generada en los dos `tasks.md`; Q-229 registrada como abierta; "Ajustes al diseño" y seguimientos
  técnicos de las revisiones; spec 02 citada como 1.0.3. Reemplaza al PR #77, que había quedado viejo.
- **Pendiente / dudas:** Q-229 (abierta, no bloquea); el tope `refresh_ip` lo confirma el dueño; Q-220 (SPEC-04/05);
  Q-028 (SPEC-12); AC-PLT-01; S-001 sin ejecutar.
- **Siguiente rol sugerido:** `qa-verifier` en la verificación conjunta de 01 y 02.
