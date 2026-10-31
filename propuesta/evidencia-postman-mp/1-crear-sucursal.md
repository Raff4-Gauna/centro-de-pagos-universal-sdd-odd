
Crear sucursal:
https://www.mercadopago.com.ar/developers/es/reference/stores/_users_user_id_stores/post

IMPORTANTE: location object REQUERIDO "Si o si se ve pasar lugar real de localizacion y no falso".

Postman:

1: POST : https://api.mercadopago.com/users/553719406/stores

2: Configura los Headers:
Key: Content-Type, Value: application/json
Key: Authorization, Value: Bearer <ver .env: MP_TEST_ACCESS_TOKEN>

3: Configura el Body:
Selecciona la pestaña "Body"
Elige la opción "raw"
En el menú desplegable, selecciona "JSON"

SOLICITUD:
{
  "name": "SucursalRG",
  "business_hours": {
    "monday": [
      {
        "open": "08:00",
        "close": "12:00"
      }
    ],
    "tuesday": [
      {
        "open": "09:00",
        "close": "18:00"
      }
    ]
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
}


______________________________________________________________________________________________________________________________________________________________________

RESPUESTA:

{
    "id": "70772484",
    "name": "SucursalRG",
    "date_creation": "2025-05-21T18:42:07.971Z",
    "business_hours": {
        "monday": [
            {
                "open": "08:00",
                "close": "12:00"
            }
        ],
        "tuesday": [
            {
                "open": "09:00",
                "close": "18:00"
            }
        ]
    },
    "location": {
        "address_line": "Independencia 0123, Resistencia, Chaco, Argentina",
        "reference": "Mercado Pago",
        "latitude": -34.603722,
        "longitude": -58.381592,
        "id": "AR-C",
        "type": "state",
        "city": "Resistencia",
        "state_id": "AR-C",
        "zip_code": "C1007XAP"
    },
    "external_id": "SUC001"
}