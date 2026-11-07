# 2026-11-06 — process-cleanup

- **Nivel:** O1
- **Intención:** cerrar lo que quedó fuera de las fichas de 00 y alinear `main.json` con el ruleset aplicado.
- **Alcance esperado:** `.github/rulesets/main.json`, `.github/workflows/{ci,zona-roja}.yml`,
  `scripts/precommit_frontend.py` y su test, `.claude/commands/handoff.md`, `.claude/agents/reviewer.md`,
  `.claude/skills/{reviewer-verdict,sdd-verification}/SKILL.md`, `specs/00-platform/{spec.sdd,design,tasks,verification,clarifications}.md`,
  `context/11-estado-actual.md`, `README.md`, este worklog.
- **Cómo se verifica:** `reviewer` sin bloqueantes; `verify_repo_protection.py` en 0 tras el merge.

## Qué se hizo
El dueño autorizó aplicar el ruleset y los ajustes una sola vez (2026-11-06). GitHub agregó
`require_extra_approval_for_unattributed_changes: true` por defecto, inerte con 0 aprobaciones: `main.json` lo declara
para que el verificador coincida. `CMD_UNSAFE` suma `\r` y `\n`. Mensajes y reglas viejas corregidas.

## Resultado
Hecho. Toca workflows: por Q-063 lo mergea el dueño, salvo autorización puntual.

## Preguntas nuevas (Q-xxx)
Ninguna.
