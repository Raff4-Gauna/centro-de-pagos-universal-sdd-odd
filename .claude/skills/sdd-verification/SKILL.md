---
name: sdd-verification
description: Procedimiento para verificar un módulo contra sus criterios de aceptación, armar verification.md y decidir si puede pasar a Verified. Úsala al cerrar un módulo o cuando haya que actualizar la matriz AC→test.
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# Verificación SDD (paso 6)

## Cuándo usarla
- Un módulo terminó sus tareas y hay que llenar `specs/NN-modulo/verification.md`.
- Hay que re-verificar después de cerrar tareas pendientes.
- `project-steward` detectó que `verification.md` no existe o está desactualizado.

## Antes de empezar
1. La spec está `Approved` o `Implemented` (no `Draft`).
2. `tasks.md` está conciliado con git (`python scripts/check_spec_state.py` sin drift).
3. Leíste `specs/_templates/verification.md` y `context/01-constitution.md`.

## Procedimiento
1. **Extraer los AC** de `spec.sdd.md` (IDs `AC-<MOD>-NN`). No inventes AC que la spec no tiene.
2. **Buscar el test de cada AC** por su ID literal en:
   - `backend/tests/**/test_*.py`
   - `scripts/tests/test_*.py`
   - `frontend/src/**/*.test.ts` y `*.test.tsx`
3. **Clasificar la cobertura**, no la intención:
   - `✔` hay test con el ID y cubre el criterio completo.
   - `⚠` hay test, pero cubre solo una parte (decir qué falta).
   - `✘` no hay test o la tarea que lo produce está pendiente.
4. **Ejecutar de verdad** y pegar la salida o el enlace al run:
   - `pytest -c scripts/pytest.ini scripts/tests`
   - `DC exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend pytest`
   - `pnpm test` y `pnpm typecheck`, desde `frontend/`
   - `pre-commit run --all-files`
   Si no se ejecutó, escribir **“pendiente”**. Nunca “debería pasar”.
5. **Pruebas transversales:** aislamiento por organización, idempotencia, permisos por rol, secretos/PII,
   migraciones reversibles. Si no aplican todavía, decir **N/A** y por qué.
6. **Checklist manual:** pasos reproducibles para el dueño, con requisitos previos y resultado esperado.
7. **Revisión de código:** pedir al `reviewer` el diff completo del módulo (no solo el último PR).
8. **Decisión:** `Aprobada`, `Con hallazgos` o `Rechazada`. Si es “Con hallazgos”, listar las tareas a reabrir o
   crear y el AC que cada una desbloquea.

## Reglas de evidencia
- Un AC no pasa a `✔` porque el archivo de test exista: tiene que haber corrido en verde en el commit que se
  verifica.
- Un `⚠` no se convierte en `✔` por optimismo: se cierra la tarea que falta o se deja el hallazgo.
- `tasks.md` pasa a `🧪` **solo** para las tareas cuyos AC quedaron `✔` y ejecutados.
- La spec pasa a `Verified` **solo** con el OK explícito del dueño. Ningún agente la marca solo.
- Si un AC desapareció de la spec, se borra su fila de `verification.md`; si aparece uno nuevo, se agrega.

## Errores típicos
- Copiar la matriz de otra sesión sin re-ejecutar.
- Marcar `✔` un AC cubierto por un test que solo verifica el nombre del archivo.
- Confundir “la tarea está mergeada” con “el AC está verificado”.
- Cerrar el módulo con tareas `☐` o `⛔`.

## Fuente de verdad
`specs/_templates/verification.md` · `specs/NN-modulo/spec.sdd.md` · `specs/NN-modulo/tasks.md` ·
`.agents/workflows/sdd-odd.md §6` · `context/01-constitution.md`.
