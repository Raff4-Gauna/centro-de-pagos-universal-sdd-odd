# Decisiones de arquitectura (ADR)

Plantilla: `specs/_templates/adr.md`. Una decisión por archivo: `ADR-NNNN-slug.md`.

## ADR a escribir (candidatos)
| ID | Decisión | Se necesita antes de |
|---|---|---|
| ADR-0001 | Multi-tenancy: esquema compartido + `organization_id`, managers tenant-aware; RLS de PostgreSQL como segunda barrera (cuándo) — **Aceptado** 2026-11-06 | Spec 02 |
| ADR-0002 | Organizaciones/Membership **propios** vs `django-organizations` / `django-saas` (la propuesta menciona ambos; ver Q-027) — **Aceptado** 2026-11-06 | Spec 02 |
| ADR-0003 | Almacenamiento y cifrado de credenciales (Fernet/KMS, rotación de clave, refresh de OAuth) | Spec 04 |
| ADR-0004 | Dónde vive el JWT en el navegador (cookie httpOnly vía capa servidor de Next.js vs localStorage) — **Aceptado** 2026-11-07 | Spec 01 |
| ADR-0005 | Contrato primero: OpenAPI generado (drf-spectacular) versionado en `specs/_contracts/` y tipos del frontend generados desde ahí | Spec 00 |
| ADR-0006 | Representación de dinero y moneda | Spec 06 |
| ADR-0007 | Asincronía: Celery + beat (poller de seguridad); Outbox diferido | Spec 07 |
| ADR-0008 | Auth máquina-a-máquina: API keys por organización con scopes | Spec 11 |
| ADR-0009 | Límite de tamaño de archivo (~400 líneas) y modularidad por capas — **Aceptado** 2026-10-31 | Spec 00 |
| ADR-0010 | Control de versiones, CI/CD, tests, logs y rollback — **Aceptado** 2026-10-31 | Spec 00 |
| ADR-0011 | SOLID como criterio de diseño por fronteras, subordinado a `C-xx` y a la proporcionalidad de ODD — **Aceptado** 2026-11-07 | Specs 00–07, 11 |
