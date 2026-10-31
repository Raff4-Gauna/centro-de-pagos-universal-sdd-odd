# Flujo de trabajo: SDD + ODD

## 0. Idea central
Dos carriles y una sola fuente de verdad (`specs/` + `context/`).

| | **Carril S — SDD** | **Carril O — ODD** |
|---|---|---|
| Enfoque | Especificación formal antes de implementar | Exploración y proceso proporcional a la tarea |
| Cuándo | Lo que es caro o peligroso si sale mal | Cambios chicos, claros y reversibles |
| Documentación | Artefactos formales y persistentes | Proporcional a la complejidad (worklog) |
| Riesgo que cubre | Reglas de negocio mal entendidas | Burocracia innecesaria |

**Ante la duda, Carril S.** El triage es un paso de 30 segundos, no una discusión.

---

## 1. Triage
Responder en orden. El primer "sí" manda a **Carril S**.

1. ¿Toca una **zona roja**? (dinero · estados de cobro · webhooks/idempotencia · credenciales · auth/permisos · aislamiento por organización · migraciones · contratos públicos · adaptadores)
2. ¿Es un módulo/feature nuevo o cambia una regla de negocio?
3. ¿Cambia un contrato público (endpoint, evento, esquema de BD)?
4. ¿Hay una ambigüedad que no se resuelve con una sola pregunta?
5. ¿Afecta a más de un módulo, o va a superar ~5 archivos / ~150 líneas?

Todo "no" → **Carril O**.

---

## 2. Carril S — los 6 pasos de SDD

| # | Paso | Artefacto (en `specs/NN-modulo/`) | Rol | Comando | Gate de salida |
|---|---|---|---|---|---|
| 1 | Especificar | `spec.sdd.md` → *Draft* | spec-writer | `/spec` | Objetivo, alcance, fuera de alcance, reglas (RN), criterios (AC) y preguntas (Q) escritos con IDs |
| 2 | Aclarar | `clarifications.md` → *Clarified* | clarifier | `/clarify` | 0 preguntas bloqueantes abiertas · matriz de permisos completa · casos límite revisados |
| 3 | Diseñar | `design.md` (+ ADR) → *Designed* | architect | `/design` | Cada RN/RF tiene dónde vive · contratos definidos · **tu aprobación → *Approved*** |
| 4 | Dividir | `tasks.md` | task-planner | `/tasks` | Cada AC cubierto por ≥1 tarea · tareas de ≤ ~300 líneas de diff, mergeables solas |
| 5 | Programar | código + tests | backend-dev / frontend-dev / integration-dev | `/implement T-xx` | La tarea cumple su DoD y no se salió del scope |
| 6 | Verificar | `verification.md` → *Verified* | qa-verifier + reviewer | `/verify` | Matriz AC→test en verde · revisión sin bloqueantes · validación funcional manual · **tu OK** |

Estados de una spec: `Draft → Clarified → Designed → Approved → Implemented → Verified`.
**Dos gates humanos:** *Approved* (después de diseñar) y *Verified* (después de verificar). Ningún agente los pasa solo.

### Reglas de oro del Carril S
- **Cero código antes de *Approved*.** (Excepción: spikes del Carril O2, que no se mergean.)
- Una tarea = un cambio pequeño, revisable y que deja el sistema funcionando.
- El implementador solo toca los archivos que lista su tarea.
- Si el implementador descubre una regla faltante: agrega `Q-xxx`, para, y vuelve al paso 2 solo para esa pregunta.

---

## 3. Carril O — ODD proporcional

Se abre una entrada de worklog **antes** de empezar (`context/worklog/YYYY-MM-DD-slug.md`, plantilla en `specs/_templates/worklog-entry.md`).

| Nivel | Ejemplo | Qué se registra | Verificación |
|---|---|---|---|
| **O0 trivial** | typo, texto de UI, formato | solo el mensaje de commit | lint |
| **O1 chico** | bug con causa clara, ajuste de UI, refactor sin cambio de comportamiento, tests faltantes | worklog de 5–8 líneas | test que falla antes y pasa después |
| **O2 exploración (spike)** | "¿qué devuelve realmente Mercado Pago en sandbox?" | nota de hallazgos con **timebox** | el entregable es conocimiento (fixtures, respuestas a Q), **no código mergeable** |

Los spikes alimentan el Carril S: sus hallazgos cierran preguntas (`Q-xxx`) o crean specs.

---

## 4. Escalamiento y des-escalamiento
- **O → S** (obligatorio): durante un cambio O aparece una zona roja, se supera ~5 archivos / ~150 líneas, o se descubre una ambigüedad de negocio. Se frena, se anota en el worklog y se abre el flujo S.
- **S liviano:** un cambio chico pero en zona roja (ej. un campo nuevo en reembolsos) **edita la sección correspondiente de la spec existente** + agrega 1–2 tareas. No requiere `design.md` nuevo.
- Las specs son documentos vivos: un cambio de comportamiento = editar la spec (con historial), no crear otra.

## 5. Cambiar una spec ya *Approved*
1. Abrir `Q-xxx` o nota de cambio explicando el porqué.
2. Editar la spec y agregar fila al "Historial de cambios" (versión, fecha, qué, por qué).
3. Revisar impacto en `design.md`, `tasks.md` y tests; marcar lo afectado.
4. Volver a *Approved* con tu OK.

## 6. Definition of Ready / Done

**Tarea lista para implementar (DoR):** cita AC · lista archivos esperados · tiene plan de pruebas · sus dependencias están hechas · spec en *Approved*.

**Tarea terminada (DoD):**
- [ ] Tests automáticos escritos y en verde (nombre incluye `AC-…`).
- [ ] Lint/format/type-check en verde.
- [ ] Ningún archivo tocado supera ~400 líneas (`C-14`); si lo supera, se dividió por capa antes de seguir.
- [ ] Aislamiento por organización probado si toca datos de negocio (test cross-tenant).
- [ ] Sin secretos ni PII en logs; logs estructurados con `request_id`/`task_id` (`C-16`).
- [ ] Si hay migración de BD: reversible y probada en ambos sentidos (`C-17`).
- [ ] Spec/diseño actualizados si el comportamiento cambió.
- [ ] Revisión del `reviewer` (obligatoria en zonas rojas).
- [ ] Commit atómico creado (Conventional Commits) — ver `context/08-control-de-versiones-ci-cd.md §2.2`.
- [ ] `tasks.md` actualizado.

## 6bis. Control de versiones, CI, tests, logs y rollback
No es un paso aparte del flujo: es la forma en la que **cualquier** paso que produce código (5 en Carril S, el
único paso de Carril O1) queda en el repo. Detalle completo, con cadencia de commits y pipeline de CI, en
`context/08-control-de-versiones-ci-cd.md`. Resumen: commit atómico apenas algo queda en verde, nunca `main`
roto, PR + `reviewer` en zona roja, release con `git tag`, migraciones reversibles, logs estructurados.

## 7. Orden de arranque recomendado
1. **Spike S-001** (Mercado Pago sandbox) — `specs/00-platform/spikes/S-001-mp-sandbox.md`.
2. Responder las preguntas bloqueantes de `specs/00-platform/clarifications.md`.
3. Spec `00-platform` (fundaciones) → *Approved* → implementar.
4. Specs `01` y `02` (identidad, tenencia) → *Approved* → implementar.
5. Núcleo del dinero: `03` motor → `05` adaptador MP → `06` cobros → `07` webhooks.
6. `08` conciliación → `09` reportes → `11` puente ERP.
