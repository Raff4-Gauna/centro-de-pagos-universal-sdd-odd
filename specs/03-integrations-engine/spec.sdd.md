---
id: SPEC-03
modulo: integrations-engine
estado: Draft
track: S
version: 0.1.0
depende_de: [SPEC-00]
actualizado: 2026-10-30
---

# Módulo de Motor de Integraciones

## 1. Contexto y problema
Cada proveedor (Mercado Pago, Payway, Clover) tiene su API, sus montos, sus estados y sus errores. Si el núcleo del Hub conoce esos detalles, cada proveedor nuevo obliga a reescribir cobros, conciliación y reportes. Este módulo define el **contrato común** y el **registro** que aíslan al núcleo de los proveedores.

## 2. Objetivo
Permitir que el núcleo opere cualquier proveedor de pagos a través de un contrato único, de modo que **agregar un proveedor no requiera modificar el núcleo**.

## 3. Alcance
### 3.1 Incluido
- Contrato `BaseAdapter` y DTOs normalizados (cobro, devolución, evento de proveedor).
- `ProviderRegistry` (alta de adaptadores por `provider_code`).
- Catálogo de **capacidades** (`Capability`) y su verificación.
- Taxonomía común de errores con bandera `retryable`.
- Cliente HTTP base (timeouts, reintentos controlados, redacción de secretos en logs).
- `IntegrationContext` (qué recibe un adaptador).
- `FakeAdapter` determinista para pruebas del núcleo sin red.
- Test de arquitectura: el núcleo no importa de `providers/*`.
### 3.2 Fuera de alcance
- Adaptadores concretos (SPEC-05, 13, 14).
- Alta/edición de integraciones, almacenamiento de credenciales y OAuth (SPEC-04).
- Persistencia de cobros y estados (SPEC-06).
- Recepción HTTP de webhooks (SPEC-07).
- UI.

## 4. Actores y permisos
Módulo interno (sin endpoints propios salvo `GET /api/integrations/{id}/capabilities/`, que expone SPEC-04). No hay permisos de usuario propios.

## 5. Glosario del módulo
**Capability**: operación que un adaptador declara soportar. **IntegrationContext**: datos que el core entrega al adaptador por operación. **ProviderRef**: identificador del recurso en el proveedor.

## 6. Reglas de negocio
- **RN-ENG-01** Cada proveedor se implementa como un adaptador registrado con un `provider_code` único (`mercadopago`, `payway`, `clover`).
- **RN-ENG-02** Cada adaptador declara un conjunto **inmutable** de capacidades. El núcleo solo invoca operaciones cuya capacidad esté declarada; si no, se lanza `CapabilityNotSupported` **antes** de cualquier llamada externa.
- **RN-ENG-03** El adaptador recibe un `IntegrationContext` (integración, organización, ambiente, credenciales resueltas). No accede a la base de datos del núcleo ni a otras organizaciones.
- **RN-ENG-04** Las entradas y salidas son DTOs normalizados con `Decimal`. La conversión al formato del proveedor (strings, centavos enteros) ocurre **solo dentro del adaptador** (C-02, C-09).
- **RN-ENG-05** Los errores del proveedor se traducen a: `ProviderAuthError`, `ProviderValidationError`, `ProviderRejected`, `ProviderNotFound`, `ProviderUnavailable` (retryable), `ProviderRateLimited` (retryable), `ProviderUnknown` (resultado ambiguo). Cada error lleva `retryable` y `provider_code`.
- **RN-ENG-06** Las operaciones que mutan estado reciben `idempotency_key`; el adaptador la mapea al mecanismo del proveedor (C-03).
- **RN-ENG-07** Timeouts explícitos en toda llamada. Se reintenta solo ante errores `retryable` **y** con operación idempotente.
- **RN-ENG-08** Las credenciales se resuelven just-in-time y nunca aparecen en logs, `repr`, excepciones ni trazas (C-06). El adaptador no las persiste.
- **RN-ENG-09** Un adaptador con capacidad `webhooks` implementa `verify_webhook` y `parse_webhook`; el núcleo persiste y procesa. Si la verificación falla se lanza `WebhookVerificationError`.
- **RN-ENG-10** Agregar un proveedor = nuevo paquete en `providers/<x>/` + registro + fila en el catálogo. No se edita el núcleo.
- **RN-ENG-11** Un timeout o respuesta ambigua tras una operación mutante produce `ProviderUnknown`; el núcleo **no reintenta a ciegas**: consulta el estado con `get_charge` o reintenta con la **misma** clave de idempotencia.

## 7. Requisitos funcionales
- **RF-ENG-01** `ProviderRegistry.register(adapter_cls)` / `.get(provider_code)`; código duplicado → error al iniciar. (RN-ENG-01)
- **RF-ENG-02** `Capability` enumera: `QR_PAYMENT`, `POS_PAYMENT`, `CARD_PAYMENT`, `CANCEL_CHARGE`, `REFUND`, `PAYMENT_STATUS`, `WEBHOOKS`, `POS_MANAGEMENT`, `SETTLEMENTS`. *(Se agrega `CANCEL_CHARGE`: la propuesta no la incluía y MP la expone.)* (RN-ENG-02)
- **RF-ENG-03** Contrato mínimo (borrador conceptual):
  - `test_connection() -> ConnectionStatus`
  - `create_charge(req: CreateChargeRequest) -> ChargeResult`
  - `get_charge(ref: ProviderRef) -> ChargeResult`
  - `cancel_charge(ref, idempotency_key) -> ChargeResult`
  - `refund(ref, amount: Decimal | None, idempotency_key) -> RefundResult`
  - `verify_webhook(headers, query, body) -> None`
  - `parse_webhook(body) -> ProviderEvent`
  - `list_pos()` / `ensure_store(...)` / `ensure_pos(...)` *(solo con `POS_MANAGEMENT`)*
- **RF-ENG-04** `ChargeResult` incluye estado normalizado (`ProviderStatus`), `provider_ref`, `external_reference`, monto, y datos de presentación (p. ej. `qr_data`). (RN-ENG-04)
- **RF-ENG-05** `FakeAdapter` simula éxito, rechazo, timeout ambiguo, duplicado y webhooks, de forma configurable. (RN-ENG-11)

## 8. Requisitos no funcionales
- **RNF-ENG-01** Ninguna llamada externa sin timeout (conexión y lectura configurables).
- **RNF-ENG-02** Cada llamada al proveedor se registra con: proveedor, operación, duración, resultado, `idempotency_key`, **sin** credenciales ni cuerpo sensible.
- **RNF-ENG-03** Cobertura de pruebas del módulo ≥ 90 % (es contrato y base de todo).

## 9. Modelo conceptual de datos
Sin tablas propias (las crea SPEC-04: `providers`, `integrations`, `integration_credentials`). DTOs en memoria: `CreateChargeRequest`, `ChargeResult`, `RefundResult`, `ProviderEvent`, `ProviderRef`, `IntegrationContext`, `ConnectionStatus`.

## 10. Estados y transiciones
`ProviderStatus` normalizado (lo que un adaptador puede reportar): `PENDING`, `PAID`, `CANCELED`, `EXPIRED`, `REFUNDED`, `PARTIALLY_REFUNDED`, `FAILED`, `UNKNOWN`. La máquina de estados del cobro vive en SPEC-06.

## 11. Contratos
Interfaz Python (RF-ENG-03) y jerarquía de excepciones (RN-ENG-05). Sin endpoints propios.

## 12. Casos límite y excepciones
- El proveedor responde 5xx **después** de crear el recurso (resultado desconocido) → `ProviderUnknown`.
- Reintento con la misma clave pero cuerpo distinto → error del proveedor; el core **nunca** muta el cuerpo en un reintento.
- Credenciales vencidas durante la operación → `ProviderAuthError` (SPEC-04 decide renovar y reintentar una vez).
- Límite de tasa (429) → `ProviderRateLimited` con espera sugerida si el proveedor la informa.
- Adaptador declara una capacidad que el ambiente de pruebas no soporta → el test de contrato lo marca como omitido con motivo, no como éxito.
- Respuesta del proveedor con estado que no conocemos → `ProviderStatus.UNKNOWN` (nunca se adivina).

## 13. Criterios de aceptación
- **AC-ENG-01** (RN-ENG-01) **Dado** un adaptador registrado con código `fake` **cuando** se pide `get("fake")` **entonces** se obtiene su clase; **y** registrar otro con el mismo código falla al iniciar.
- **AC-ENG-02** (RN-ENG-02) **Dado** un adaptador sin `REFUND` **cuando** el core invoca `refund` **entonces** se lanza `CapabilityNotSupported` y no hay llamada de red.
- **AC-ENG-03** (RN-ENG-10, C-09) **Dado** el código del núcleo **cuando** corre el test de arquitectura **entonces** ningún módulo fuera de `providers/` importa desde `providers/*`.
- **AC-ENG-04** (RN-ENG-05) **Dado** un 503 del proveedor **cuando** el adaptador lo traduce **entonces** lanza `ProviderUnavailable` con `retryable=True`; y un 401 lanza `ProviderAuthError` con `retryable=False`.
- **AC-ENG-05** (RN-ENG-08) **Dado** un `IntegrationContext` con token **cuando** se hace `repr()`, se loguea o se lanza una excepción **entonces** el token no aparece en ningún texto.
- **AC-ENG-06** (RN-ENG-11) **Dado** un `FakeAdapter` configurado con timeout ambiguo en `create_charge` **cuando** el core reintenta con la misma clave **entonces** se obtiene el mismo `ChargeResult` y no se crea un segundo recurso.
- **AC-ENG-07** (RN-ENG-04) **Dado** un monto `Decimal("1500.00")` **cuando** pasa por el contrato **entonces** nunca se convierte a `float` en el núcleo.
- **AC-ENG-08** (RN-ENG-07) **Dado** una llamada sin timeout configurado **cuando** se construye el cliente HTTP **entonces** falla con error de configuración.

## 14. Interfaz de usuario
No aplica.

## 15. Riesgos y supuestos
- Riesgo: abstracción demasiado genérica que no calce con Payway/Clover. Mitigación: validar el contrato contra las notas de Payway/Clover antes de congelarlo (se marcan **no verificadas** en `context/03`); el contrato puede evolucionar con ADR.
- Supuesto: un cobro del Hub = una operación del proveedor (SPEC-06).

## 16. Preguntas abiertas
Ninguna bloqueante. Q-002 (Point dentro del MVP → el catálogo de capacidades debe contemplarlo) y Q-007 (Charge + Refund, sin `Payment` separado) quedaron decididas el 2026-10-31 — ver `specs/00-platform/clarifications.md`.

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-30 | Borrador inicial | — |
| 0.1.1 | 2026-10-31 | §16 actualizada | Q-002 y Q-007 decididas |
