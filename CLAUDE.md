@AGENTS.md

# Notas específicas de Claude Code

- Claude Code **no lee `AGENTS.md` por sí solo**; por eso este archivo lo importa con `@AGENTS.md`.
- Para tareas del **Carril S**, empezá en modo plan y usá los comandos: `/triage` → `/spec` → `/clarify` → `/design` → `/tasks` → `/implement T-xx` → `/verify`.
- Para el **Carril O**: `/log "intención"` abre la entrada de worklog y después trabajás directo.
- Los subagentes viven en `.claude/agents/` y los define `.agents/roles.md`. Los subagentes no pueden crear otros subagentes: la sesión principal orquesta.
- El revisor (`reviewer`) es de solo lectura a propósito: quien escribe el código no lo revisa.
- Nunca leas ni imprimas `.env*` (está denegado en `.claude/settings.json`).
