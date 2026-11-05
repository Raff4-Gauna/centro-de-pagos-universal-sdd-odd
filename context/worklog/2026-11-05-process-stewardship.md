# 2026-11-05 — process-stewardship

- **Nivel:** O1
- **Intención:** cerrar el drift entre lo que dice el tablero (`tasks.md`/`verification.md`), lo que pasó en git y
  el estado real del proyecto; agregar un rol de bibliotecario (`project-steward`) y un chequeo determinista.
- **Alcance esperado:** `context/11-estado-actual.md`, `context/12-solid-y-diseno.md`,
  `context/decisions/ADR-0011-solid-y-fronteras.md`, `context/decisions/README.md`, `context/worklog/`,
  `AGENTS.md`, `CLAUDE.md`, `README.md`, `.agents/roles.md`, `.claude/agents/{project-steward,reviewer}.md`,
  `.claude/commands/{reconcile,handoff}.md`, `.claude/skills/**`, `specs/00-platform/{tasks,verification}.md`,
  `specs/README.md`, `scripts/check_spec_state.py`, `scripts/spec_state_baseline.json`,
  `scripts/tests/test_check_spec_state.py`. Solo proceso, documentación y tooling: **sin código de producción**.
- **Cómo se verifica:** `python scripts/check_spec_state.py` sin drift sobre el árbol real;
  `pytest -c scripts/pytest.ini scripts/tests/test_check_spec_state.py`; `ruff check` y `ruff format --check` sobre
  los archivos Python nuevos. Los tests del script usan repos git temporales (no tocan el repo real).

## Qué se hizo

- Se reconciliaron las 41 tareas de `00-platform` con `git log`: 30 mergeadas, 10 pendientes, 1 bloqueada por
  Q-048. Cada tarea mergeada quedó con PR y SHA de merge en `tasks.md`.
- Se creó `specs/00-platform/verification.md` con la matriz AC→test (26 ✔, 2 ⚠, 6 ✘) y la decisión
  **Con hallazgos**, sin marcar nada como `Verified`.
- Se agregó `context/11-estado-actual.md` como tablero vivo y se importó desde `CLAUDE.md`.
- Se agregó `context/12-solid-y-diseno.md` + `ADR-0011` con el mapeo SOLID a las capas del proyecto.
- Se agregó el rol `project-steward`, los comandos `/reconcile` y `/handoff`, y las skills
  `sdd-verification` y `reviewer-verdict`.
- Se agregó `scripts/check_spec_state.py` con baseline explícito para los 7 AC sin cobertura conocidos.

## Resultado

Hecho. Los AC sin test (`AC-PLT-01, 05, 17, 24, 29, 32, 33`) quedan en el baseline, no ocultos: el script falla si
aparece uno nuevo. La spec `00-platform` **no** se marca `Verified`: falta el OK del dueño y cerrar tareas.

## Preguntas nuevas (Q-xxx)

- Ninguna. Se reutilizan Q-048 (`.env.example`) y Q-057/Q-058 (merge y zonas rojas).

## Revisión (2026-11-05)
- Bloqueante corregido: mypy en `scripts/tests/test_check_spec_state.py` (`dict` invariante).
- Corregido: ADR-0011 vuelve a **Propuesto** (sin OK del dueño); `project-steward` ya no escribe en `.claude/**`,
  `.agents/**`, `AGENTS.md`, `CLAUDE.md` ni en su propio chequeo/baseline; AC-PLT-06 y AC-PLT-20 pasan a ⚠; la nota
  "en CI corre" de `tasks.md` era falsa (todavía no está enganchado); comandos de `AGENTS.md` que no existen marcados
  como pendientes.
- Va por Carril O pese a tocar `scripts/**` (zona roja por Q-058) porque es tooling de proceso que no toca el gate de
  CI; igual pasó por `reviewer`.
- **Para después (falsos "sin drift" del chequeo):** leer `git log` de `origin/main` (no de HEAD) y exigir `(#PR)`
  para considerar mergeada una tarea; reportar filas cuyo ID no calza; exigir un solo símbolo de estado por celda;
  buscar el ID del AC con límite de palabra y fuera de comentarios; `SHA_RE` no debe aceptar `#1234567`; 🧪 debe
  exigir que todos sus AC estén ✔; renombrar `test_corpus`; engancharlo en el job `lint`.

