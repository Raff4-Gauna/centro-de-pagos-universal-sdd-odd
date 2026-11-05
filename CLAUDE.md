@AGENTS.md
@context/11-estado-actual.md

# Notas específicas de Claude Code

- Claude Code **no lee `AGENTS.md` por sí solo**; por eso este archivo lo importa con `@AGENTS.md`.
- El **tablero vivo** se importa con `@context/11-estado-actual.md`: cada sesión nueva sabe dónde quedó sin
  empezar de cero. Si el tablero y `git log` no coinciden, manda git y se corre `/reconcile`.
- Para tareas del **Carril S**, empezá en modo plan y usá los comandos:
  `/triage` → `/spec` → `/clarify` → `/design` → `/tasks` → `/implement T-xx` → `/verify`.
- Para el **Carril O**: `/log "intención"` abre la entrada de worklog y después trabajás directo.
- Para reconciliar el estado del proyecto: `/reconcile <NN-modulo>` (subagente `project-steward`).
- Para cerrar la sesión: `/handoff` (actualiza el tablero, corre `check_spec_state.py` y deja Hecho/Pendiente/Siguiente).
- Los subagentes viven en `.claude/agents/` y los define `.agents/roles.md`. Los subagentes no pueden crear otros
  subagentes: la sesión principal orquesta.
- El revisor (`reviewer`) es de solo lectura a propósito: quien escribe el código no lo revisa. Su veredicto es un
  comentario en el PR que cita el SHA del último commit + el label `zona-roja`; no es un approve nativo.
- Nunca leas ni imprimas `.env*` (está denegado en `.claude/settings.json`).

## Arranque de una sesión nueva

1. Leer `context/11-estado-actual.md` (se importa solo) y `context/01-constitution.md`.
2. Correr `python scripts/check_spec_state.py`.
3. Si hay drift, `/reconcile <NN-modulo>` antes de tocar nada.
4. Tomar la primera acción pendiente de `context/11-estado-actual.md §3`.
5. Anunciar qué se retoma y qué **no** se rehace.
