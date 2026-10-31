---
id: SPEC-05
modulo: mercadopago-adapter
estado: Draft
track: S
version: 0.1.0
depende_de: [SPEC-03, S-001]
actualizado: 2026-10-30
---

# Módulo de Adaptador Mercado Pago

> Basado en `context/03-mercadopago-api-notes.md` (verificado 2026-10-30). Lo marcado ⚠️ depende del spike S-001.

## 1. Contexto y problema
El proyecto legacy cobraba por QR con APIs que Mercado Pago movió a la **API de Orders**. Hay que reconstruir la integración como adaptador del motor (SPEC-03), sin copiar el diseño legacy (COM, estado en el objeto, un solo token).

## 2. Objetivo
Permitir que el Hub cree y gestione **cobros QR dinámicos** de Mercado Pago (crear, consultar, cancelar, devolver, gestionar sucursales/cajas y procesar notificaciones) cumpliendo el contrato del motor.

## 3. Alcance
### 3.1 Incluido
- Capacidades: `QR_PAYMENT` (modo **dinámico**), `CANCEL_CHARGE`, `REFUND`, `PAYMENT_STATUS`, `WEBHOOKS`, `POS_MANAGEMENT`.
- Sucursales (Store) y cajas (POS): listar, crear, "crear si no existe".
- Órdenes QR vía `POST /v1/orders`, `GET`, `cancel`, `refund`.
- Verificación de firma y parseo de webhooks del tópico `orders`.
- Mapeo de estados MP → `ProviderStatus`.
- Generación de PNG del QR desde `qr_data` (para el puente ERP).
- Fixtures de sandbox y tests de contrato.
### 3.2 Fuera de alcance
- Point, QR estático e híbrido (SPEC-12, Q-002/Q-003).
- OAuth y renovación de tokens (SPEC-04, Q-014).
- Persistencia de cobros (SPEC-06) y recepción HTTP del webhook (SPEC-07).
- Comisión/neto y conciliación (SPEC-08) — sujeto a ⚠️ Q-016.
- Uso de APIs legacy (`/instore/qr/...`, `POST /qrs`, tópicos `payments`/`merchant_orders`).

## 4. Actores y permisos
Módulo interno. Las acciones las dispara el núcleo con permisos ya validados por SPEC-02/06.

## 5. Glosario del módulo
Ver `context/02-glossary.md`: Store, POS/Caja, Order (MP), `external_reference`.

## 6. Reglas de negocio
- **RN-MP-01** El código nuevo usa **solo** la API de Orders para QR. Prohibido usar endpoints legacy.
- **RN-MP-02** Los montos viajan como **string decimal con 2 decimales** (`"1500.00"`); dentro del Hub son `Decimal`.
- **RN-MP-03** `external_reference` es obligatorio, ≤ 64 caracteres, solo `[A-Za-z0-9_-]` y **sin PII**. Por defecto es el código del cobro del Hub (Q-009). La referencia de la venta del ERP viaja en `description` (≤ 150, sin PII).
- **RN-MP-04** Cada creación/cancelación/devolución envía `X-Idempotency-Key`. La clave se **persiste antes de enviar** y se reutiliza idéntica ante reintentos; el cuerpo de un reintento **nunca cambia**.
- **RN-MP-05** El token se envía **solo** en `Authorization: Bearer`. Nunca por query ni en logs.
- **RN-MP-06** Una notificación se acepta solo si la firma (`x-signature` + `x-request-id` + `data.id` + secreto de la aplicación) es válida; se usa el validador del SDK oficial si existe. Firma inválida → `WebhookVerificationError`.
- **RN-MP-07** La notificación es un **aviso**: para pasar a `PAID` o `REFUNDED` el núcleo confirma con `GET /v1/orders/{id}` (C-04).
- **RN-MP-08** Mapeo de estados (la tabla es normativa):

  | MP `status` | MP `status_detail` | `ProviderStatus` |
  |---|---|---|
  | `created` | `created` | `PENDING` |
  | `processed` | `accredited` | `PAID` |
  | `canceled` | `canceled` | `CANCELED` |
  | `expired` | `expired` | `EXPIRED` |
  | `refunded` | `refunded` | `REFUNDED` |
  | `refunded` | `partially_refunded` | `PARTIALLY_REFUNDED` |
  | cualquier otro | — | `UNKNOWN` (se audita; nunca se adivina) |
  | `at_terminal` | — | *(Point; fuera del MVP)* |

- **RN-MP-09** Cancelar solo es válido con la orden `created`. Si ya está `processed`, el camino es devolución; el adaptador responde con error de validación explicativo, sin llamar a MP si ya conoce el estado.
- **RN-MP-10** Orders **no expone pagos rechazados** en QR: la orden permanece `PENDING` hasta pagarse o vencer. El adaptador no inventa un estado "rechazado".
- **RN-MP-11** `expiration_time` por defecto `PT15M`; configurable por integración dentro de `PT30S`–`PT3H`.
- **RN-MP-12** Sucursales: se exige ubicación **real y completa** (calle, número, ciudad, provincia, latitud, longitud) antes de llamar a MP. Cajas: `name` obligatorio, `external_id` alfanumérico ≤ 40 y único por cuenta, `category` MCC (621102 por defecto en AR).
- **RN-MP-13** "Crear si no existe" distingue **no existe** de **falló la consulta**: ante error o duda se lanza excepción tipada; **nunca** se crea a ciegas (corrige el defecto del legacy).
- **RN-MP-14** El adaptador devuelve `qr_data` (texto del QR). El PNG se genera en el backend (no con servicios externos) cuando el cliente lo pide.
- **RN-MP-15** Fixtures y logs no contienen tokens, secretos ni PII.

## 7. Requisitos funcionales
- **RF-MP-01** Implementar el contrato de SPEC-03 con las capacidades de 3.1. (RN-MP-01)
- **RF-MP-02** `create_charge` construye `POST /v1/orders` con `type=qr`, `config.qr.mode=dynamic`, `config.qr.external_pos_id`, `total_amount`, `transactions.payments[].amount`, `external_reference`, `description`, `expiration_time`. (RN-MP-02/03/11)
- **RF-MP-03** `get_charge`, `cancel_charge`, `refund` (total y parcial) con mapeo de estados. (RN-MP-08/09)
- **RF-MP-04** `verify_webhook` y `parse_webhook` para `order.processed`, `order.refunded`, `order.canceled` y otros `action`. (RN-MP-06)
- **RF-MP-05** `list_pos`, `ensure_store`, `ensure_pos` con validaciones de RN-MP-12/13.
- **RF-MP-06** `test_connection` valida credenciales con una llamada de solo lectura.
- **RF-MP-07** `render_qr_png(qr_data) -> bytes/base64`. (RN-MP-14)

## 8. Requisitos no funcionales
- **RNF-MP-01** Timeouts: conexión ≤ 5 s, lectura ≤ 15 s (configurables).
- **RNF-MP-02** Reintentos solo ante `ProviderUnavailable`/`RateLimited` y con la misma clave de idempotencia (máx. 3, con backoff).
- **RNF-MP-03** Tests de contrato con fixtures reales de sandbox; los tests de red real son opcionales y marcados.

## 9. Modelo conceptual de datos
Sin tablas propias. Configuración por integración (en SPEC-04): `environment`, `expiration_time`, `default_category`, `webhook_secret` (cifrado).

## 10. Estados y transiciones
Ver RN-MP-08. La máquina de estados del cobro está en SPEC-06.

## 11. Contratos
Contra MP: `POST /users/{id}/stores`, `GET/POST/PUT /pos`, `POST/GET /v1/orders`, `POST /v1/orders/{id}/cancel`, `POST /v1/orders/{id}/refund`. Contra el núcleo: contrato de SPEC-03.

## 12. Casos límite y excepciones
- Timeout tras `POST /v1/orders` → `ProviderUnknown`; se reintenta con la misma clave o se consulta por `external_reference` ⚠️.
- Misma clave con cuerpo distinto → `idempotency_key_already_used`: es un bug del núcleo, se registra y se alerta.
- Orden pagada justo al vencer ⚠️ (S-001, paso 7): el adaptador reporta lo que dice MP; la política de expiración está en SPEC-06.
- `external_reference` repetido ⚠️ (S-001, paso 12).
- Caja inexistente o sin `name` → `ProviderValidationError` con mensaje accionable.
- Webhook de otra aplicación o `live_mode` incorrecto para el ambiente de la integración → rechazado y auditado.
- Webhook duplicado o desordenado → el adaptador solo parsea; la idempotencia es de SPEC-06/07.
- Devolución mayor al monto pagado → `ProviderValidationError`.

## 13. Criterios de aceptación
- **AC-MP-01** (RN-MP-01/02/03) **Dado** un `CreateChargeRequest` de `Decimal("1500.00")` **cuando** se crea el cobro **entonces** el request a `/v1/orders` tiene `total_amount: "1500.00"`, `type: "qr"`, `config.qr.mode: "dynamic"` y un `external_reference` válido; el test falla si se usa un endpoint legacy.
- **AC-MP-02** (RN-MP-04) **Dado** un timeout al crear **cuando** se reintenta **entonces** el reintento usa la **misma** `X-Idempotency-Key` y el **mismo** cuerpo.
- **AC-MP-03** (RN-MP-08) **Dado** cada combinación de la tabla **cuando** se mapea **entonces** el resultado coincide; un estado desconocido da `UNKNOWN`.
- **AC-MP-04** (RN-MP-06) **Dado** una notificación con firma válida **cuando** se verifica **entonces** pasa; con firma alterada o `ts` ausente lanza `WebhookVerificationError`.
- **AC-MP-05** (RN-MP-07) **Dado** una notificación `order.processed` **cuando** el núcleo la procesa **entonces** consulta `GET /v1/orders/{id}` antes de declarar `PAID`. *(verificado en SPEC-06/07)*
- **AC-MP-06** (RN-MP-09) **Dado** una orden `processed` **cuando** se pide cancelar **entonces** error de validación explicativo.
- **AC-MP-07** (RN-MP-12) **Dado** una sucursal sin latitud/longitud **cuando** se intenta crear **entonces** falla antes de llamar a MP.
- **AC-MP-08** (RN-MP-13) **Dado** que la consulta de cajas falla por un 503 **cuando** se ejecuta `ensure_pos` **entonces** lanza `ProviderUnavailable` y **no** crea ninguna caja.
- **AC-MP-09** (RN-MP-05/15) **Dado** cualquier llamada **cuando** se inspeccionan logs y fixtures **entonces** no hay tokens ni secretos.
- **AC-MP-10** (RN-MP-14) **Dado** un `qr_data` **cuando** se renderiza **entonces** el PNG decodifica al mismo texto.
- **AC-MP-11** (RN-MP-10) **Dado** un pago rechazado en sandbox ⚠️ **cuando** se consulta la orden **entonces** sigue `PENDING` (se ajusta con S-001).
- **AC-MP-12** (RN-MP-03) **Dado** una referencia con PII o caracteres inválidos **cuando** se arma el request **entonces** se rechaza antes de enviar.

## 14. Interfaz de usuario
No aplica (la UI de integraciones está en SPEC-04).

## 15. Riesgos y supuestos
- ⚠️ Estructura exacta de la respuesta y origen de comisión/neto (S-001).
- Riesgo: MP cambia la API → fixtures y tests de contrato detectan deriva; revisar changelog cada fase.
- Supuesto: una aplicación MP por integración (el secreto de webhook es por aplicación).

## 16. Preguntas abiertas
Q-002, Q-009, Q-014, Q-015, Q-016, Q-017, Q-018, Q-019.

## 17. Trazabilidad
Se completa al generar `tasks.md`.

## 18. Historial de cambios
| Versión | Fecha | Cambio | Motivo |
|---|---|---|---|
| 0.1.0 | 2026-10-30 | Borrador inicial | Basado en docs MP verificadas 2026-10-30 |
