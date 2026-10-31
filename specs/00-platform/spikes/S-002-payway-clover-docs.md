# S-002 — Spike: cuentas de prueba y confirmación documental Payway + Clover

- **Nivel ODD:** O2 (exploración)
- **Timebox:** 1 jornada por proveedor (2 en total). Se corta y se documenta qué falta si no alcanza.
- **Resultado esperado:** conocimiento + fixtures, igual que S-001. **No es código mergeable.**
- **Alimenta:** `context/05-payway-api-notes.md`, `context/06-clover-api-notes.md`, y habilita redactar
  `specs/13-payway-adapter/spec.sdd.md` y `specs/14-clover-adapter/spec.sdd.md` (hoy "Futuro").
- **Prerrequisito:** este spike es de **Fase 9/10** del roadmap (después del MVP de Mercado Pago). No bloquea
  nada del camino a H2/H3. Se deja escrito ahora para no repetir el trabajo de investigación hecho en esta sesión.
- **Actualización 2026-10-31 (Clover):** la cuenta de desarrollador, la app sandbox (`AppCloverGR`) y el RAID ya
  están creados — ver `context/10-clover-cuenta-sandbox-real.md`. Los pasos 1 (cuenta/app/RAID) de la sección
  "Pasos — Clover" de abajo ya están hechos; falta ejecutar los pasos 2–5 (dispositivo/simulador, venta de punta
  a punta, cancelación/devolución) cuando se priorice la Fase 10. Payway sigue sin cuenta de prueba propia.

## Por qué hace falta (a diferencia de Mercado Pago)
Con Mercado Pago, `context/03-mercadopago-api-notes.md` está verificado contra una cuenta real (la del usuario,
con sucursal y caja ya creadas). Con Payway y Clover solo se llegó a documentación pública de terceros y
checklists oficiales — ver `context/05-payway-api-notes.md` y `context/06-clover-api-notes.md` para el detalle de
qué quedó confirmado y qué no. Antes de diseñar esos adaptadores en serio hace falta repetir el mismo ejercicio
que S-001: cuenta de pruebas propia, una venta real, inspección del payload completo.

## Pasos — Payway
1. Gestionar cuenta de pruebas (`developers.decidir.com` o el canal comercial de Payway Argentina).
2. Tokenizar una tarjeta de prueba desde un checkout mínimo (HTML+JS descartable) con la `public_key`.
3. Confirmar la venta server-to-server con la `private_key` y guardar el payload completo.
4. Confirmar: formato del monto (¿centavos enteros?), si `site_transaction_id` realmente actúa como idempotency
   key ante un reintento con el mismo valor, y si existe algún mecanismo de notificación asíncrona o todo es
   síncrono.
5. Probar un rechazo (tarjeta de prueba que rechaza) y una devolución.

## Pasos — Clover
1. Completar el checklist oficial: cuenta de desarrollador global → app semi-integrada en sandbox → generar RAID
   → comercio de prueba. ([Fuente](https://docs.clover.com/docs/creating-a-sandbox-app))
2. Conectar contra un dispositivo de prueba o simulador (confirmar si Clover sandbox ofrece un simulador sin
   hardware físico).
3. Seguir el tutorial oficial "Make a sale" de punta a punta y guardar el payload completo de request/response.
4. Confirmar: nombre real de la cabecera de dispositivo, si la confirmación de pago es síncrona (la llamada queda
   abierta hasta que el dispositivo resuelve) o llega por evento aparte, y cómo funciona la idempotencia que
   menciona la documentación ("Track transactions with idempotency keys").
5. Probar cancelación y devolución si el sandbox lo permite.

## Entregables
- [ ] Fixtures JSON sanitizadas (sin claves) → `backend/apps/integrations/providers/payway/fixtures/` y
      `.../clover/fixtures/`.
- [ ] Actualizar `context/05-payway-api-notes.md` y `context/06-clover-api-notes.md`: mover cada ⚠️ a confirmado,
      con fecha y fuente (respuesta real, no documentación de terceros).
- [ ] Decidir si el `BaseAdapter` (SPEC-03) necesita ajustes para soportar confirmación síncrona (si resulta que
      Payway y/o Clover confirman en la misma llamada, a diferencia del modelo asíncrono de MP).

## Reglas del spike
Las mismas que S-001: nada de claves en el repo ni en las notas; cada hallazgo con fecha y fuente.
