# Legacy: GUAZUNCHITO_MP_QR (qué conservar y qué no)

> **Aclaración (2026-10-31, a pedido del usuario):** "GUAZUNCHITO_MP_QR" es únicamente el nombre interno del
> proyecto legacy que este Hub reemplaza — no tiene relación con el nombre ni la identidad de **Centro de Pagos
> Universal**. Se mantiene en este archivo solo como referencia histórica (qué conocimiento del cobro por QR de
> Mercado Pago vale la pena conservar); no es una convención a repetir en ningún otro lugar del proyecto nuevo.

Proyecto funcional (2025): Python + SDK propio + servidor **COM** (`MPQR.Server`) + **SQL Server** + webhook local con ngrok, consumido por un sistema de gestión de escritorio.

## Qué se conserva (conocimiento, no código)
- Flujo de alta: **sucursal → caja → cobro**, con convención de nombres `SUC001` / `SUC001POS001` y categoría `621102`.
- Patrón "crear si no existe" y **sincronización masiva** local ↔ Mercado Pago (`sync_all_pos_with_mp`).
- Registro de eventos con nivel, componente, identificador externo y excepción (base de la auditoría).
- Contrato funcional que el ERP ya conoce: crear QR, consultar estado, cancelar, obtener QR en PNG Base64, último error.

## Qué NO se traslada
| Legacy | Por qué | En el Hub |
|---|---|---|
| Servidor COM | Atado a Windows y a un proceso; difícil de escalar y testear | API REST + (después) un cliente .NET delgado |
| Estado en el objeto (`_last_png`, `_last_oid`, `_last_error`) | No es seguro con concurrencia | Respuestas explícitas por llamada |
| `pos_exists` devuelve `False` también ante error | Confunde "no existe" con "falló" → riesgo de crear duplicados | Excepciones tipadas (`NotFound` ≠ `ProviderUnavailable`) |
| Un único token en `.env` | Single-tenant | Credenciales cifradas por integración |
| Estado del pago por heurísticas (`result.get(...) or result.get('data'...)`) | Frágil | Estados normalizados + máquina de estados |
| ngrok y `webhook_server_32.py` | Solo desarrollo | Receptor de webhooks firmado y asíncrono |
| `title` en el cobro | Eliminado en Orders | `description` (≤150, sin PII) |

## Hallazgos a tener en cuenta
- ✅ **Resuelto (2026-10-31):** con `const.py` y `qr_client.py` a la vista, el legacy usaba
  `PUT/POST/DELETE /instore/orders/qr/seller/collectors/{user_id}/pos/{external_pos_id}/qrs` para crear (dos
  llamadas: `PUT` crea la orden, `POST` al mismo endpoint devuelve `qr_data`), consultar y cancelar, y
  `GET /instore/qr/seller/collectors/{user_id}/pos/{external_pos_id}/orders` para el estado pre-pago. Es,
  efectivamente, la API presencial anterior a Orders — **confirma que hay que migrar entero a `POST /v1/orders`**
  (RN-MP-01); no se reutiliza ni un endpoint.
- El legacy ya intuía el problema de "Orders no expone rechazos" (RN-MP-10): `get_order_status` primero
  consultaba la orden QR (pre-pago) y, si no encontraba nada, caía a buscar en `/v1/payments/search` por
  `external_reference`. Es el mismo patrón de dos fuentes que describe `context/03-mercadopago-api-notes.md`,
  solo que hecho con heurísticas (`result.get(...) or result.get('data', {}).get(...)`) en vez de una máquina de
  estados — exactamente lo que el Hub reemplaza por estados normalizados (RN-CHG-07/08).
- El webhook legacy (`webhook.py`) procesaba tópicos **`payment`** y **`merchant_order`**, que ya no existen en
  Orders (hoy es un único tópico **`orders`**, ver §4 de `context/03-mercadopago-api-notes.md`): otra confirmación
  de que no hay nada de webhooks para reutilizar, solo el patrón de **guardar primero, deduplicar por hash del
  payload y marcar procesado después**, que sí vale la pena conservar (se traduce al diseño de `webhook_events`
  de SPEC-07).
- La cancelación legacy (`cancel_order`) usaba `DELETE` sobre el mismo endpoint de creación y, si fallaba, un
  **método alternativo** que creaba una "orden de cancelación" de \$0,01 (`_alternative_cancel`) — un parche para
  un problema real (no se podía cancelar de forma confiable) que en Orders se resuelve mejor: `POST
  /v1/orders/{id}/cancel` solo es válido con la orden en `created` (RN-MP-09); si ya está `processed`, el camino
  correcto es devolución, no un cobro trampa de centavos.
- El esquema SQL Server del legacy (`db_config.py`: `mp_credenciales`, `mp_sucursales`, `mp_cajas`, `mp_ordenes`,
  `mp_orden_items`, `mp_pagos`, `mp_webhooks`, `mp_logs`, `mp_configuraciones`) ya separaba credenciales,
  sucursales/cajas, órdenes y pagos, y el log de eventos ya guardaba nivel/módulo/excepción — ese nivel de
  separación es compatible con el modelo de `SPEC-06` (`charges`/`charge_events`/`refunds`). Lo que no se
  traslada es la *forma* (SQL Server + `pyodbc` + procedimientos ad-hoc): el Hub usa PostgreSQL con
  `DecimalField`, migraciones de Django y los managers tenant-aware de `C-01`.
- La sucursal de prueba "Resistencia, Chaco" se creó con coordenadas de Buenos Aires (ver
  `context/09-cuenta-sandbox-mp-datos-reales.md`). Mercado Pago pide ubicación real (impacta impuestos/
  facturación): en producción usar las coordenadas correctas, no copiar esta sucursal de prueba tal cual.
- Los datos de la cuenta de pruebas (usuario MP, store, POS, token `TEST-…`) están documentados aparte en
  `context/09-cuenta-sandbox-mp-datos-reales.md`, **no en este archivo**, para no mezclar credenciales con
  decisiones de diseño. Ese archivo recuerda rotar el token si se compartió fuera de un canal privado.
- Hay una inconsistencia de ERP: el legacy habla de un sistema en **C# .NET**; la propuesta, de **PowerBuilder + SQL Server** (Q-023).

## Convivencia
El legacy sigue funcionando mientras el Hub no lo reemplace. **No se migran datos** (Q-022). Cuando el ERP pueda consumir REST, se apaga el COM.
