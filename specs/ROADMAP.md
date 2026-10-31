# Roadmap de módulos

> Orden pensado en **rebanadas verticales**: se descubre pronto lo incierto (Mercado Pago real) y se llega a un cobro de punta a punta antes de pulir.

## Módulos
| ID | Módulo | Objetivo | Depende de | Zona roja | Hito | Estado |
|---|---|---|---|---|---|---|
| 00 | platform | Repo, Docker, CI, settings, logging, convenciones, OpenAPI | — | No | H1 | Por redactar |
| 01 | identity-access | Usuarios, login con Google, JWT, sesión segura | 00 | **Sí** | H1 | Por redactar |
| 02 | tenancy-rbac | Organizaciones, memberships, roles, sucursales, filtro obligatorio | 01 | **Sí** | H1 | Por redactar |
| 03 | integrations-engine | Contrato común: BaseAdapter, registry, capacidades, errores, FakeAdapter | 00 | **Sí** | H2 | **Draft** |
| 04 | integration-management | Alta de integraciones, credenciales cifradas, prueba de conexión, (OAuth) | 02, 03 | **Sí** | H2 | Por redactar |
| 05 | mercadopago-adapter | Stores/POS, órdenes QR, cancelar, devolver, parseo y firma de webhooks | 03, S-001 | **Sí** | H2 | **Draft** |
| 06 | charges | Cobros, estados, idempotencia, cancelación, devolución | 02, 03, 04 | **Sí** | H2–H3 | **Draft** |
| 07 | webhooks | Receptor firmado, registro de eventos, dedupe, procesamiento asíncrono, poller | 05, 06 | **Sí** | H3 | Por redactar |
| 08 | reconciliation | Bruto/comisión/neto, diferencias, duplicados, comprobantes | 06, 07, S-001 | **Sí** | H4 | Por redactar |
| 09 | reports | Totales por proveedor/sucursal/período, exportación | 08 | No | H4 | Por redactar |
| 10 | audit | Registro de auditoría append-only (mínimo desde H1) | 00 | **Sí** | H1→ | Por redactar |
| 11 | erp-bridge | Credenciales máquina-a-máquina (API keys), contrato estable para el ERP, PNG del QR, cliente .NET | 06, 07 | **Sí** | H5 | Por redactar |
| 12 | mercadopago-point | Terminales Point y cobros presenciales | 05, 06 | **Sí** | H2–H3 (dentro del MVP, ver Q-002) | Por redactar |
| 13 | payway-adapter | Tarjetas / POS Payway | 03, S-002 | **Sí** | Fase 9 | Futuro |
| 14 | clover-adapter | Clover (OAuth, dispositivo) | 03, S-002 | **Sí** | Fase 10 | Futuro |

## Dependencias (resumen)
```
00 ─┬─ 01 ─ 02 ─┬─ 04 ──┐
    ├─ 03 ──────┤       ├─ 06 ─ 07 ─ 08 ─ 09
    │    └─ 05 ─────────┘             └─ 11
    └─ 10 (transversal)
```

## Cambios respecto del plan por fases de la propuesta
1. **Spike S-001 antes de cualquier diseño del adaptador** (la doc de MP cambió; hay datos que solo el sandbox confirma).
2. **Webhooks pasan a módulo propio (07)**: son la parte más delicada del dinero.
3. **Auditoría (10) arranca temprano**, no al final.
4. **Puente ERP (11) explícito**: el ERP no puede iniciar sesión con Google.
5. **Point (12) dentro del MVP, pero después del QR** *(actualizado 2026-10-31, Q-002: el usuario decidió no
   recortarlo; se mantiene el orden de implementación — primero QR de punta a punta, después Point — ver nota
   en `specs/00-platform/clarifications.md`)*.
6. La interfaz se especifica **dentro de cada módulo** (sección 14 de la spec), no como una fase aparte. El
   *cómo* común a todas esas pantallas (Material UI + Tailwind, esquemas de carga, arquitectura cliente/servidor)
   está en `context/07-frontend-ui-guidelines.md`.
7. **S-002** (`specs/00-platform/spikes/S-002-payway-clover-docs.md`) es el equivalente de S-001 para Payway y
   Clover: confirma contra cuentas de prueba reales lo que hoy son notas de documentación pública
   (`context/05-payway-api-notes.md`, `context/06-clover-api-notes.md`). Se ejecuta recién antes de las fases 9/10,
   no bloquea el MVP. **Actualización 2026-10-31:** la cuenta de desarrollador y la app sandbox de Clover ya están
   creadas (`context/10-clover-cuenta-sandbox-real.md`); falta solo correr los pasos del spike (dispositivo/
   simulador + venta de punta a punta). Payway sigue sin cuenta de prueba propia.
8. **Shell de navegación** (selector de empresa/sucursal, "Inicio", "Configuración") se especifica una sola vez
   como contexto transversal en `context/07-frontend-ui-guidelines.md §5`, no como módulo propio: cada fila de su
   tabla de "Configuración" ya apunta al módulo (`02`, `04`, `08`, `11`, `12`, `14`) que la implementa.
9. **Buenas prácticas de desarrollo** (tamaño de archivo, control de versiones, CI/CD, tests, logs, rollback) se
   fijaron antes de escribir código en `context/01-constitution.md` (`C-14`–`C-17`) y
   `context/08-control-de-versiones-ci-cd.md`. Aplican desde el primer commit de `00-platform`, no se posponen.

## Primer camino de punta a punta (meta de H2)
Org fija en BD → integración MP sandbox → caja → `POST /api/charges/` → QR → pago con comprador de prueba → webhook → cobro `paid`.
