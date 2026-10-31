---
id: SPEC-NN
modulo: nombre-en-slug
estado: Draft            # Draft | Clarified | Designed | Approved | Implemented | Verified
track: S
version: 0.1.0
depende_de: []           # ej. [SPEC-02, SPEC-03]
actualizado: YYYY-MM-DD
---

# Módulo de <Nombre>

## 1. Contexto y problema
<Por qué existe este módulo. 3–6 líneas. Qué duele hoy.>

## 2. Objetivo
<Una frase verificable. "Permitir que X haga Y de forma Z".>

## 3. Alcance
### 3.1 Incluido
- …
### 3.2 Fuera de alcance
- … (explícito; evita que el implementador "mejore" cosas)

## 4. Actores y permisos
| Acción | owner | admin | operator | viewer | sistema/ERP |
|---|---|---|---|---|---|
| … | ✔/✘ | | | | |

## 5. Glosario del módulo
<Solo términos nuevos; el resto en `context/02-glossary.md`.>

## 6. Reglas de negocio
> Una regla = una afirmación verificable. Prefijo `RN-<MOD>-NN`.
- **RN-XXX-01** …

## 7. Requisitos funcionales
- **RF-XXX-01** El sistema debe …  (cubre RN-XXX-0n)

## 8. Requisitos no funcionales
Seguridad · rendimiento (ej. p95) · auditoría · observabilidad (logs/métricas) · disponibilidad · privacidad.
- **RNF-XXX-01** …

## 9. Modelo conceptual de datos
| Entidad | Campos clave | Invariantes / constraints |
|---|---|---|
| … | … | … |

## 10. Estados y transiciones
<Tabla estado origen → evento → estado destino → quién/qué lo dispara. Si no hay estados: "No aplica".>

## 11. Contratos
<Endpoints (método, ruta, request, response, errores), eventos, interfaces. Nivel conceptual; el detalle va en `design.md`.>

## 12. Casos límite y excepciones
- … (concurrencia, reintentos, fallas parciales, proveedor caído, datos duplicados, zona horaria, vacíos)

## 13. Criterios de aceptación
> Given / When / Then. Cada AC referencia las reglas que verifica. Prefijo `AC-<MOD>-NN`.
- **AC-XXX-01** (RN-XXX-01)
  - **Dado** …
  - **Cuando** …
  - **Entonces** …

## 14. Interfaz de usuario
<Pantallas, acciones, estados: carga / vacío / error / sin permiso. Si no hay UI: "No aplica".>

## 15. Riesgos y supuestos
- Supuesto: … · Riesgo: … (mitigación)

## 16. Preguntas abiertas
<Enlazar a `clarifications.md`. Las bloqueantes impiden pasar a *Clarified*.>

## 17. Trazabilidad
| AC | Tarea(s) | Test(s) |
|---|---|---|
| AC-XXX-01 | T-XXX-01 | `test_AC_XXX_01_…` |

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | YYYY-MM-DD | Borrador inicial | — |
