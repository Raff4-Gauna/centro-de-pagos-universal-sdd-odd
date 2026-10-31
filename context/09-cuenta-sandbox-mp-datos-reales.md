# Datos reales de la cuenta de pruebas Mercado Pago (SistemaRG)

> 🔒 **Actualizado 2026-10-31:** los valores secretos (tokens, contraseña y código del usuario de prueba) ya **no
> están en este archivo**: se movieron a `.env` (ignorado por `.gitignore`; claves en `.env.example`) y acá quedan
> como `<ver .env: NOMBRE>`. Los IDs (user, app, store, POS) no son secretos y se mantienen. Como esos valores
> estuvieron pegados en chats, **hay que rotarlos** desde "Tus integraciones" en Mercado Pago Developers y
> actualizar `.env`. Ver `context/worklog/2026-10-31-repo-bootstrap.md`.

## 1. Aplicación
| Campo | Valor |
|---|---|
| Nombre de la app | SistemaRG |
| User ID (vendedor) | `553719406` |
| Número de aplicación | `5332602214240276` |
| Integración | Código QR, modelo **dinámico** |
| País | Argentina |
| Creada | 20/05/2025 |
| Public Key (test) | `<ver .env: MP_TEST_PUBLIC_KEY>` |
| Access Token (test) | `<ver .env: MP_TEST_ACCESS_TOKEN>` |
| Usuario de prueba (comprador) | `TESTUSER1064981229` |
| Webhooks configurados | Ninguno todavía (hay que crear uno para el tópico **`orders`**, no el que menciona el legacy) |

## 2. Sucursal (Store) real creada
`GET https://api.mercadopago.com/stores/70772484`

```json
{
  "id": "70772484",
  "name": "SucursalRG",
  "date_creation": "2025-05-21T18:42:07.971Z",
  "business_hours": {
    "monday": [{ "open": "08:00", "close": "12:00" }],
    "tuesday": [{ "open": "09:00", "close": "18:00" }]
  },
  "location": {
    "address_line": "Independencia 0123, Resistencia, Chaco, Argentina",
    "reference": "Mercado Pago",
    "latitude": -34.603722,
    "longitude": -58.381592,
    "id": "AR-C", "type": "state", "city": "Resistencia",
    "state_id": "AR-C", "zip_code": "C1007XAP"
  },
  "external_id": "SUC001",
  "status": "active",
  "user_id": 553719406,
  "site_id": "MLA",
  "open_hours": "24 hrs."
}
```

⚠️ **Ojo:** la latitud/longitud (`-34.603722, -58.381592`) corresponden a **Buenos Aires**, no a Resistencia,
Chaco. Es un dato de prueba inconsistente — en producción, `RN-MP-12` exige ubicación real y completa antes de
llamar a Mercado Pago. No reutilizar esta sucursal como plantilla de producción tal cual.

## 3. Caja (POS) real creada
`GET https://api.mercadopago.com/pos?external_id=SUC001POS001`

```json
{
  "user_id": 553719406,
  "name": "CAJAPOS",
  "fixed_amount": true,
  "category": 621102,
  "store_id": "70772484",
  "external_id": "SUC001POS001",
  "id": 113464285,
  "qr": {
    "image": "https://www.mercadopago.com/instore/merchant/qr/113464285/ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.png",
    "template_document": "https://www.mercadopago.com/instore/merchant/qr/113464285/template_ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.pdf",
    "template_image": "https://www.mercadopago.com/instore/merchant/qr/113464285/template_ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.png"
  },
  "date_created": "2025-05-21T19:02:42.000-04:00",
  "date_last_updated": "2025-05-21T19:02:42.000-04:00",
  "external_store_id": "SUC001",
  "qr_code": "00020101021143540016com.mercadolibre0130https://mpago.la/pos/11346428550150011204314482715204970053030325802AR5908libreria6004CABA630455BB"
}
```

Esta caja (`external_id: SUC001POS001`, `mp_pos_id: 113464285`) es el **QR estático de la caja** (vive en
`/pos`), distinto del **QR dinámico por cobro** que genera la Orders API (`qr_data` de cada orden). El Hub usa
ambos conceptos: la caja (fija, se crea una vez) y la orden (una por cobro).

## 4. Comandos de referencia que ya funcionaban (APIs que siguen vigentes)
Estos tres endpoints (`/stores`, `/pos`) **no cambiaron** y se pueden seguir usando tal cual en el adaptador
nuevo — es el endpoint de **crear la orden de cobro** el que migra a Orders API (ver
`context/03-mercadopago-api-notes.md` y `context/04-legacy-guazunchito.md`).

```bash
# Crear una caja
curl -X POST "https://api.mercadopago.com/pos?access_token=$MP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Caja PB","external_id":"VGMDIS"}'

# Crear una sucursal (requiere "location" con ubicación real — RN-MP-12)
curl -X POST "https://api.mercadopago.com/users/553719406/stores" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MP_ACCESS_TOKEN" \
  -d '{
    "name": "SucursalRG",
    "business_hours": {
      "monday": [{"open": "08:00", "close": "12:00"}],
      "tuesday": [{"open": "09:00", "close": "18:00"}]
    },
    "external_id": "SUC001",
    "location": {
      "street_number": "0123",
      "street_name": "Independencia",
      "city_name": "Resistencia",
      "state_name": "Chaco",
      "latitude": -34.603722,
      "longitude": -58.381592,
      "reference": "Mercado Pago"
    }
  }'

# Obtener una sucursal específica
curl -X GET "https://api.mercadopago.com/stores/70772484" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MP_ACCESS_TOKEN"

# Listar todas las tiendas / buscar tiendas de un usuario
curl -X GET "https://api.mercadopago.com/stores?access_token=$MP_ACCESS_TOKEN"
curl -X GET "https://api.mercadopago.com/users/553719406/stores/search?access_token=$MP_ACCESS_TOKEN"

# Crear un punto de venta para una tienda específica
curl -X POST "https://api.mercadopago.com/pos?access_token=$MP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Caja PB","external_id":"PBTEST","store_id":70044176}'
```

Lo que **no** se reutiliza del legacy es el endpoint de creación de orden QR (ver
`context/04-legacy-guazunchito.md`, hallazgo resuelto): había que migrarlo a `POST /v1/orders` igual, y eso ya
está especificado en `specs/05-mercadopago-adapter/spec.sdd.md`.

## 5. Estructura del proyecto legacy (para referencia, no se migra código)
```
Integración-Mp/
├── .env                        # credenciales — nunca se migran como archivo, solo el conocimiento
├── com_server/
│   └── mpqr_server.py          # servidor COM (Windows) — no se traslada (ver context/04)
├── mpqr/
│   ├── __init__.py
│   ├── config.py                # lectura de .env
│   ├── const.py                 # endpoints legacy (confirmaron la migración a Orders)
│   ├── db_config.py             # SQL Server vía pyodbc, config y logs en BD
│   ├── http_client.py           # cliente HTTP con token desde BD
│   ├── pos_client.py            # alta/consulta de sucursal y caja (patrón reutilizable)
│   ├── qr_client.py             # creación/consulta/cancelación de orden QR (legacy, a migrar)
│   └── webhook.py               # procesamiento de notificaciones (tópicos legacy, a migrar)
├── doc_postman/
├── webhook_server.py / webhook_server_32.py   # servidor local con ngrok — solo desarrollo
├── registerCOM.bat / unregisterCOM.bat        # alta/baja del servidor COM en Windows
├── test_db.py / test_db_conexion.py / test_integration.py / test_payment_status.py
├── requirements.txt
└── README.md
```

## 6. Próximo paso concreto
Con esta cuenta de pruebas ya armada (sucursal + caja reales), el **spike S-001**
(`specs/00-platform/spikes/S-001-mp-sandbox.md`) se puede ejecutar directo, sin paso previo de alta de sucursal/
caja: solo falta crear el webhook de la aplicación (tópico `orders`) y correr una orden real con
`POST /v1/orders` usando `external_pos_id: "SUC001POS001"`.

## 7. Segundo set de credenciales (panel "Tus integraciones", 2026-10-31)

> 🔒 Igual que la sección 1: los valores viven solo en `.env`; como quedaron pegados en un chat, **rotalos** antes
> de usarlos en serio.

El usuario pegó una captura más reciente del panel de Mercado Pago, app **SistemaRG**, integración **Código QR /
modelo dinámico**, con estos valores:

| Campo | Valor |
|---|---|
| País de operación | Argentina |
| Public Key (prueba) | `<ver .env: MP_TESTUSER_PUBLIC_KEY>` |
| Access Token (prueba) | `<ver .env: MP_TESTUSER_ACCESS_TOKEN>` |
| N.º de la aplicación (mostrado en este panel) | `5469141309261729` |
| User ID (mostrado en este panel) | `2452338094` |
| Usuario de prueba | `TESTUSER1064981229` |
| Contraseña | `<ver .env: MP_TESTUSER_PASSWORD>` |
| Código de verificación | `<ver .env: MP_TESTUSER_VERIFICATION_CODE>` |

**Reconciliación con la sección 1 (hallazgo, no una contradicción grave):**
- La **sucursal** (`SucursalRG`, Independencia 0123, Resistencia, Chaco) y la **caja** (`CAJAPOS`) que muestra
  este panel son **las mismas** que ya están documentadas en §2/§3 — confirma que es el mismo negocio de prueba.
- Lo que **no coincide** con la sección 1 es el formato y el número: acá el token usa el prefijo **`APP_USR-`**
  (formato de credencial "real"/de usuario de prueba logueado) en vez de **`TEST-…`** (formato de "credenciales
  de prueba" clásicas de la app), y el número de aplicación/usuario también difiere (`5469141309261729` /
  `2452338094` acá vs `5332602214240276` / `553719406` en §1). Esto es consistente con cómo Mercado Pago expone
  dos caminos de prueba distintos (credenciales de prueba de la app vs. iniciar sesión como el **usuario de
  prueba vendedor**): no se asumió cuál es cuál sin confirmarlo.
- **Antes de ejecutar S-001 con estas credenciales**: confirmar en el panel de Mercado Pago Developers cuál de
  los dos tokens (§1 o §7) es el vigente/recomendado hoy para probar la Orders API, porque pueden pertenecer a
  dos "identidades de prueba" distintas aunque operen sobre la misma sucursal/caja. Si surge una duda de negocio
  sobre cuál usar, se anota como `Q-0xx` en `specs/00-platform/clarifications.md` antes de que el spike corra.

## 8. Dato de contexto: NO es el "Inicio" ni la "Configuración" del Hub
El usuario también adjuntó capturas del **panel propio de Mercado Pago** (saldo en pesos/dólares, inversiones,
transferencias, actividad, y el menú de Cuenta/Negocio). Eso es la billetera y el panel **de Mercado Pago como
entidad financiera**, no una referencia a copiar para el Hub: el Hub no es un adquirente ni mueve saldo propio
(`context/00-project-brief.md §4`, "Fuera del MVP: Ser adquirente"). Lo único que se usa de esas capturas es la
**estructura de secciones** (Cuenta, Seguridad, Colaboradores, Negocio, Locales y cajas, Integraciones…) como
inspiración para diseñar el equivalente del Hub — eso se especifica en
`context/07-frontend-ui-guidelines.md §5` ("Inicio" y "Configuración" del Hub), que deja explícito qué se adapta
y qué no.
