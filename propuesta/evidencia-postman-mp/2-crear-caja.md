Crear caja
https://www.mercadopago.com.ar/developers/es/reference/pos/_pos/post

Postman:

1: POST : https://api.mercadopago.com/pos

2: Configura los Headers:
Key: Content-Type, Value: application/json
Key: Authorization, Value: Bearer <token de prueba de la app 5332602214240276 — retirado del repo>

3: Configura el Body:
Selecciona la pestaña "Body"
Elige la opción "raw"
En el menú desplegable, selecciona "JSON"

SOLICITUD:
{
  "name": "CAJAPOS",
  "fixed_amount": true,
  "store_id": "70772484",
  "external_store_id": "SUC001",
  "external_id": "SUC001POS001",
  "category": 621102
}


IMPORTANTE: store_id "Identificador de la sucursal a la que pertenece el punto de venta", en este caso es "70772484" creado en la sucursal anteriormente.

______________________________________________________________________________________________________________________________________________________________________

RESPUESTA:

{
    "id": 113464285,
    "qr": {
        "image": "https://www.mercadopago.com/instore/merchant/qr/113464285/ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.png",
        "template_document": "https://www.mercadopago.com/instore/merchant/qr/113464285/template_ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.pdf",
        "template_image": "https://www.mercadopago.com/instore/merchant/qr/113464285/template_ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8.png"
    },
    "status": "active",
    "date_created": "2025-05-21T19:02:42.000-04:00",
    "date_last_updated": "2025-05-21T19:02:42.000-04:00",
    "uuid": "ed3bb1fc191145e085f9b0de1d5d99c166ebc33bed5145ce9245b705c8d1d8d8",
    "user_id": 553719406,
    "name": "CAJAPOS",
    "fixed_amount": true,
    "category": 621102,
    "store_id": "70772484",
    "external_store_id": "SUC001",
    "external_id": "SUC001POS001",
    "site": "MLA",
    "qr_code": "00020101021143540016com.mercadolibre0130https://mpago.la/pos/11346428550150011204314482715204970053030325802AR5908libreria6004CABA630455BB"
}
