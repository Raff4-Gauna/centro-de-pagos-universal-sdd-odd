# mpqr/const.py
BASE_URL = "https://api.mercadopago.com"

# --- POS ----------------------------------------------------
URL_CREATE_POS   = "/pos"
URL_GET_POS      = "/pos"
URL_LIST_POS     = "/pos"

# --- QR dinámico -------------------------------------------
URL_CREATE_ORDER = (
    "/instore/orders/qr/seller/collectors/{user_id}/"
    "pos/{external_pos_id}/qrs"
)                                  # PUT   ✔ crea orden + devuelve qr_data
                                  # POST  ✔ obtiene qr_data después del PUT
                                  # DELETE ✔ cancela orden (mismo endpoint)

URL_GET_ORDER    = (
    "/instore/qr/seller/collectors/{user_id}/"
    "pos/{external_pos_id}/orders"
)                                  # GET   ✔ consulta estado (solo antes del pago)

# --- Payments API (para consultar pagos procesados) -------
URL_SEARCH_PAYMENTS = "/v1/payments/search"          # GET ✔ buscar pago por external_reference
URL_GET_PAYMENT     = "/v1/payments/{payment_id}"    # GET ✔ obtener detalles del pago por ID

# Para compatibilidad hacia atrás (ya no se usa directamente)
URL_CANCEL_ORDER = URL_CREATE_ORDER  # Same endpoint, different method
URL_GET_QR_DATA = URL_CREATE_ORDER   # Same endpoint, different method