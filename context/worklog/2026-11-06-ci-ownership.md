# 2026-11-06 — ci-ownership

- **Nivel:** O1
- **Intención:** alinear `AGENTS.md` con Q-057: Claude se encarga de todo el CI y de GitHub, merge incluido.
- **Alcance esperado:** `AGENTS.md`, `.claude/skills/reviewer-verdict/SKILL.md`, `.claude/agents/reviewer.md`, este
  worklog. Son rutas de gobierno (zona roja por Q-058): van con `reviewer` aunque sean solo documentos.
- **Cómo se verifica:** `python scripts/check_spec_state.py` sin drift; `grep` sin menciones de "mergea el dueño".

## Qué se hizo
El texto agregado en la sesión de proceso del 2026-11-05 decía que hasta T-PLT-40 mergeaba el dueño, lo que
contradecía Q-057 (decidida por el dueño el 2026-10-31) y su pedido del 2026-11-02. El dueño lo confirmó el
2026-11-06: "Claude sigue mergeando y se encarga de todo el CI". Se mantiene el criterio de certeza de Q-057.

## Resultado
Hecho. #42 y #43 se mergearon con esta regla antes de corregir el texto: CI verde y `reviewer` aprobado, sin label.

## Preguntas nuevas (Q-xxx)
Ninguna.
