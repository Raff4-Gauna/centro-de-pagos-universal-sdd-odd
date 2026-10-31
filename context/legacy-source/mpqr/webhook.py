# mpqr/webhook.py
import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from .db_config import get_db_config

log = logging.getLogger("mpqr.webhook")

class WebhookProcessor:
    """
    Procesador robusto de webhooks de Mercado Pago
    Maneja notificaciones de pagos y órdenes de manera completa
    """
    
    def __init__(self):
        self.db = get_db_config()

    def handle_notification(self, data: Dict[str, Any], headers: Dict[str, str] = None, 
                          ip_origen: str = None) -> bool:
        """
        Procesa una notificación webhook de Mercado Pago
        
        Args:
            data: Datos JSON del webhook
            headers: Headers HTTP de la request
            ip_origen: IP de origen de la notificación
            
        Returns:
            bool: True si se procesó correctamente
        """
        try:
            # Extraer datos básicos
            topic = data.get("topic", "")
            action = data.get("action", "")
            mp_id = data.get("id")
            external_reference = data.get("external_reference")
            
            # Calcular hash del payload para evitar duplicados
            payload_str = json.dumps(data, sort_keys=True)
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
            
            log.info("Webhook recibido: topic=%s, action=%s, id=%s, ext_ref=%s", 
                    topic, action, mp_id, external_reference)
            
            # Registrar webhook en base de datos
            webhook_id = self._store_webhook(
                tipo=topic,
                accion=action,
                mp_id=mp_id,
                external_reference=external_reference,
                payload_raw=payload_str,
                headers_raw=json.dumps(headers) if headers else None,
                ip_origen=ip_origen,
                hash_payload=payload_hash
            )
            
            # Verificar si ya fue procesado (evitar duplicados)
            if self._is_duplicate_webhook(payload_hash, webhook_id):
                log.warning("Webhook duplicado detectado, ignorando")
                return True
            
            # Procesar según el tipo
            if topic == "payment":
                success = self._process_payment_notification(data, webhook_id)
            elif topic == "merchant_order":
                success = self._process_merchant_order_notification(data, webhook_id)
            else:
                log.warning("Tipo de webhook no soportado: %s", topic)
                success = False
            
            # Marcar como procesado
            self._mark_webhook_processed(webhook_id, success)
            
            # Log del resultado
            self.db.log_event(
                nivel="INFO" if success else "WARNING",
                modulo="webhook",
                mensaje=f"Webhook procesado: {topic}/{action} - {'éxito' if success else 'fallo'}",
                external_reference=external_reference,
                datos_adicionales={
                    "webhook_id": webhook_id,
                    "topic": topic,
                    "action": action,
                    "mp_id": mp_id,
                    "success": success
                }
            )
            
            return success
            
        except Exception as e:
            log.error("Error procesando webhook: %s", str(e))
            self.db.log_event(
                nivel="ERROR",
                modulo="webhook",
                mensaje="Error procesando webhook",
                datos_adicionales=data,
                excepcion=e
            )
            return False

    def _process_payment_notification(self, data: Dict[str, Any], webhook_id: int) -> bool:
        """
        Procesa notificaciones de pagos
        """
        try:
            mp_payment_id = data.get("id")
            external_reference = data.get("external_reference")
            
            if not mp_payment_id:
                log.error("Webhook de pago sin ID")
                return False
            
            # Si tenemos external_reference, buscar la orden local
            orden_id = None
            if external_reference:
                orden_id = self._get_orden_by_external_reference(external_reference)
            
            # Obtener detalles del pago desde MP API
            payment_details = self._fetch_payment_details(mp_payment_id)
            
            if not payment_details:
                log.error("No se pudieron obtener detalles del pago %s", mp_payment_id)
                return False
            
            # Insertar o actualizar pago en base de datos
            self._upsert_payment(payment_details, orden_id)
            
            # Si hay orden local, actualizarla
            if orden_id:
                self._update_orden_status(orden_id, payment_details)
            
            return True
            
        except Exception as e:
            log.error("Error procesando notificación de pago: %s", str(e))
            return False

    def _process_merchant_order_notification(self, data: Dict[str, Any], webhook_id: int) -> bool:
        """
        Procesa notificaciones de merchant orders
        """
        try:
            merchant_order_id = data.get("id")
            
            if not merchant_order_id:
                log.error("Webhook de merchant order sin ID")
                return False
            
            # Aquí podrías implementar lógica específica para merchant orders
            # Por ahora solo logueamos
            log.info("Merchant order notification procesada: %s", merchant_order_id)
            return True
            
        except Exception as e:
            log.error("Error procesando notificación de merchant order: %s", str(e))
            return False

    def _store_webhook(self, tipo: str, accion: str, mp_id: int = None, 
                      external_reference: str = None, payload_raw: str = None,
                      headers_raw: str = None, ip_origen: str = None,
                      hash_payload: str = None) -> int:
        """
        Almacena el webhook en la base de datos
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO mp_webhooks 
                (tipo, accion, mp_id, external_reference, payload_raw, 
                 headers_raw, ip_origen, hash_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tipo, accion, mp_id, external_reference, payload_raw,
                  headers_raw, ip_origen, hash_payload))
            
            # Obtener el ID del webhook insertado
            cursor.execute("SELECT @@IDENTITY")
            webhook_id = cursor.fetchone()[0]
            
            conn.commit()
            conn.close()
            
            return webhook_id
            
        except Exception as e:
            log.error("Error almacenando webhook: %s", str(e))
            raise

    def _is_duplicate_webhook(self, payload_hash: str, current_webhook_id: int) -> bool:
        """
        Verifica si ya existe un webhook con el mismo hash
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM mp_webhooks 
                WHERE hash_payload = ? AND webhook_id != ? AND procesado = 1
            """, (payload_hash, current_webhook_id))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            log.error("Error verificando webhook duplicado: %s", str(e))
            return False

    def _mark_webhook_processed(self, webhook_id: int, success: bool):
        """
        Marca el webhook como procesado
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE mp_webhooks 
                SET procesado = ?, 
                    fecha_procesamiento = GETDATE(),
                    intentos_procesamiento = intentos_procesamiento + 1,
                    error_procesamiento = CASE WHEN ? = 0 THEN 'Error en procesamiento' ELSE NULL END
                WHERE webhook_id = ?
            """, (1 if success else 0, 1 if success else 0, webhook_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            log.error("Error marcando webhook como procesado: %s", str(e))

    def _get_orden_by_external_reference(self, external_reference: str) -> Optional[int]:
        """
        Busca una orden por external_reference
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT orden_id FROM mp_ordenes 
                WHERE external_reference = ?
            """, (external_reference,))
            
            row = cursor.fetchone()
            conn.close()
            
            return row[0] if row else None
            
        except Exception as e:
            log.error("Error buscando orden: %s", str(e))
            return None

    def _fetch_payment_details(self, mp_payment_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene detalles del pago desde la API de MP
        """
        try:
            # Importar HTTPClient aquí para evitar dependencias circulares
            from .http_client import HTTPClient
            
            client = HTTPClient()
            payment_url = f"/v1/payments/{mp_payment_id}"
            
            return client._request("GET", payment_url)
            
        except Exception as e:
            log.error("Error obteniendo detalles del pago: %s", str(e))
            return None

    def _upsert_payment(self, payment_details: Dict[str, Any], orden_id: int = None):
        """
        Inserta o actualiza un pago en la base de datos
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            mp_payment_id = payment_details.get("id")
            
            # Verificar si ya existe
            cursor.execute("SELECT pago_id FROM mp_pagos WHERE mp_payment_id = ?", (mp_payment_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Actualizar
                cursor.execute("""
                    UPDATE mp_pagos 
                    SET estado = ?, 
                        estado_detalle = ?,
                        fecha_aprobacion = ?,
                        fecha_actualizacion = GETDATE(),
                        datos_mp_raw = ?
                    WHERE mp_payment_id = ?
                """, (
                    payment_details.get("status"),
                    payment_details.get("status_detail"),
                    payment_details.get("date_approved"),
                    json.dumps(payment_details),
                    mp_payment_id
                ))
            else:
                # Insertar
                cursor.execute("""
                    INSERT INTO mp_pagos 
                    (orden_id, mp_payment_id, external_reference, monto, moneda,
                     metodo_pago, tipo_pago, estado, estado_detalle, 
                     fecha_creacion, fecha_aprobacion, datos_mp_raw)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    orden_id,
                    mp_payment_id,
                    payment_details.get("external_reference"),
                    payment_details.get("transaction_amount"),
                    payment_details.get("currency_id"),
                    payment_details.get("payment_method_id"),
                    payment_details.get("payment_type_id"),
                    payment_details.get("status"),
                    payment_details.get("status_detail"),
                    payment_details.get("date_created"),
                    payment_details.get("date_approved"),
                    json.dumps(payment_details)
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            log.error("Error guardando pago: %s", str(e))
            raise

    def _update_orden_status(self, orden_id: int, payment_details: Dict[str, Any]):
        """
        Actualiza el estado de una orden basado en el pago
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Mapear estado de MP a estado local
            mp_status = payment_details.get("status")
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
            """, (local_status, mp_status, payment_details.get("id"), local_status, orden_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            log.error("Error actualizando estado de orden: %s", str(e))

    def get_payment_status(self, external_reference: str) -> str:
        """
        Obtiene el estado de un pago por external_reference
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT estado FROM mp_pagos 
                WHERE external_reference = ? 
                ORDER BY fecha_actualizacion DESC
            """, (external_reference,))
            
            row = cursor.fetchone()
            conn.close()
            
            return row[0] if row else "pending"
            
        except Exception as e:
            log.error("Error consultando estado desde DB: %s", str(e))
            return "pending"