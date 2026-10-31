# Notas de la API de Mercado Pago (Argentina)

> **Verificado el 2026-10-30** contra la documentación pública de Mercado Pago Developers. Esta API cambia: antes de codificar un endpoint, reconfirmar en la doc oficial (el subagente `integration-dev` tiene esa obligación).
> Lo marcado ⚠️ **no está confirmado** y se resuelve en el spike S-001.

## 1. Conclusión para el proyecto
- **Sucursales (Store) y cajas (POS) siguen vigentes** con los mismos endpoints que usaba el proyecto legacy.
- **La creación y gestión de cobros QR se movió a la API de Orders (`POST /v1/orders`)**. Las APIs anteriores ("Órdenes presenciales V2" — `PUT /instore/qr/seller/collectors/.../orders` — y "QR Modelo dinámico" — `POST /qrs`) tienen guías de migración y MP indica que las novedades solo se desarrollan sobre Orders. No se encontró una fecha de apagado: ⚠️ revisar el changelog/panel.
- Las notificaciones cambiaron: **tópico `orders`** (se configura en la aplicación, en "Tus integraciones"). En Orders no existe `notification_url` y los tópicos `payments` / `merchant_orders` no aplican.
- **Regla del proyecto (RN-MP-01):** código nuevo usa **solo** Orders API.

## 2. Orders API — QR
| Tema | Dato |
|---|---|
| Crear | `POST https://api.mercadopago.com/v1/orders` → `201` con la orden completa |
| Consultar | `GET /v1/orders/{id}` |
| Cancelar | `POST /v1/orders/{id}/cancel` (solo si la orden está `created`) |
| Devolver | `POST /v1/orders/{id}/refund` (total o parcial) |
| Autenticación | `Authorization: Bearer <access_token>` **solo por header** (por query no se permite) |
| Idempotencia | `X-Idempotency-Key` **obligatorio** en crear, cancelar y devolver. Misma clave + body distinto → error `idempotency_key_already_used` |
| `type` | `qr` |
| Modos QR | `config.qr.mode`: `static`, `dynamic`, `hybrid`. Dinámico = QR único por transacción; devuelve `qr_data` que **la app convierte en imagen QR** |
| Caja | `config.qr.external_pos_id` (en el body, ya no en el path) |
| Montos | strings con 2 decimales: `"total_amount": "50.00"`, `transactions.payments[].amount` |
| `external_reference` | **obligatorio**, máx. 64, solo letras, números, `-` y `_`, **sin PII** |
| `description` | máx. 150, sin PII (reemplaza a `title`, que se eliminó) |
| `expiration_time` | duración ISO 8601 (`PT15M`); mínimo `PT30S`, máximo `PT3H`; por defecto 15 min |
| Estados (`status`) | `created`, `processed`, `refunded`, `canceled`, `expired` (+ `at_terminal` en Point) |
| `status_detail` | `created`, `canceled`, `accredited`, `refunded`, `expired`, `partially_refunded` |
| Pagos rechazados | **No se exponen** en Orders: la orden queda `created` hasta que haya un pago aprobado |

## 3. Orders API — Point
- `type: "point"`, `config.point.terminal_id` (obtenido del listado de terminales: `GET /terminals/v1/list`).
- La terminal debe estar configurada en modo **PDV** (o SELF_SERVICE).
- La orden se carga sola en la terminal; si no, el operador actualiza en el dispositivo.
- Cancelar por API solo con estado `created`. Si está `at_terminal`, se cancela **en el dispositivo** y el aviso llega por webhook.
- Una terminal con una orden pendiente rechaza órdenes nuevas (409).

## 4. Webhooks
- Se configuran **por aplicación** (Tus integraciones → Webhooks), tópico **"Order (Mercado Pago)"**. Cada aplicación tiene su **clave secreta** (no vence; renovarla es recomendable).
- Notificación: query `data.id` y `type`; body con `action` (`order.processed`, `order.refunded`, `order.canceled`…), `api_version`, `application_id`, `date_created`, `id`, `live_mode`, `type`, `user_id`, `data`.
- Validación: header `x-signature` (`ts=…,v1=…`) + `x-request-id` + `data.id` + secreto. Los SDK oficiales traen `WebhookSignatureValidator` (también Python) → **usarlo**.
- Responder `200/201` dentro de **22 s**; MP recomienda responder primero y procesar después. Reintenta si no recibe 2xx.
- Tras responder, consultar `GET /v1/orders/{id}` para el estado completo.
- Identificar al vendedor cuando hay una sola URL para varios: la doc sugiere agregar `?client=…` a la URL. Nuestra decisión provisional: **una URL por integración** con id no adivinable (Q-015).
- Tópico opcional `mp-connect`: avisa cuando una cuenta se vincula/desvincula por OAuth.

## 5. Sucursales y cajas
| Recurso | Endpoint | Notas |
|---|---|---|
| Crear sucursal | `POST /users/{user_id}/stores` | `location` obligatorio y **real** (calle, número, ciudad, provincia, lat/long); datos incorrectos pueden afectar cálculo de impuestos y facturación. `external_id` propio |
| Crear caja | `POST /pos` | `name` obligatorio para poder crear órdenes QR; `external_id` único por cuenta, alfanumérico, máx. 40; `external_store_id` = `external_id` de la sucursal; `category` = MCC (621102 en Argentina); nuevo `config.qr.operating_mode` (p. ej. `pdv` = atendido) |
| Actualizar caja | `PUT /pos/{id}` | `409` si el `external_id` ya existe |

## 6. Credenciales
- **Integración propia** (tu app, tu cuenta): Access Token de producción de tu aplicación.
- **Integración de terceros** (vendedores que te autorizan): Access Token por **OAuth (authorization code)**. El token dura **180 días**; se renueva con `refresh_token`, y **cada renovación entrega un refresh token nuevo que hay que guardar** (rotación). → El `CredentialManager` debe renovar de forma atómica y tolerar carreras.
- El `user_id` para crear sucursales sale de la cuenta (propia) o de la respuesta OAuth (terceros).

## 7. Sandbox
- Al crear la aplicación se generan **cuentas de prueba** (vendedor y comprador, con saldo ficticio) y credenciales de prueba (`APP_USR-…`).
- Flujo de prueba: crear sucursal+caja con credenciales de prueba → crear orden → pagar con la app de MP logueada con el comprador de prueba → verificar webhook (`order.processed`).
- Hay tarjetas de prueba con comportamientos fijos (aprobado / rechazado).
- ⚠️ La doc histórica decía que el entorno de pruebas no valida devoluciones; la doc actual de Orders incluye una prueba de reembolso con webhook `order.refunded`. **Verificar en S-001.**

## 8. Mapa legacy → nuevo (para `GUAZUNCHITO_MP_QR`)
| Legacy (COM / SDK Python) | Nuevo (adaptador MP) |
|---|---|
| `CreatePOS` / `create_pos` | `POST /pos` (igual) |
| `GetPOS` / `list_all_pos` | `GET /pos` (igual) |
| `CreateQR(pos, title, total, desc, ext_ref)` | `POST /v1/orders` (`title` desaparece; `external_reference` obligatorio; `total_amount` string; `expiration_time` relativo) |
| `GetQRStatus` | `GET /v1/orders/{id}` + webhook `orders` |
| `CancelQR` | `POST /v1/orders/{id}/cancel` (+ `X-Idempotency-Key`) |
| — (no existía) | `POST /v1/orders/{id}/refund` |
| Webhook `payments`/`merchant_orders` | Webhook `orders` con firma verificada |
| `LastQrPng` (PNG Base64) | Generar PNG desde `qr_data` en el backend (endpoint para el ERP) |

## 9. Preguntas que solo el sandbox responde (⚠️ → S-001)
1. Forma exacta de la respuesta de creación en modo `dynamic` (ruta de `qr_data`, ids de pago).
2. ¿De dónde salen **comisión y neto** en el mundo Orders? (¿en la orden, vía Payments `GET /v1/payments/{id}`, o solo en reportes de liquidación?) → define el módulo de conciliación.
3. ¿`external_reference` debe ser único en MP o solo lo exigimos nosotros?
4. Comportamiento exacto al vencer (`expired`) con pago en vuelo.
5. Devolución parcial: estado y `status_detail` resultantes; webhook generado.
6. Orden de llegada y duplicados reales de webhooks.
7. Formato del manifiesto de la firma frente a lo que implementa el validador del SDK de Python.

## 10. Fuentes (Mercado Pago Developers)
- Procesamiento QR (Orders): https://www.mercadopago.com.ar/developers/es/docs/qr-code/payment-processing
- Migrar desde Órdenes presenciales V2: https://www.mercadopago.com.ar/developers/es/docs/qr-code/migrate-instore-orders-v2-to-orders
- Migrar desde QR Modelo dinámico: https://www.mercadopago.com.br/developers/es/docs/qr-code/migrate-dynamic-qr-model-to-orders
- Point (Orders): https://www.mercadopago.com.ar/developers/es/docs/mp-point/payment-processing
- Notificaciones (Orders): https://www.mercadopago.com.ar/developers/es/docs/checkout-pro-orders/notifications
- Renovar Access Token (OAuth): https://www.mercadopago.com.br/developers/es/docs/security/oauth/renewal.md
- Compra de prueba QR: https://www.mercadopago.com.ar/developers/es/docs/qr-code/test-integration/test-purchase
- Crear caja (referencia): https://www.mercadopago.com.br/developers/es/reference/in-person-payments/qr-code/pos/create-pos/post
- Nota: la doc de MP menciona un **MCP server oficial** (búsqueda de documentación, configuración de webhooks, usuarios de prueba). Evaluarlo como herramienta del `integration-dev` (confirmar instalación en la doc).

## 11. No verificado en esta pasada
Notas de Payway (doble API key, montos en centavos, `site_transaction_id`) y Clover (OAuth, RAID, Pay Display API) vienen de la propuesta y **no se contrastaron** con documentación vigente. Verificar al llegar a esas fases.
