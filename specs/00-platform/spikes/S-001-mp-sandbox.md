# S-001 — Spike: Mercado Pago sandbox (Orders API)

- **Nivel ODD:** O2 (exploración)
- **Timebox:** 1 jornada. Si no alcanza, se corta y se documenta qué falta.
- **Resultado esperado:** conocimiento + fixtures. **No es código mergeable** (script descartable en `/tmp` o rama de spike).
- **Alimenta:** specs 05, 07, 08 y preguntas Q-015, Q-016.

## Preparación
- [ ] App en "Tus integraciones" con solución de pagos presenciales (QR).
- [ ] Cuentas de prueba: vendedor (Argentina) y comprador; credenciales de prueba `APP_USR-…`.
- [ ] URL pública para webhooks (túnel de desarrollo) configurada en el tópico **Order (Mercado Pago)**; anotar la clave secreta.
- [ ] Postman o script mínimo con `requests` (sin SDK propio).

## Pasos
1. Crear **sucursal** y **caja** de prueba (`POST /users/{id}/stores`, `POST /pos`). Guardar respuestas.
2. Crear **orden QR dinámica** (`POST /v1/orders`, `X-Idempotency-Key`). Guardar request/response.
3. Repetir el POST con la **misma clave** (mismo body) y luego con body distinto → anotar respuestas.
4. Pagar con el comprador de prueba (tarjeta aprobada) → capturar **webhook completo** (headers, query, body).
5. `GET /v1/orders/{id}` antes y después del pago.
6. Pagar con tarjeta que **rechaza** → ¿qué ve la orden? ¿llega webhook?
7. Dejar **vencer** una orden (`PT30S`) y también pagar justo al límite.
8. **Cancelar** una orden `created`; intentar cancelar una `processed`.
9. **Devolución total** y **parcial** → estados, `status_detail`, webhooks.
10. Validar la **firma** con el validador del SDK oficial de Python y con cálculo manual; anotar el manifiesto.
11. Buscar **comisión y neto**: respuesta de la orden, `GET /v1/payments/{id}` si existe, reportes.
12. Probar **`external_reference` repetido** en dos órdenes.
13. Generar el **PNG** desde `qr_data` y escanearlo con la app.

## Entregables
- [ ] Fixtures JSON **sanitizadas** (sin tokens, sin PII) → `backend/apps/integrations/providers/mercadopago/fixtures/`.
- [ ] Tabla "documentado vs real" en `context/03-mercadopago-api-notes.md` (sección 9 resuelta).
- [ ] Respuestas a Q-015 (URL de webhook), Q-016 (comisión/neto), Q-017 (rechazos QR).
- [ ] Lista de sorpresas y su impacto en las specs 05, 06, 07, 08.

## Reglas del spike
- Nada de tokens en el repo ni en las notas. Si se filtra uno: revocarlo.
- Cada hallazgo se anota con fecha y fuente (respuesta real o documentación).
