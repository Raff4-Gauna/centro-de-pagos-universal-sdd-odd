---
description: Reconcilia tasks.md, verification.md y el tablero con git, y detecta drift
argument-hint: "<NN-modulo>"
---
Usá el subagente **project-steward** sobre `specs/$ARGUMENTS/` (si no se indica módulo, el de
`context/11-estado-actual.md`).

1. Corré `python scripts/check_spec_state.py` y mostrá el drift tal cual.
2. Cruzá cada `T-XX-NN` con `git log --format='%h|%s'`; actualizá Estado y Evidencia (PR + SHA).
3. Actualizá o creá `verification.md` con la matriz AC→test y la cobertura `✔/⚠/✘`.
4. Actualizá `context/11-estado-actual.md` §1, §3 y el pie de sesión.
5. Listá los AC sin test como bloqueantes y proponé las 3 acciones siguientes.
6. Corré `python scripts/check_spec_state.py --write` para regenerar la conciliación.

No modifiques código de producción. No marques una spec como `Verified`. Si falta una regla, creá `Q-xxx` y pará.
