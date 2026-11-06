---
name: reviewer-verdict
description: Procedimiento para revisar un PR y emitir el veredicto del reviewer con el SHA correcto, separar hallazgos bloqueantes de no bloqueantes y aplicar la regla de zona roja. Úsala al revisar cualquier diff.
allowed-tools: Read, Grep, Glob, Bash
---

# Veredicto del reviewer

## Cuándo usarla
- Hay un PR abierto y toca una zona roja o pide revisión.
- Hay que re-revisar después de un push (el veredicto anterior quedó invalidado).
- El orquestador necesita saber si puede mergear.

## Antes de empezar
1. Obtener el SHA real del último commit del PR: `git rev-parse HEAD` o el SHA que muestra GitHub.
2. Leer la spec, `context/01-constitution.md` y `context/12-solid-y-diseno.md`.
3. Confirmar el alcance de la tarea (`tasks.md`) y que el diff no se salga de él.

## Procedimiento
1. Revisar el **diff completo**, no solo el último commit.
2. Separar hallazgos:
   - **Bloqueantes:** violan `C-xx`, `C-14`, dejan `main` rojo, acreditan dinero sin confirmación, filtran datos,
     rompen aislamiento o se salen del scope.
   - **No bloqueantes:** estilo, SOLID mal aplicado sin violar `C-xx`, mejoras, dudas.
3. Cada hallazgo lleva `archivo:línea` y la regla violada (`C-xx`/`RN-xx`). Sin archivo:línea no es un hallazgo,
   es una opinión.
4. Emitir el comentario con el formato de abajo.
5. Recordar que el label `zona-roja` lo aplica Claude al abrir el PR; el veredicto no lo reemplaza.
6. Si el autor pushea después del veredicto, **no** se reutiliza: se revisa de nuevo y se cita el SHA nuevo.

## Formato
```
VEREDICTO: aprobado | cambios requeridos — SHA <sha> — <YYYY-MM-DD>

## Bloqueantes
| Severidad | Hallazgo | Archivo:línea | Regla |
|---|---|---|---|
| Bloqueante | … | … | C-xx / RN-xx |

## No bloqueantes
| Severidad | Hallazgo | Archivo:línea | Regla |
|---|---|---|---|
| No bloqueante | … | … | … |

## Checklist
- [ ] Zona roja verificada
- [ ] Tests con ID de AC
- [ ] `tasks.md` actualizado
- [ ] Sin secretos/PII
```

## Reglas del proyecto
- 0 aprobaciones nativas de GitHub: la aprobación es el comentario + el label `zona-roja` + el check en verde sobre
  ese SHA.
- `reviewer` no edita archivos ni mergea.
- Con bloqueantes, el veredicto es `cambios requeridos` y el PR no se mergea.
- Sin bloqueantes y con pipeline verde en ese SHA, el veredicto es `aprobado`.
- El merge lo hace Claude solo con certeza total: pipeline completo en verde, veredicto sin bloqueantes, DoD y squash; ante cualquier duda, mergea el dueño (Q-057).

## Errores típicos
- Citar el SHA equivocado o el de la base.
- Aprobar “a ojo” sin correr el chequeo de tests.
- Convertir una preferencia de estilo en bloqueante.
- Aprobar después de un push sin releer el diff.

## Fuente de verdad
`AGENTS.md § Reviewer` · `.claude/agents/reviewer.md` · `context/01-constitution.md` ·
`context/12-solid-y-diseno.md §9` · `context/08-control-de-versiones-ci-cd.md §3.7`.
