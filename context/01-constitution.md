# Constitución del proyecto (reglas no negociables)

Cambiarlas requiere un ADR y tu aprobación explícita. Ninguna spec ni tarea puede contradecirlas.

> **C-14 a C-17** se agregaron el 2026-10-31 a pedido explícito del usuario (buenas prácticas de desarrollo,
> seguridad y control de versiones desde el día uno). Ver `ADR-0009` y `ADR-0010`.

| ID | Regla | Cómo se verifica |
|---|---|---|
| **C-01 Aislamiento** | Toda entidad de negocio lleva `organization_id`. Toda lectura/escritura pasa por managers/selectors tenant-aware. | Test cross-tenant por endpoint; test de arquitectura que prohíbe `Model.objects` crudo en servicios de negocio |
| **C-02 Dinero** | `Decimal` en dominio y BD (`max_digits=12, decimal_places=2`). Nunca `float`. Las conversiones (centavos enteros, strings) ocurren **solo dentro del adaptador**. | Lint/grep en CI; tests de redondeo |
| **C-03 Idempotencia** | Crear cobro/cancelar/devolver exige clave de idempotencia. Los webhooks se procesan de forma idempotente (dedupe + transiciones que son no-op si ya se aplicaron). | Tests de repetición y concurrencia |
| **C-04 Verdad del pago** | Un cobro solo pasa a pagado por confirmación **servidor-a-servidor** (webhook verificado + consulta al proveedor, o poller). Nunca por el navegador/frontend. | Test: ningún endpoint de cliente puede setear `paid` |
| **C-05 Máquina de estados** | Estados y transiciones explícitos. Una transición inválida se rechaza y queda auditada. | Tests de tabla de transiciones |
| **C-06 Secretos** | Credenciales cifradas en reposo; nunca en logs, errores, respuestas completas ni fixtures. Rotación de tokens atómica. | Test de que `repr`/logs no filtran; revisión |
| **C-07 Webhooks** | Verificar firma, responder 2xx rápido, procesar en cola. Sin firma válida → 401 y no se procesa. | Tests con firma válida/ inválida |
| **C-08 Auditoría** | Toda acción sensible y cambio de estado registra quién, qué, cuándo y en qué organización. Log de auditoría append-only. | Tests de eventos |
| **C-09 Frontera del adaptador** | Nada específico de un proveedor fuera de `integrations/providers/<x>/`. El core solo conoce DTOs normalizados y capacidades. | Test de arquitectura (imports) |
| **C-10 Privacidad** | Sin PII en `external_reference`/`description` enviados a proveedores. Guardar del pagador solo lo imprescindible. | Revisión + tests de sanitizado |
| **C-11 Pruebas** | Todo criterio de aceptación tiene ≥1 test automático con su ID en el nombre. Los adaptadores tienen tests de contrato con fixtures de sandbox. | Matriz AC→test en `verification.md` |
| **C-12 Spec manda** | El código que contradice una spec Approved es un bug (del código o de la spec): se corrige uno u otro de forma explícita, nunca en silencio. | Revisión |
| **C-13 Dependencias** | No se agregan dependencias en zonas rojas sin ADR. Versiones fijadas. | Revisión |
| **C-14 Tamaño y modularidad de archivo** | Ningún archivo de código (`.py`, `.ts`, `.tsx`, `.jsx`) supera **~400 líneas**. Si una funcionalidad crece, se divide por responsabilidad (capas `api/`→`services/`→`selectors/`→`domain/`→`models.py` en backend; `app/`→`modules/`→`components/`→`hooks/`→`lib/` en frontend), nunca se "aprieta" en un archivo más largo. | Script de CI (`scripts/check_file_size.py`, ver `context/08-control-de-versiones-ci-cd.md`) que falla el build ante cualquier archivo por encima del límite |
| **C-15 Control de versiones** | Commits atómicos por cambio cohesivo (Conventional Commits), nunca un commit que deje `main`/la rama de integración en estado roto (tests o lint en rojo). Una tarea `T-xx` completa = al menos un commit propio. Zonas rojas solo mergean vía PR con `reviewer` aprobado. | CI bloquea merge si el pipeline no está verde; revisión de historial |
| **C-16 Observabilidad** | Toda request/tarea asíncrona genera logs **estructurados** (JSON) con `request_id`/`task_id`, `organization_id` (si aplica), componente y duración — nunca `print` ni logs de texto libre en código de negocio. El log de auditoría (C-08) es un canal aparte, append-only, no se mezcla con logs operativos. | Revisión; test de que el logger de negocio usa el formateador estructurado |
| **C-17 Reversibilidad y despliegue** | Toda migración de base de datos es reversible y se prueba en ambos sentidos antes de mergear. Cada release queda etiquetada (`git tag`) para poder volver atrás. Un cambio riesgoso en zona roja se protege con *feature flag* antes de activarse por defecto. | CI corre `migrate` y `migrate <app> <anterior>` en un entorno descartable; checklist de release |
