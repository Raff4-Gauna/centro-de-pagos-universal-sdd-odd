---
description: Cierra la sesión, actualiza el tablero y deja el traspaso para la próxima
argument-hint: "[nota opcional]"
---
Cerrá la sesión sin tocar código de producción. Si hay una nota ($ARGUMENTS), incorporala al pie.

1. Actualizá `context/11-estado-actual.md`: fecha, último commit (`git log -1 --format='%h'`), último PR, módulo
   activo, §1 (dónde estamos), §3 (qué sigue) y §6 (pie de sesión).
2. Actualizá `specs/NN-modulo/tasks.md` y `verification.md` si cambió algún estado.
3. Corré `python scripts/check_spec_state.py` y pegá el resultado (sin ocultar fallos).
4. Dejá el bloque:
   ```
   Hecho: …
   Pendiente / dudas (Q-xxx): …
   Siguiente rol sugerido: …
   ```
5. Si hubo cambios de documentos, commit `docs(platform): session handoff <fecha>` en una rama `log/YYYY-MM-DD-handoff`
   y PR: el ruleset rechaza el push directo a `main`.

Si quedó trabajo a medias sin commit, decilo explícitamente: es la información que git no puede reconstruir.
