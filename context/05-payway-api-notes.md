# Notas de API — Payway (verificado 2026-10-31)

> Estado: **investigación documental, sin sandbox probado**. No confundir con `context/03-mercadopago-api-notes.md`,
> que sí está verificado contra la cuenta real. Todo lo marcado ⚠️ se confirma en el spike **S-002**
> (`specs/00-platform/spikes/S-002-payway-clover-docs.md`) antes de redactar `specs/13-payway-adapter/spec.sdd.md`.

## 1. Qué es Payway en este proyecto
Payway es la marca comercial en Argentina del gateway que internacionalmente se conoce como **Decidir** (Grupo
Banco Galicia / Prisma). La propuesta original ya lo señalaba como "ex Decidir": son el mismo producto, y buena
parte de la documentación pública en inglés vive bajo el nombre "Decidir" o "Decidir Plus". [Fuente: Decidir Plus
gateway guide](https://developer.spreedly.com/docs/decidir-plus-gateway-guide).

## 2. Autenticación (confirmado en documentación de terceros)
- El gateway se configura con un par de claves: **`public_key`** (se usa para tokenizar la tarjeta desde el
  cliente/checkout) y **`private_key`** (se usa server-to-server para confirmar/capturar la venta). Esto coincide
  con lo que ya describía la propuesta original.
- La tokenización de la tarjeta **no es responsabilidad del backend del Hub**: la tarjeta se tokeniza del lado del
  cliente (JS del checkout de Payway/Decidir, o un proveedor intermedio) y el backend solo recibe y reenvía el
  **token** ya emitido. Esto es una diferencia de diseño importante respecto a Mercado Pago: el Hub **nunca ve el
  número de tarjeta**, ni siquiera de paso.

## 3. Lo que no pudimos confirmar documentalmente (⚠️ requiere S-002)
- Formato exacto del monto (centavos enteros vs. decimal) — la propuesta original decía "centavos, enteros"; no
  encontramos una fuente primaria de Payway Argentina (solo ejemplos de terceros con otra moneda) que lo confirme
  byte a byte.
- Mecanismo real de idempotencia. La propuesta asumía `site_transaction_id` como ancla de idempotencia, pero la
  documentación de terceros solo lo describe como "identificador del sitio/comercio para la transacción", no como
  una idempotency key garantizada por el servidor. Hay que confirmarlo contra la documentación oficial de
  `developers.decidir.com` (Argentina) o `payway.com.ar`, con cuenta de pruebas propia.
- Mecanismo de notificación asíncrona (¿hay webhooks, o todo es síncrono request/response en la confirmación de
  venta?). No encontramos evidencia de un webhook propio de Payway para QR/POS; es posible que, a diferencia de
  Mercado Pago, el flujo sea mayormente síncrono (se cobra y se confirma en la misma llamada) con reintentos de
  consulta de estado por `site_transaction_id`.
- Terminal física: si el Hub va a cobrar con posnet/POS físico Payway (no solo tarjeta tokenizada vía checkout
  web), hace falta el SDK o protocolo del dispositivo, que no es el mismo mecanismo que la tokenización web.

## 4. Supuesto de diseño mientras no se confirme S-002
El `PaywayAdapter` (módulo 13, fase 9 del roadmap) **no se diseña en detalle todavía**. Lo único que ya se puede
fijar en la Constitución del motor (`SPEC-03`) es que el contrato común (`BaseAdapter`) no puede asumir "todo es
asíncrono como MP": debe soportar tanto un flujo que confirma en la misma llamada (Payway) como uno que confirma
por webhook/poller (Mercado Pago). Esto ya está contemplado en el diseño de capacidades (`capabilities.md`).

## 5. Qué hacer antes de programar el adaptador de Payway
1. Crear cuenta de pruebas en Payway/Decidir Argentina (`developers.decidir.com` o el portal que indique Payway
   comercial) — requiere gestión comercial, no es autoservicio como Mercado Pago.
2. Repetir el spike S-001 pero para Payway: una venta real en sandbox, inspeccionar el payload completo de
   respuesta (dónde vienen comisión/neto si es que vienen), confirmar formato de monto e idempotencia.
3. Recién ahí pasar `specs/13-payway-adapter/spec.sdd.md` de "Futuro" a "Draft".

## Fuentes consultadas
- [Decidir Plus gateway guide (Spreedly)](https://developer.spreedly.com/docs/decidir-plus-gateway-guide)
- [Decidir Plus fact sheet (Spreedly)](https://developer.spreedly.com/docs/decidir-plus-factsheet)
- [Decidir fact sheet (Spreedly)](https://developer.spreedly.com/docs/decidir-factsheet)
- SDK oficial: [`decidir/sdk-java-v2`](https://github.com/decidir/sdk-java-v2) (confirma la existencia de un SDK
  mantenido por Decidir; no se inspeccionó el código en este análisis)
