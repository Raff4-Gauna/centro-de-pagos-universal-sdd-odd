---
spec: SPEC-NN
fecha: YYYY-MM-DD
resultado: Pendiente     # Aprobada | Con hallazgos | Rechazada
---
# Verificación — Módulo <Nombre>

## 1. Matriz AC → test
| AC | Test(s) | Resultado |
|---|---|---|
| AC-XXX-01 | `test_AC_XXX_01_…` | ✔/✘ |

## 2. Pruebas transversales
- [ ] Aislamiento entre organizaciones (recurso de otra org → 404/403)
- [ ] Idempotencia / repetición
- [ ] Permisos por rol
- [ ] Sin secretos/PII en logs ni respuestas
- [ ] Migraciones aplican y revierten

## 3. Validación funcional manual (la hace el dueño)
1. Paso reproducible …
2. …

## 4. Revisión de código (reviewer)
| Severidad | Hallazgo | Archivo:línea | Regla | Estado |
|---|---|---|---|---|

## 5. Decisión
<Aprobar → spec *Verified* · o listar tareas a reabrir.>
