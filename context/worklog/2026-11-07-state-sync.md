# 2026-11-07 — state-sync

- **Nivel:** O1
- **Intención:** conciliar `T-IDA-01` con git. El squash de #65 tomó el asunto del único commit y salió sin `(T-IDA-01)`:
  `main` no se reescribe, así que `check_spec_state.py` necesita una forma explícita de enlazar esa tarea con su merge.
- **Alcance esperado:** `scripts/spec_state.py`, `scripts/check_spec_state.py`, `scripts/spec_state_baseline.json`,
  `scripts/tests/test_check_spec_state.py`, `specs/01-identity-access/tasks.md`, `context/11-estado-actual.md` y este
  worklog. Sin código de producción.
- **Cómo se verifica:** `check_spec_state.py` da 0 drifts sobre `main`; los tests nuevos cubren la entrada válida, la falta
  de entrada, un SHA inexistente, un commit sin PR, un valor que no es SHA completo, un commit de rama sin mergear y
  un commit sin PR que nombra la tarea; gitleaks sin hallazgos.

## Qué se hizo
Clave `squashed_without_id` en la baseline, que exige un SHA real y con PR. La fila de `T-IDA-01` pasa a `✅` y su ficha
vecina `T-IDA-11` guarda las notas del veredicto de #65. La causa quedó corregida fuera del repo: el script de merge de
la sesión ahora pasa el título del PR como asunto del squash.

## Resultado
El primer veredicto (`2882241`) fue RECHAZADO: aceptaba un SHA abreviado, una referencia o un commit de una rama sin
mergear. Ahora la entrada exige 40 hex y que el commit esté en la historia de `HEAD`. Un commit sin PR que nombre la tarea
ya no le gana a la entrada. `check_spec_state.py` da 0 drifts sobre la rama.

Queda fuera: `--write` sin `--spec` sale con 2 porque `tasks.md` de 01 no tiene marcadores de conciliación, y eso rompe el
paso 6 de `/reconcile`.
