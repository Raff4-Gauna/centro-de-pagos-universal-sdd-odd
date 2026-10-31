# # mpqr/qr_client.py
# import json, uuid, logging, base64
# from datetime import datetime, timedelta
# from typing import Dict, Any, Optional
# from .http_client import HTTPClient
# from .db_config import get_db_config
# from .config import get
# from .const import (
#     URL_CREATE_ORDER, URL_GET_ORDER, URL_CANCEL_ORDER, URL_GET_QR_DATA,
#     URL_SEARCH_PAYMENTS, URL_GET_PAYMENT
# )

# log = logging.getLogger("mpqr.qr")

# class QRClient(HTTPClient):
#     def __init__(self):
#         super().__init__()
#         self.db = get_db_config()
    
#     def create_order(self, external_pos_id: str, title: str, total_amount: float, 
#                     description: str = None, external_reference: str = None):
#         """
#         Crea una orden QR dinámica
        
#         Args:
#             external_pos_id: ID del POS donde se procesará
#             title: Título del producto/servicio
#             total_amount: Monto total de la orden
#             description: Descripción opcional
#             external_reference: Referencia externa opcional
#         """
#         try:
#             user_id = self.db.get_config("USER_ID")
#             if not user_id:
#                 raise ValueError("USER_ID no encontrado en variables de entorno")
            
#             # Generar IDs únicos si no se proporcionan
#             if not external_reference:
#                 external_reference = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            
#             # URL con parámetros
#             url = URL_CREATE_ORDER.format(
#                 user_id=user_id,
#                 external_pos_id=external_pos_id
#             )
            
#             # Cuerpo de la petición con TODOS los campos requeridos
#             body = {
#                 "external_reference": external_reference,
#                 "title": title,
#                 "description": description or title,
#                 "notification_url": self.db.get_config("WEBHOOK_URL"),
#                 "expiration_date": self._get_expiration_date(),
#                 "total_amount": total_amount,
#                 "items": [
#                     {
#                         "sku_number": external_reference,
#                         "category": "marketplace",
#                         "title": title,
#                         "description": description or title,
#                         "unit_price": total_amount,
#                         "quantity": 1,
#                         "unit_measure": "unit",  
#                         "total_amount": total_amount
#                     }
#                 ]
#             }
            
#             log.debug("Creando orden QR: %s", json.dumps(body, indent=2))
            
#             # PUT para crear la orden
#             order_response = self._request("PUT", url, json=body)
#             log.info("Orden creada: %s", external_reference)
            
#             # POST para obtener QR data
#             qr_data_response = self._request("POST", url, json=body)
            
#             # Generar PNG del QR (opcional)
#             qr_png_b64 = None
#             if qr_data_response.get("qr_data"):
#                 qr_png_b64 = self._generate_qr_png(qr_data_response["qr_data"])
            
#             return {
#                 "order_id": external_reference,
#                 "qr_data": qr_data_response.get("qr_data"),
#                 "qr_png_b64": qr_png_b64,
#                 "order_info": order_response
#             }
            
#         except Exception as e:
#             log.error("Error creando orden QR: %s", str(e))
#             raise
    
#     def get_order_status(self, external_pos_id: str, external_reference: str = None):
#         """
#         Consulta el estado de una orden usando el flujo correcto:
#         1. Primero intenta consultar como orden QR (antes del pago)
#         2. Si no encuentra, busca como pago procesado (después del pago)
        
#         Args:
#             external_pos_id: ID del POS
#             external_reference: Referencia externa de la orden
            
#         Returns:
#             dict: Estado de la orden/pago con información unificada
#         """
#         try:
#             # PASO 1: Intentar consultar como orden QR (estado pre-pago)
#             try:
#                 qr_order_result = self._get_qr_order(external_pos_id, external_reference)
#                 if qr_order_result:
#                     log.info("Orden encontrada en estado QR: %s", external_reference)
#                     return {
#                         "status": "pending",
#                         "source": "qr_order",
#                         "data": qr_order_result,
#                         "external_reference": external_reference
#                     }
#             except Exception as qr_error:
#                 log.debug("No encontrada como orden QR: %s", str(qr_error))
            
#             # PASO 2: Buscar como pago procesado usando Payments API
#             payment_result = self._get_processed_payment(external_reference)
#             if payment_result:
#                 log.info("Pago procesado encontrado: %s", external_reference)
#                 return {
#                     "status": payment_result.get("status", "unknown"),
#                     "source": "payment",
#                     "data": payment_result,
#                     "external_reference": external_reference,
#                     "payment_id": payment_result.get("id"),
#                     "amount": payment_result.get("transaction_amount"),
#                     "currency": payment_result.get("currency_id"),
#                     "date_created": payment_result.get("date_created"),
#                     "date_approved": payment_result.get("date_approved")
#                 }
            
#             # PASO 3: No encontrado en ningún lado
#             log.warning("Orden/Pago no encontrado: %s", external_reference)
#             return {
#                 "status": "not_found",
#                 "source": "none",
#                 "external_reference": external_reference,
#                 "error": "Orden no encontrada en QR ni en pagos procesados"
#             }
            
#         except Exception as e:
#             log.error("Error consultando estado de orden: %s", str(e))
#             raise
    
#     def _get_qr_order(self, external_pos_id: str, external_reference: str = None):
#         """
#         Consulta el estado de una orden QR (método original)
#         Solo funciona ANTES de que se procese el pago
#         """
#         user_id = self.db.get_config("USER_ID")
#         url = URL_GET_ORDER.format(
#             user_id=user_id,
#             external_pos_id=external_pos_id
#         )
        
#         params = {}
#         if external_reference:
#             params["external_reference"] = external_reference
        
#         response = self._request("GET", url, params=params)
#         return response
    
#     def _get_processed_payment(self, external_reference: str):
#         """
#         Busca un pago procesado usando la Payments API
#         Funciona DESPUÉS de que se procese el pago
        
#         Args:
#             external_reference: Referencia externa para buscar
            
#         Returns:
#             dict: Información del pago si se encuentra, None si no
#         """
#         try:
#             # PASO 1: Buscar pagos por external_reference
#             params = {
#                 "external_reference": external_reference,
#                 "limit": 10  # Limitar resultados
#             }
            
#             log.debug("Buscando pago con external_reference: %s", external_reference)
#             search_response = self._request("GET", URL_SEARCH_PAYMENTS, params=params)
            
#             # Verificar si encontramos resultados
#             results = search_response.get("results", [])
#             if not results:
#                 log.debug("No se encontraron pagos para external_reference: %s", external_reference)
#                 return None
            
#             # PASO 2: Tomar el primer resultado (más reciente)
#             payment_summary = results[0]
#             payment_id = payment_summary.get("id")
            
#             if not payment_id:
#                 log.warning("Payment ID no encontrado en resultados de búsqueda")
#                 return payment_summary  # Devolver lo que tengamos
            
#             # PASO 3: Obtener detalles completos del pago
#             log.debug("Obteniendo detalles del pago ID: %s", payment_id)
#             payment_url = URL_GET_PAYMENT.format(payment_id=payment_id)
#             payment_details = self._request("GET", payment_url)
            
#             log.info("Pago encontrado - ID: %s, Status: %s, Amount: %s", 
#                     payment_id, 
#                     payment_details.get("status"), 
#                     payment_details.get("transaction_amount"))
            
#             return payment_details
            
#         except Exception as e:
#             log.error("Error buscando pago procesado: %s", str(e))
#             # Si falla la búsqueda detallada, puede ser que el pago no exista
#             return None
    
#     # Método de compatibilidad hacia atrás
#     def get_order(self, external_pos_id: str, external_reference: str = None):
#         """
#         Método de compatibilidad - usa la nueva lógica mejorada
#         """
#         return self.get_order_status(external_pos_id, external_reference)
    
#     def cancel_order(self, external_pos_id: str, external_reference: str):
#         """
#         Cancela una orden existente (método correcto para QR dinámico)
#         """
#         try:
#             user_id = self.db.get_config("USER_ID")
            
#             # Para QR dinámico, usar el endpoint correcto
#             url = URL_CREATE_ORDER.format(
#                 user_id=user_id,
#                 external_pos_id=external_pos_id
#             )
            
#             # Cuerpo para cancelación
#             body = {
#                 "external_reference": external_reference
#             }
            
#             # Usar DELETE en el endpoint de creación, no en orders
#             response = self._request("DELETE", url, json=body)
#             log.info("Orden cancelada: %s", external_reference)
#             return response
            
#         except Exception as e:
#             log.error("Error cancelando orden: %s", str(e))
#             # Si falla la cancelación, intentar método alternativo
#             return self._alternative_cancel(external_pos_id, external_reference)
    
#     def _alternative_cancel(self, external_pos_id: str, external_reference: str):
#         """
#         Método alternativo para cancelar orden (crear nueva orden con monto 0)
#         """
#         try:
#             log.warning("Intentando cancelación alternativa para: %s", external_reference)
            
#             # Crear una orden de "cancelación" con monto 0
#             cancel_result = self.create_order(
#                 external_pos_id=external_pos_id,
#                 title=f"CANCELACION-{external_reference}",
#                 total_amount=0.01,  # Monto mínimo
#                 description=f"Cancelación de orden {external_reference}",
#                 external_reference=f"CANCEL-{external_reference}"
#             )
            
#             log.info("Orden de cancelación creada: %s", cancel_result["order_id"])
#             return {"status": "cancelled_alternative", "cancel_order": cancel_result}
            
#         except Exception as alt_e:
#             log.error("Error en cancelación alternativa: %s", str(alt_e))
#             # Si todo falla, al menos informar que la orden original sigue activa
#             return {"status": "cancellation_failed", "message": "La orden permanece activa"}
    
#     def expire_order(self, external_pos_id: str, external_reference: str):
#         """
#         Método más directo: modificar la orden para que expire inmediatamente
#         """
#         try:
#             user_id = self.db.get_config("USER_ID")
#             url = URL_CREATE_ORDER.format(
#                 user_id=user_id,
#                 external_pos_id=external_pos_id
#             )
            
#             # Obtener la orden actual
#             current_order = self.get_order(external_pos_id, external_reference)
            
#             if current_order:
#                 # Actualizar con fecha de expiración pasada
#                 from datetime import datetime, timedelta
#                 expired_date = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "-03:00"
                
#                 body = current_order.copy()
#                 body["expiration_date"] = expired_date
                
#                 response = self._request("PUT", url, json=body)
#                 log.info("Orden expirada: %s", external_reference)
#                 return response
            
#         except Exception as e:
#             log.error("Error expirando orden: %s", str(e))
#             raise
    
#     def _get_expiration_date(self):
#         """
#         Genera fecha de expiración para la orden
#         """
#         from datetime import datetime, timedelta
#         expiration_min = int(self.db.get_config("EXPIRATION_MIN", "15"))
#         expiration = datetime.now() + timedelta(minutes=expiration_min)
#         return expiration.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "-03:00"
    
#     def _generate_qr_png(self, qr_data: str):
#         """
#         Genera imagen PNG del código QR (requiere qrcode y PIL)
#         """
#         try:
#             import qrcode
#             from io import BytesIO
            
#             qr = qrcode.QRCode(
#                 version=1,
#                 error_correction=qrcode.constants.ERROR_CORRECT_L,
#                 box_size=10,
#                 border=4,
#             )
#             qr.add_data(qr_data)
#             qr.make(fit=True)
            
#             img = qr.make_image(fill_color="black", back_color="white")
            
#             # Convertir a base64
#             buffer = BytesIO()
#             img.save(buffer, format="PNG")
#             img_b64 = base64.b64encode(buffer.getvalue()).decode()
            
#             return img_b64
            
#         except ImportError:
#             log.warning("qrcode no instalado, no se puede generar PNG")
#             return None
#         except Exception as e:
#             log.error("Error generando QR PNG: %s", str(e))
#             return None



# mpqr/qr_client.py - VERSIÓN MEJORADA CON PERSISTENCIA
import json, uuid, logging, base64
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .http_client import HTTPClient
from .db_config import get_db_config
from .config import get
from .const import (
    URL_CREATE_ORDER, URL_GET_ORDER, URL_CANCEL_ORDER, URL_GET_QR_DATA,
    URL_SEARCH_PAYMENTS, URL_GET_PAYMENT
)

log = logging.getLogger("mpqr.qr")

class QRClient(HTTPClient):
    def __init__(self):
        super().__init__()
        self.db = get_db_config()
    
    def create_order(self, external_pos_id: str, title: str, total_amount: float, 
                    description: str = None, external_reference: str = None,
                    expiration_minutes: int = None) -> Dict[str, Any]:
        """
        Crea una orden QR dinámica y la persiste en base de datos
        
        Args:
            external_pos_id: ID del POS donde se procesará
            title: Título del producto/servicio
            total_amount: Monto total de la orden
            description: Descripción opcional
            external_reference: Referencia externa opcional
            expiration_minutes: Minutos de expiración (opcional)
        """
        try:
            # Validar POS existe en DB local
            pos_info = self.db.get_pos_by_external_id(external_pos_id)
            if not pos_info:
                raise ValueError(f"POS {external_pos_id} no encontrado en base de datos local")
            
            # Obtener configuración
            user_id = self.db.get_config("USER_ID")
            if not user_id:
                raise ValueError("USER_ID no encontrado en configuración")
            
            # Generar IDs únicos si no se proporcionan
            if not external_reference:
                external_reference = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            
            # Calcular fecha de expiración
            if expiration_minutes is None:
                expiration_minutes = int(self.db.get_config("EXPIRATION_MIN", "15"))
            
            expiration_date = self._calculate_expiration_date(expiration_minutes)
            
            # URL con parámetros
            url = URL_CREATE_ORDER.format(
                user_id=user_id,
                external_pos_id=external_pos_id
            )
            
            # Cuerpo de la petición
            body = {
                "external_reference": external_reference,
                "title": title,
                "description": description or title,
                "notification_url": self.db.get_config("WEBHOOK_URL"),
                "expiration_date": expiration_date,
                "total_amount": total_amount,
                "items": [
                    {
                        "sku_number": external_reference,
                        "category": "marketplace",
                        "title": title,
                        "description": description or title,
                        "unit_price": total_amount,
                        "quantity": 1,
                        "unit_measure": "unit",  
                        "total_amount": total_amount
                    }
                ]
            }
            
            log.debug("Creando orden QR: %s", json.dumps(body, indent=2))
            
            # PUT para crear la orden en MP
            order_response = self._request("PUT", url, json=body)
            log.info("Orden creada en MP: %s", external_reference)
            
            # POST para obtener QR data
            qr_data_response = self._request("POST", url, json=body)
            qr_data = qr_data_response.get("qr_data")
            
            # Generar PNG del QR
            qr_png_b64 = None
            if qr_data:
                qr_png_b64 = self._generate_qr_png(qr_data)
            
            # CRÍTICO: Persistir orden en base de datos local
            orden_id = self._persist_order_to_db(
                caja_id=pos_info['caja_id'],
                external_reference=external_reference,
                title=title,
                description=description,
                total_amount=total_amount,
                qr_data=qr_data,
                qr_png_b64=qr_png_b64,
                expiration_date=expiration_date,
                order_response=order_response
            )
            
            # Log del éxito
            self.db.log_event(
                nivel="INFO",
                modulo="qr_client",
                mensaje=f"Orden QR creada y persistida: {external_reference}",
                external_reference=external_reference,
                datos_adicionales={
                    "orden_id": orden_id,
                    "pos_id": external_pos_id,
                    "amount": total_amount,
                    "expiration": expiration_date
                }
            )
            
            return {
                "order_id": external_reference,
                "orden_id_db": orden_id,  # ID interno de la DB
                "qr_data": qr_data,
                "qr_png_b64": qr_png_b64,
                "expiration_date": expiration_date,
                "order_info": order_response
            }
            
        except Exception as e:
            log.error("Error creando orden QR: %s", str(e))
            self.db.log_event(
                nivel="ERROR",
                modulo="qr_client",
                mensaje=f"Error creando orden QR: {external_reference or 'N/A'}",
                external_reference=external_reference,
                excepcion=e
            )
            raise

    def _persist_order_to_db(self, caja_id: int, external_reference: str, 
                           title: str, description: str, total_amount: float,
                           qr_data: str, qr_png_b64: str, expiration_date: str,
                           order_response: Dict[str, Any]) -> int:
        """
        Persiste la orden en la base de datos local
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Insertar orden principal
            cursor.execute("""
                INSERT INTO mp_ordenes 
                (caja_id, external_reference, titulo, descripcion, monto_total,
                 moneda, qr_data, qr_imagen_base64, fecha_expiracion, datos_adicionales)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                caja_id,
                external_reference,
                title,
                description,
                total_amount,
                self.db.get_config("CURRENCY_ID", "ARS"),
                qr_data,
                qr_png_b64,
                expiration_date,
                json.dumps(order_response) if order_response else None
            ))
            
            # Obtener ID de la orden insertada
            cursor.execute("SELECT @@IDENTITY")
            orden_id = cursor.fetchone()[0]
            
            # Insertar items de la orden
            cursor.execute("""
                INSERT INTO mp_orden_items 
                (orden_id, sku, titulo, descripcion, precio_unitario, cantidad, monto_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                orden_id,
                external_reference,
                title,
                description,
                total_amount,
                1,
                total_amount
            ))
            
            conn.commit()
            conn.close()
            
            log.info("Orden persistida en DB local: orden_id=%s, external_ref=%s", 
                    orden_id, external_reference)
            
            return orden_id
            
        except Exception as e:
            log.error("Error persistiendo orden en DB: %s", str(e))
            raise
    
    def get_order_status(self, external_pos_id: str, external_reference: str = None) -> Dict[str, Any]:
        """
        Consulta el estado de una orden con información mejorada desde DB local
        """
        try:
            # PASO 1: Buscar en base de datos local primero
            local_order = self._get_local_order(external_reference)
            
            # PASO 2: Consultar estado en MP
            # Intentar como orden QR (antes del pago)
            qr_order_result = None
            try:
                qr_order_result = self._get_qr_order(external_pos_id, external_reference)
                if qr_order_result:
                    log.info("Orden encontrada en estado QR: %s", external_reference)
                    
                    # Combinar datos locales con datos de MP
                    result = {
                        "status": "pending",
                        "source": "qr_order",
                        "data": qr_order_result,
                        "external_reference": external_reference,
                        "local_order": local_order
                    }
                    
                    return result
                    
            except Exception as qr_error:
                log.debug("No encontrada como orden QR: %s", str(qr_error))
            
            # PASO 3: Buscar como pago procesado
            payment_result = self._get_processed_payment(external_reference)
            if payment_result:
                log.info("Pago procesado encontrado: %s", external_reference)
                
                # Actualizar orden local si existe
                if local_order:
                    self._update_local_order_from_payment(local_order['orden_id'], payment_result)
                
                return {
                    "status": payment_result.get("status", "unknown"),
                    "source": "payment",
                    "data": payment_result,
                    "external_reference": external_reference,
                    "local_order": local_order,
                    "payment_id": payment_result.get("id"),
                    "amount": payment_result.get("transaction_amount"),
                    "currency": payment_result.get("currency_id"),
                    "date_created": payment_result.get("date_created"),
                    "date_approved": payment_result.get("date_approved")
                }
            
            # PASO 4: Solo datos locales (orden expirada/cancelada)
            if local_order:
                return {
                    "status": local_order['estado'].lower(),
                    "source": "local_db",
                    "external_reference": external_reference,
                    "local_order": local_order,
                    "message": "Orden encontrada solo en base de datos local"
                }
            
            # PASO 5: No encontrado
            log.warning("Orden/Pago no encontrado: %s", external_reference)
            return {
                "status": "not_found",
                "source": "none",
                "external_reference": external_reference,
                "error": "Orden no encontrada en MP ni en base de datos local"
            }
            
        except Exception as e:
            log.error("Error consultando estado de orden: %s", str(e))
            self.db.log_event(
                nivel="ERROR",
                modulo="qr_client",
                mensaje=f"Error consultando estado: {external_reference}",
                external_reference=external_reference,
                excepcion=e
            )
            raise

    def _get_local_order(self, external_reference: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene una orden desde la base de datos local
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    o.orden_id, o.external_reference, o.titulo, o.descripcion,
                    o.monto_total, o.moneda, o.estado, o.estado_mp,
                    o.fecha_creacion, o.fecha_expiracion, o.fecha_pago,
                    o.qr_data, o.qr_imagen_base64, o.mp_payment_id
                FROM mp_ordenes o
                WHERE o.external_reference = ?
            """, (external_reference,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'orden_id': row[0],
                    'external_reference': row[1],
                    'titulo': row[2],
                    'descripcion': row[3],
                    'monto_total': float(row[4]) if row[4] else 0,
                    'moneda': row[5],
                    'estado': row[6],
                    'estado_mp': row[7],
                    'fecha_creacion': row[8],
                    'fecha_expiracion': row[9],
                    'fecha_pago': row[10],
                    'qr_data': row[11],
                    'qr_imagen_base64': row[12],
                    'mp_payment_id': row[13]
                }
            
            return None
            
        except Exception as e:
            log.error("Error obteniendo orden local: %s", str(e))
            return None

    def _update_local_order_from_payment(self, orden_id: int, payment_data: Dict[str, Any]):
        """
        Actualiza una orden local basada en datos de pago
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Mapear estado
            mp_status = payment_data.get("status")
            local_status = "PENDIENTE"
            
            if mp_status == "approved":
                local_status = "PAGADO"
            elif mp_status in ["rejected", "cancelled"]:
                local_status = "CANCELADO"
            elif mp_status == "pending":
                local_status = "PENDIENTE"
            
            cursor.execute("""
                UPDATE mp_ordenes 
                SET estado = ?,
                    estado_mp = ?,
                    mp_payment_id = ?,
                    fecha_pago = CASE WHEN ? = 'PAGADO' THEN GETDATE() ELSE fecha_pago END
                WHERE orden_id = ?
            """, (local_status, mp_status, payment_data.get("id"), local_status, orden_id))
            
            conn.commit()
            conn.close()
            
            log.info("Orden local actualizada desde pago: orden_id=%s, status=%s", 
                    orden_id, local_status)
            
        except Exception as e:
            log.error("Error actualizando orden local: %s", str(e))

    def _calculate_expiration_date(self, minutes: int) -> str:
        """
        Calcula fecha de expiración en formato ISO para MP
        """
        expiration = datetime.now() + timedelta(minutes=minutes)
        return expiration.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "-03:00"

    # ... resto de métodos existentes sin cambios ...
    
    def _get_qr_order(self, external_pos_id: str, external_reference: str = None):
        """
        Consulta el estado de una orden QR (método original)
        Solo funciona ANTES de que se procese el pago
        """
        user_id = self.db.get_config("USER_ID")
        url = URL_GET_ORDER.format(
            user_id=user_id,
            external_pos_id=external_pos_id
        )
        
        params = {}
        if external_reference:
            params["external_reference"] = external_reference
        
        response = self._request("GET", url, params=params)
        return response
    
    def _get_processed_payment(self, external_reference: str):
        """
        Busca un pago procesado usando la Payments API
        Funciona DESPUÉS de que se procese el pago
        
        Args:
            external_reference: Referencia externa para buscar
            
        Returns:
            dict: Información del pago si se encuentra, None si no
        """
        try:
            # PASO 1: Buscar pagos por external_reference
            params = {
                "external_reference": external_reference,
                "limit": 10  # Limitar resultados
            }
            
            log.debug("Buscando pago con external_reference: %s", external_reference)
            search_response = self._request("GET", URL_SEARCH_PAYMENTS, params=params)
            
            # Verificar si encontramos resultados
            results = search_response.get("results", [])
            if not results:
                log.debug("No se encontraron pagos para external_reference: %s", external_reference)
                return None
            
            # PASO 2: Tomar el primer resultado (más reciente)
            payment_summary = results[0]
            payment_id = payment_summary.get("id")
            
            if not payment_id:
                log.warning("Payment ID no encontrado en resultados de búsqueda")
                return payment_summary  # Devolver lo que tengamos
            
            # PASO 3: Obtener detalles completos del pago
            log.debug("Obteniendo detalles del pago ID: %s", payment_id)
            payment_url = URL_GET_PAYMENT.format(payment_id=payment_id)
            payment_details = self._request("GET", payment_url)
            
            log.info("Pago encontrado - ID: %s, Status: %s, Amount: %s", 
                    payment_id, 
                    payment_details.get("status"), 
                    payment_details.get("transaction_amount"))
            
            return payment_details
            
        except Exception as e:
            log.error("Error buscando pago procesado: %s", str(e))
            # Si falla la búsqueda detallada, puede ser que el pago no exista
            return None
    
    # Método de compatibilidad hacia atrás
    def get_order(self, external_pos_id: str, external_reference: str = None):
        """
        Método de compatibilidad - usa la nueva lógica mejorada
        """
        return self.get_order_status(external_pos_id, external_reference)
    
    def cancel_order(self, external_pos_id: str, external_reference: str):
        """
        Cancela una orden existente (método correcto para QR dinámico)
        """
        try:
            user_id = self.db.get_config("USER_ID")
            
            # Para QR dinámico, usar el endpoint correcto
            url = URL_CREATE_ORDER.format(
                user_id=user_id,
                external_pos_id=external_pos_id
            )
            
            # Cuerpo para cancelación
            body = {
                "external_reference": external_reference
            }
            
            # Usar DELETE en el endpoint de creación, no en orders
            response = self._request("DELETE", url, json=body)
            
            # Actualizar estado en DB local
            self._update_local_order_status(external_reference, "CANCELADO")
            
            log.info("Orden cancelada: %s", external_reference)
            self.db.log_event(
                nivel="INFO",
                modulo="qr_client",
                mensaje=f"Orden cancelada: {external_reference}",
                external_reference=external_reference,
                datos_adicionales=response
            )
            
            return response
            
        except Exception as e:
            log.error("Error cancelando orden: %s", str(e))
            # Si falla la cancelación, intentar método alternativo
            return self._alternative_cancel(external_pos_id, external_reference)
    
    def _update_local_order_status(self, external_reference: str, new_status: str):
        """
        Actualiza el estado de una orden en la DB local
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE mp_ordenes 
                SET estado = ?
                WHERE external_reference = ?
            """, (new_status, external_reference))
            
            conn.commit()
            conn.close()
            
            log.debug("Estado de orden actualizado en DB local: %s -> %s", 
                     external_reference, new_status)
            
        except Exception as e:
            log.error("Error actualizando estado local de orden: %s", str(e))
    
    def _alternative_cancel(self, external_pos_id: str, external_reference: str):
        """
        Método alternativo para cancelar orden (crear nueva orden con monto 0)
        """
        try:
            log.warning("Intentando cancelación alternativa para: %s", external_reference)
            
            # Crear una orden de "cancelación" con monto 0
            cancel_result = self.create_order(
                external_pos_id=external_pos_id,
                title=f"CANCELACION-{external_reference}",
                total_amount=0.01,  # Monto mínimo
                description=f"Cancelación de orden {external_reference}",
                external_reference=f"CANCEL-{external_reference}"
            )
            
            # Marcar orden original como cancelada
            self._update_local_order_status(external_reference, "CANCELADO")
            
            log.info("Orden de cancelación creada: %s", cancel_result["order_id"])
            return {"status": "cancelled_alternative", "cancel_order": cancel_result}
            
        except Exception as alt_e:
            log.error("Error en cancelación alternativa: %s", str(alt_e))
            # Si todo falla, al menos marcar como cancelada localmente
            self._update_local_order_status(external_reference, "ERROR")
            return {"status": "cancellation_failed", "message": "La orden permanece activa"}
    
    def expire_order(self, external_pos_id: str, external_reference: str):
        """
        Método más directo: modificar la orden para que expire inmediatamente
        """
        try:
            user_id = self.db.get_config("USER_ID")
            url = URL_CREATE_ORDER.format(
                user_id=user_id,
                external_pos_id=external_pos_id
            )
            
            # Obtener la orden actual
            current_order = self.get_order(external_pos_id, external_reference)
            
            if current_order:
                # Actualizar con fecha de expiración pasada
                expired_date = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "-03:00"
                
                body = current_order.copy()
                body["expiration_date"] = expired_date
                
                response = self._request("PUT", url, json=body)
                
                # Actualizar en DB local
                self._update_local_order_status(external_reference, "EXPIRADO")
                
                log.info("Orden expirada: %s", external_reference)
                return response
            
        except Exception as e:
            log.error("Error expirando orden: %s", str(e))
            raise
    
    def _generate_qr_png(self, qr_data: str):
        """
        Genera imagen PNG del código QR (requiere qrcode y PIL)
        """
        try:
            import qrcode
            from io import BytesIO
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convertir a base64
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_b64 = base64.b64encode(buffer.getvalue()).decode()
            
            return img_b64
            
        except ImportError:
            log.warning("qrcode no instalado, no se puede generar PNG")
            return None
        except Exception as e:
            log.error("Error generando QR PNG: %s", str(e))
            return None

    def get_orders_by_status(self, status: str = None, limit: int = 100) -> list:
        """
        Obtiene órdenes desde la base de datos local por estado
        
        Args:
            status: Estado a filtrar (PENDIENTE, PAGADO, CANCELADO, EXPIRADO)
            limit: Límite de resultados
            
        Returns:
            Lista de órdenes
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT TOP (?) 
                        o.orden_id, o.external_reference, o.titulo, o.monto_total,
                        o.estado, o.fecha_creacion, o.fecha_expiracion, o.fecha_pago
                    FROM mp_ordenes o
                    WHERE o.estado = ?
                    ORDER BY o.fecha_creacion DESC
                """, (limit, status))
            else:
                cursor.execute("""
                    SELECT TOP (?) 
                        o.orden_id, o.external_reference, o.titulo, o.monto_total,
                        o.estado, o.fecha_creacion, o.fecha_expiracion, o.fecha_pago
                    FROM mp_ordenes o
                    ORDER BY o.fecha_creacion DESC
                """, (limit,))
            
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    'orden_id': row[0],
                    'external_reference': row[1],
                    'titulo': row[2],
                    'monto_total': float(row[3]) if row[3] else 0,
                    'estado': row[4],
                    'fecha_creacion': row[5],
                    'fecha_expiracion': row[6],
                    'fecha_pago': row[7]
                })
            
            conn.close()
            return orders
            
        except Exception as e:
            log.error("Error obteniendo órdenes por estado: %s", str(e))
            return []

    def cleanup_expired_orders(self) -> int:
        """
        Marca como expiradas las órdenes que ya pasaron su fecha de expiración
        
        Returns:
            Número de órdenes marcadas como expiradas
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE mp_ordenes 
                SET estado = 'EXPIRADO'
                WHERE estado = 'PENDIENTE' 
                  AND fecha_expiracion < GETDATE()
            """)
            
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                log.info("Órdenes marcadas como expiradas: %d", rows_affected)
                self.db.log_event(
                    nivel="INFO",
                    modulo="qr_client",
                    mensaje=f"Limpieza automática: {rows_affected} órdenes expiradas",
                    datos_adicionales={"expired_count": rows_affected}
                )
            
            return rows_affected
            
        except Exception as e:
            log.error("Error en limpieza de órdenes expiradas: %s", str(e))
            return 