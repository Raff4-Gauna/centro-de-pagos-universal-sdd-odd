---
id: SPEC-00
modulo: platform
estado: Por redactar
track: S
version: 0.0.0
---
# Módulo de Plataforma (fundaciones)

Pendiente de redactar con `/spec 00-platform`. Alcance previsto: repositorio y convenciones, Docker Compose (PostgreSQL, Redis, backend, frontend), settings por entorno, logging estructurado (`C-16`), CI completo (lint, tamaño de archivo `C-14`, escaneo de secretos, type-check, tests de arquitectura C-01/C-09, cobertura, chequeo de migraciones reversibles `C-17`) — ver `context/08-control-de-versiones-ci-cd.md §3` para el pipeline ya definido —, OpenAPI versionado (`specs/_contracts/`), `.env.example`, shell de navegación base (selector de empresa/sucursal, layout `(dashboard)` — ver `context/07-frontend-ui-guidelines.md §5`).
Sin bloqueantes: Q-020 se decidió el 2026-10-31 (túnel en desarrollo; hosting de producción antes de H2). El paso 10 del pipeline (deploy a staging) queda fuera de esta spec hasta elegir hosting.
Decisiones técnicas a fijar al redactarla: versiones fijadas (Python, Django, DRF, Celery, PostgreSQL, Redis, Node, Next.js, MUI), gestor de dependencias y lockfile (backend y frontend), gate de cobertura general, `mypy` sí/no, `structlog` vs `logging`+JSON, ADR-0005 (OpenAPI), rate limiting básico, CI en GitHub Actions + protección de `main`.
