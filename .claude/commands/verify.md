---
description: Paso 6 SDD — verifica la spec implementada y arma verification.md
argument-hint: "<NN-modulo>"
---
Para `specs/$ARGUMENTS/`:

1. Subagente **qa-verifier**: matriz AC → test → resultado, tests faltantes y checklist de validación funcional manual.
2. Subagente **reviewer** (solo lectura): revisión del diff completo del módulo.
3. Consolidá en `specs/$ARGUMENTS/verification.md`. Si hay bloqueantes, listá qué tarea hay que reabrir.
4. Pedime el OK para marcar la spec como **Verified**.
