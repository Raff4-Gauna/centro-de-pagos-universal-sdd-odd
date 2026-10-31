---
description: Clasifica un pedido en Carril S (SDD) o Carril O (ODD) y propone el siguiente paso
argument-hint: "<descripción del cambio>"
---
Hacé el triage de este pedido: $ARGUMENTS

1. Leé `.agents/workflows/sdd-odd.md` (sección Triage) y `context/01-constitution.md`.
2. Respondé las 5 preguntas del triage una por una, citando qué archivos/módulos se tocarían.
3. Decidí **Carril S** u **O** (nivel O0/O1/O2). Ante la duda, S.
4. Indicá el siguiente comando (`/spec …` o `/log …`) y qué roles intervienen. No escribas código todavía.
