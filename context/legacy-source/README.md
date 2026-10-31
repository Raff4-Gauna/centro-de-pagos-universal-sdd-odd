# Código fuente del legacy (solo lectura, solo referencia)

Copia exacta de `Integración-Mp/mpqr/*.py` y `Integración-Mp/com_server/mpqr_server.py` del proyecto Python +
COM que ya tenías funcionando contra Mercado Pago (conectado a un sistema en C#/.NET). Se guarda acá como
**evidencia**, no como punto de partida: nada de este código se copia al backend nuevo.

Qué se conserva de acá (como conocimiento) y qué no: ver `context/04-legacy-guazunchito.md`.
Qué endpoints usaba y en qué migraron: ver `context/03-mercadopago-api-notes.md` y
`context/09-cuenta-sandbox-mp-datos-reales.md`.

No hay `.env` ni credenciales en esta copia — las credenciales de prueba están documentadas aparte, de forma
explícita, en `context/09-cuenta-sandbox-mp-datos-reales.md`.
