# Skills de Claude Code

Una **skill** es un procedimiento repetible que varios agentes necesitan recordar. No reemplaza al subagente ni a
la spec: dice *cómo* hacer el trabajo sin violar las reglas.

| Skill | Cuándo usarla | Agentes que la cargan |
|---|---|---|
| [`sdd-verification`](sdd-verification/SKILL.md) | Cerrar un módulo, armar/actualizar `verification.md`, decidir si pasa a `Verified` | `qa-verifier`, `project-steward`, orquestador |
| [`reviewer-verdict`](reviewer-verdict/SKILL.md) | Revisar un PR, emitir el veredicto con SHA y aplicar la regla de `zona-roja` | `reviewer`, orquestador |

## Reglas de las skills
- Una skill = un procedimiento; las reglas de negocio viven en `specs/` y `context/01-constitution.md`.
- Cada skill cita su fuente de verdad y no la copia.
- Si una skill y una `C-xx` chocan, manda la constitución.
- Si el procedimiento cambia, se actualiza la skill en el mismo PR.
- No se crean skills para chequeos deterministas: eso son scripts de `scripts/` + CI.

## Estructura
```
.claude/skills/
├── README.md
├── sdd-verification/SKILL.md
└── reviewer-verdict/SKILL.md
```
Cuando una skill necesite detalle, se agrega `references/*.md` y se carga solo si hace falta. El `SKILL.md` no
debería pasar de ~150 líneas.
