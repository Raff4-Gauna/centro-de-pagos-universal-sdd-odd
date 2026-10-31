# Notas de API — Clover (verificado 2026-10-31)

> Estado: **investigación documental, sin sandbox probado**. Confirmar en spike **S-002**
> (`specs/00-platform/spikes/S-002-payway-clover-docs.md`) antes de redactar `specs/14-clover-adapter/spec.sdd.md`.
> Fuente primaria: documentación oficial de Clover ([docs.clover.com](https://docs.clover.com/docs/rest-pay-development-basics)),
> que sigue activa y es la que hay que seguir (no está dada de baja).

## 1. Qué es "REST Pay Display" (lo que la propuesta llamaba "semi-integrada")
Clover ofrece dos caminos para integrarse con una terminal física (Flex, Mini, Compact):
- **Semi-integración vía REST Pay Display API**: el sistema del comercio (el Hub, en este caso) le dice al
  dispositivo Clover "cobrá $X", el dispositivo maneja la UI de pago (tarjeta, propina, firma) y devuelve el
  resultado. Es el modelo equivalente a "Point" de Mercado Pago.
- Integración completa dentro del propio Clover OS (apps que corren adentro del dispositivo) — **no aplica** a
  este proyecto, que necesita controlar el cobro desde un sistema externo.

## 2. Confirmado en la documentación oficial
- **OAuth 2.0 obligatorio**: hace falta un flujo OAuth para obtener un **access token + refresh token** de la
  cuenta del comercio. La documentación es explícita en que las llamadas de REST Pay Display deben hacerse con un
  **token generado por OAuth**, no con un "merchant token" — usar un merchant token devuelve error.
  [Fuente](https://docs.clover.com/docs/rest-pay-development-basics).
- **Remote Application ID (RAID)**: es un identificador que Clover genera para la *app* del desarrollador
  (distinto del Clover App ID), y es obligatorio para conectarse al dispositivo físico. Se gestiona desde la
  cuenta de desarrollador de Clover.
- **Conexión al dispositivo**: el POS (en este caso, el backend del Hub o un cliente delgado en la caja) se
  conecta al Flex/Mini/Compact por red local o a través de la nube de Clover.
- El flujo de "hacer una venta" incluye pasos documentados como tutoriales separados: *Make a sale*, *Get customer
  confirmation*, *Print a receipt*, además de páginas dedicadas a **idempotencia** ("Track transactions with
  idempotency keys") y a **reconciliación y recuperación de pagos** — ambas existen como conceptos propios de
  Clover, lo cual es una buena señal de que el adaptador puede mapearse al mismo contrato que MP (confirmar,
  cancelar, reconciliar).

## 3. Lo que no se pudo confirmar en esta pasada (⚠️ requiere S-002)
- El nombre y formato exacto de la cabecera de dispositivo (la propuesta original mencionaba
  `X-Clover-Device-Id`); no se verificó contra la referencia de API actual.
- Si la confirmación de pago llega por **webhook** (Clover sí tiene un sistema de webhooks para otros eventos,
  como cambios de inventario en apps completas) o si en REST Pay Display todo es **síncrono** (la llamada de venta
  se mantiene abierta hasta que el dispositivo resuelve el cobro). Esto cambia bastante el diseño del adaptador:
  si es síncrono, se parece más a Payway que a Mercado Pago.
- Página exacta de "Track transactions with idempotency keys": no se abrió el contenido, solo se confirmó que
  existe en el índice de la documentación.

## 4. Qué hacer antes de programar el adaptador de Clover
1. Crear cuenta de desarrollador Clover + app en modo sandbox (el checklist oficial ya lo describe paso a paso:
   cuenta global → app semi-integrada en sandbox → RAID → comercio de prueba).
2. Conseguir (o simular) un dispositivo Clover de prueba — Clover ofrece un simulador de dispositivo para
   sandbox según la documentación de "Development Basics".
3. Repetir el spike S-001 pero para Clover: una venta de prueba de punta a punta, confirmar si la respuesta es
   síncrona o por webhook, y la cabecera real del dispositivo.
4. Recién ahí pasar `specs/14-clover-adapter/spec.sdd.md` de "Futuro" a "Draft".

## Fuentes consultadas
- [REST Pay Display — Get started (docs.clover.com)](https://docs.clover.com/docs/rest-pay-development-basics)
- [Device connection (docs.clover.com)](https://docs.clover.com/dev/docs/device-connection)
- [Payments (semi) integration FAQs (docs.clover.com)](https://docs.clover.com/dev/docs/payments-semi-integration-faqs)
- [Create an app in the sandbox environment (docs.clover.com)](https://docs.clover.com/docs/creating-a-sandbox-app)
- [REST Pay Display API introduction (community.clover.com)](https://community.clover.com/questions/44597/rest-pay-display-api-introduction.html)
