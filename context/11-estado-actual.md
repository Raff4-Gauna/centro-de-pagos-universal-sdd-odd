---
actualizado: 2026-11-27
ultimo_commit: 921d087
ultimo_pr: "#116"
modulo_activo: 01-identity-access + 02-tenancy-rbac
fase: cierre de 01 y 02 (Q-108), verificados Con hallazgos; 00 con verificación Con hallazgos
---

# Estado actual del proyecto

> Tablero vivo. **No duplica reglas de negocio**: dice dónde estamos y qué sigue. La fuente de verdad del detalle
> es `specs/NN-modulo/tasks.md` + `verification.md` + `git log`; si este archivo y git no coinciden, manda git y
> hay que correr `/reconcile`.

## 1. Dónde estamos (2026-11-27)

| Módulo | Spec | Tareas | Código | Nota |
|---|---|---|---|---|
| 00-platform | Approved 1.0.23 | 42 ✅ (42) | 42 de 42 tareas | Verificación **Con hallazgos** (falta AC-PLT-01); ruleset activo |
| 01-identity-access | Approved 1.0.2 | 33 ✅ (33) | 33 de 33 tareas | Verificación conjunta **Con hallazgos** (#153): 38 ✔; Q-130 y Q-131 decididas; se cierra con 02 (Q-108) |
| 02-tenancy-rbac | Approved 1.0.4 | 40 ✅ (40) | 40 de 40 tareas | Verificación conjunta **Con hallazgos** (#153): 40 ✔ (AC-TEN-17 cerrado por T-TEN-40, #155); falta la validación manual de la UI; Q-229 abierta, no bloquea |
| 03-integrations-engine | Draft | — | 0 % | Falta cerrar el contrato del motor |
| 04-integration-management | Por redactar | — | 0 % | Bloquea a 06 |
| 05-mercadopago-adapter | Draft | — | 0 % | Depende del spike S-001 |
| 06-charges | Draft | — | 0 % | Núcleo del dinero; hereda AC-CHG-18 de AC-TEN-28 (Q-244) |
| 07–14 | Por redactar / Futuro | — | 0 % | Ver `specs/ROADMAP.md` |

- **01 y 02:** todo el código planificado está en `main` (`T-IDA-00..32`, PR #63 a #149; `T-TEN-01..40`, PR #82 a
  #155), conciliado con git el 2026-11-27 (`check_spec_state.py`: sin drift). Ninguna tarea está 🧪 y ninguna spec
  está `Verified`. La verificación conjunta (PR #153, sobre `5536088`) dio **Con hallazgos** en las dos.
- **Decisiones del dueño del 2026-11-26** (después de #153): confirma el tope `refresh_ip` de 60/min por IP (Q-130);
  la prueba con Google real se posterga hasta tener hosting y no bloquea `Verified` de 01 (Q-131); la cláusula s2s del
  cobro `pending` sale de AC-TEN-28 y pasa a SPEC-06 como AC-CHG-18 (Q-244).
- **Spec 02 en 1.0.4** (OK del dueño del 2026-11-26): solo cambia AC-TEN-28 (Q-244). La 1.0.3 (PR #151) sumó a
  RNF-TEN-04 `organization.create_repeated` y `operator_command.rejected`, y a AC-TEN-17 lo de Q-243.
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

- Tareas mergeadas: `T-PLT-01..42`, `T-IDA-00..32` y `T-TEN-01..40` (detalle y evidencia en el `tasks.md` de cada
  módulo).
- No reabrir una tarea `✅` sin evidencia nueva (test que falla, bug reproducible o cambio de spec aprobado).
- No re-especificar 00, 01 ni 02: están `Approved`. Un cambio de comportamiento va por “Historial de cambios”.
- No reescribir los documentos de proceso que ya existen (`context/08`, `ADR-0009`, `ADR-0010`); se extienden.

## 3. Qué sigue, en orden

1. **Acciones del dueño para cerrar 01 y 02:** la validación manual de la UI de 02 (`specs/02-tenancy-rbac/verification.md
   §5`, pasos 1 a 3) y asignar Q-229 (no bloquea 02). Después, **el dueño decide `Verified` de 01 y 02 juntos**
   (Q-108). Ningún agente lo marca. Google real queda para cuando haya hosting (Q-131).
2. **Dependabot (2026-11-27):** #73, #147 y #116 mergeados (psycopg 3.3.9 ya trae la reversión de TLS de 3.3.8).
   Quedan dos: #67 (`pnpm/action-setup` 6.1.1, toca `.github/actions/`; lo mergea el dueño, Q-063) y #68 (imagen
   `astral-sh/uv` 0.13.10, rechazado: el test de AC-PLT-25 fija 0.13.6 y CI instala 0.13.6 desde `.github/actions/setup/`;
   el dueño decide si se sube uv en los dos lados o se cierra).
3. **Redactar la spec 04** (bloquea a 06).
4. **Ejecutar S-001** antes de diseñar el adaptador de Mercado Pago.
5. Incorporar el checklist de buenas prácticas de software escalable que el dueño va a pasar; mapearlo contra
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

- **Hecho:** `T-TEN-40` mergeada (#155, `984a532`): AC-TEN-17 ✔ y 02 en 40 ✔. Dependabot: #73 (`a6fe7d5`), #147
  (`5538077`: django 5.2.19, psycopg 3.3.9, pydantic-settings 2.16.3, ruff 0.17.6, pyyaml 6.0.4) y #116 (`921d087`:
  next 16.4.6 y parches de frontend), cada uno con `reviewer` APROBADO sobre el head y CI completo en verde. Versiones
  de los documentos alineadas (spec 00 → 1.0.23, hook `ruff-pre-commit` v0.17.6).
- **Pendiente / dudas:** validación manual de la UI de 02; Q-229 (abierta, no bloquea); #67 (lo mergea el dueño) y #68
  (decisión del dueño sobre uv); Q-220 (SPEC-04/05); Q-028 (SPEC-12); AC-PLT-01; S-001 sin ejecutar.
  `scripts/spec_state_baseline.json` sigue con AC que ya tienen test (lo cambia un PR con `reviewer`, no
  `project-steward`).
- **Siguiente rol sugerido:** el dueño hace la validación manual de 02 y decide `Verified` de 01 y 02; después,
  spec-writer en la spec 04.
