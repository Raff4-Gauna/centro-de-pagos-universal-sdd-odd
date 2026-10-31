# ADR-0010 — Política de control de versiones, CI/CD, tests, logs y rollback

- **Estado:** Aceptado
- **Fecha:** 2026-10-31
- **Specs afectadas:** SPEC-00 (platform, CI/CD concreto). Reglas de constitución `C-15`, `C-16`, `C-17`.

## Contexto
El usuario pidió "buen control de versión" con los agentes trabajando semi-autónomamente, que decidan "la mejor
decisión de cada cuánto mandar los cambios", más desarrollo "por instancias" con tests automáticos, rollback y
logs. Sin una política explícita, cada agente/sesión podría commitear con una cadencia distinta (todo junto al
final, o un commit por línea), lo que hace el historial inútil para revisar o revertir.

## Opciones
1. **Commit manual, a pedido del humano.** Predecible, pero no escala con agentes trabajando sin supervisión
   constante (el pedido explícito del usuario es que el agente lo decida solo).
2. **Commit automático por cada cambio de archivo.** Historial ruidoso, imposible de revisar, no sirve para
   rollback (no hay una unidad de trabajo clara a la que volver).
3. **Commit atómico por unidad de trabajo verificable en verde** (un AC o una tarea completa, con tests y lint
   pasando), con PR por tarea y squash-merge a `main`.

## Decisión
Opción 3, detallada en `context/08-control-de-versiones-ci-cd.md`: rama por tarea/spec/log, commit solo cuando
algo queda en verde (nunca con tests o lint rotos), un commit por AC o por tarea completa, PR con `reviewer`
obligatorio en zona roja, merge por squash, release con `git tag`. El pipeline de CI (lint → tamaño de archivo →
secretos → type-check → arquitectura → tests → cobertura → migraciones reversibles → build → deploy) es el mismo
documento. Logs estructurados (JSON, `request_id`) separados del log de auditoría (que es tabla, no archivo).
Rollback = redeployar el tag anterior + migraciones reversibles + feature flags en zona roja nueva.

## Consecuencias
- Se gana: historial de `main` legible (una línea por tarea/AC), posibilidad real de volver atrás sin arqueología
  de git, agentes que no necesitan preguntar "¿commiteo ahora?" porque la regla ya está escrita.
- Se paga: más disciplina de PR por tarea chica en vez de lotes grandes; el pipeline de CI tarda más por tener
  más etapas.
- Pendiente: elegir las herramientas concretas (gitleaks, ruff/mypy, proveedor de CI) al redactar `00-platform`;
  esta decisión fija la **política**, no el tooling exacto.
