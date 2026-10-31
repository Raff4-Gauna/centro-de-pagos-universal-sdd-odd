# com_server/mpqr_server.py
import sys, os, json, pythoncom, logging
from pathlib import Path
from win32com.server import register
from dotenv import load_dotenv

# ─── Configurar logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("mpqr_com")

# ─── Inserta raíz del proyecto en sys.path ────────────────────────────
_here = Path(__file__).resolve()
_root = _here.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ─── Carga variables de entorno desde .env ────────────────────────────
load_dotenv(dotenv_path=_root / ".env", override=False)

# ─── Imports de tu SDK -------------------------------------------------
from mpqr.qr_client  import QRClient
from mpqr.pos_client import POSClient
from mpqr.db_config import get_db_config, DecimalEncoder  # ✅ IMPORTAR DecimalEncoder

# ─── Clase expuesta al COM --------------------------------------------
class MPQRServer:
    _public_methods_ = [
        "CreatePOS", "GetPOS",
        "CreateQR", "GetQRStatus", "CancelQR",
        "LastQrPng", "LastOrderId", "GetLastError"
    ]
    _reg_progid_ = "MPQR.Server"
    _reg_clsid_  = "{7B0625B0-F4BB-4F8A-BBA1-0DDEB7E425A1}"

    def __init__(self):
        try:
            self.db_config = get_db_config()
            self.qr  = QRClient()
            self.pos = POSClient()
            self._last_png   = ""
            self._last_oid   = ""
            self._last_error = ""
            log.info("MPQR COM Server inicializado correctamente")
            self.db_config.log_event('INFO', 'mpqr_server', 'MPQR COM Server initialized successfully')
        except Exception as e:
            self._last_error = str(e)
            log.error("Error inicializando MPQR COM Server: %s", e)
            if hasattr(self, 'db_config'):
                self.db_config.log_event('ERROR', 'mpqr_server', 'Error initializing MPQR COM Server', excepcion=e)
            raise

    def _handle_error(self, operation: str, error: Exception) -> str:
        """Maneja errores de forma consistente y los registra en DB"""
        error_msg = f"Error en {operation}: {str(error)}"
        self._last_error = error_msg
        log.error(error_msg)
        self.db_config.log_event('ERROR', 'mpqr_server', error_msg, excepcion=error)
        return json.dumps({"error": error_msg, "success": False}, cls=DecimalEncoder)  # ✅ USAR DecimalEncoder

    def _safe_json_response(self, data: dict) -> str:
        """Serializa respuesta de forma segura manejando Decimals"""
        try:
            return json.dumps(data, cls=DecimalEncoder, ensure_ascii=False)  # ✅ USAR DecimalEncoder
        except Exception as e:
            log.error("Error serializando respuesta: %s", str(e))
            return json.dumps({
                "error": f"Error serializando respuesta: {str(e)}", 
                "success": False
            })

    # -------- POS ----------
    def CreatePOS(self, external_pos_id):
        """Crea un nuevo punto de venta usando configuración de la DB"""
        try:
            result = self.pos.create_pos(external_pos_id)
            self._last_error = ""
            log.info("POS creado: %s", external_pos_id)
            self.db_config.log_event('INFO', 'mpqr_server', f'POS created: {external_pos_id}', external_reference=external_pos_id)
            return self._safe_json_response({"data": result, "success": True})  # ✅ USAR MÉTODO SEGURO
        except Exception as e:
            return self._handle_error("CreatePOS", e)

    def GetPOS(self, external_pos_id):
        """Obtiene información de un POS existente"""
        try:
            result = self.pos.get_pos(external_pos_id)
            self._last_error = ""
            log.info("POS obtenido: %s", external_pos_id)
            self.db_config.log_event('INFO', 'mpqr_server', f'POS retrieved: {external_pos_id}', external_reference=external_pos_id)
            return self._safe_json_response({"data": result, "success": True})  # ✅ USAR MÉTODO SEGURO
        except Exception as e:
            return self._handle_error("GetPOS", e)

    # -------- QR Dinámico --------
    def CreateQR(self, external_pos_id: str, title: str, total_amount: float, description: str = None, external_reference: str = None):
        """Crea una orden QR dinámica y devuelve el QR en base64"""
        try:
            result = self.qr.create_order(external_pos_id, title, total_amount, description, external_reference)
            self._last_png = result.get("qr_png_b64", "")
            self._last_oid = result.get("order_id", "")
            self._last_error = ""
            log.info("QR creado para POS %s, Orden ID: %s", external_pos_id, self._last_oid)
            self.db_config.log_event('INFO', 'mpqr_server', f'QR order created for POS {external_pos_id}, Order ID: {self._last_oid}', external_reference=self._last_oid, datos_adicionales={'pos_id': external_pos_id})
            return self._safe_json_response({"data": result, "success": True})  # ✅ USAR MÉTODO SEGURO
        except Exception as e:
            return self._handle_error("CreateQR", e)
    
    def GetQRStatus(self, external_pos_id: str, order_id: str):
        """Consulta el estado de una orden QR"""
        try:
            log.info(f"🔍 GetQRStatus llamado: POS={external_pos_id}, OrderID={order_id}")
            
            result = self.qr.get_order_status(external_pos_id, order_id)
            self._last_error = ""
            
            # LOG DETALLADO
            log.info(f"📊 Resultado MP: {json.dumps(result, indent=2, cls=DecimalEncoder)}")
            
            # Verificar campos críticos
            if result and 'status' in result:
                status = result.get('status', 'unknown')
                payment_status = result.get('payment_status') or result.get('data', {}).get('status')
                payment_id = result.get('payment_id') or result.get('data', {}).get('id')
                
                log.info(f"✅ Datos clave: Status={status}, PaymentStatus={payment_status}, PaymentID={payment_id}")
                
                self.db_config.log_event('INFO', 'mpqr_server', 
                                       f'QR status retrieved: {order_id}', 
                                       external_reference=order_id, 
                                       datos_adicionales={
                                           'pos_id': external_pos_id, 
                                           'status': status,
                                           'payment_status': payment_status,
                                           'payment_id': payment_id
                                       })
            
            return self._safe_json_response({"data": result, "success": True})
        except Exception as e:
            return self._handle_error("GetQRStatus", e)

    def CancelQR(self, external_pos_id: str, order_id: str):
        """Cancela una orden QR"""
        try:
            result = self.qr.cancel_order(external_pos_id, order_id)
            self._last_error = ""
            log.info("QR cancelado: %s", order_id)
            self.db_config.log_event('INFO', 'mpqr_server', f'QR order cancelled: {order_id}', external_reference=order_id, datos_adicionales={'pos_id': external_pos_id})
            return self._safe_json_response({"data": result, "success": True})  # ✅ USAR MÉTODO SEGURO
        except Exception as e:
            return self._handle_error("CancelQR", e)
    
    # -------- Helpers ------
    def LastQrPng(self):
        """Devuelve el PNG en Base64 del último QR generado"""
        return self._last_png
    
    def LastOrderId(self):
        """Devuelve el ID de la última orden creada"""
        return self._last_oid
    
    def GetLastError(self):
        """Devuelve el último error ocurrido"""
        return self._last_error

# ─── CLI para registrar / desregistrar --------------------------------
def _usage():
    print("Uso: python mpqr_server.py --register | --unregister")
    sys.exit(1)

if __name__ == "__main__":
    if "--register" in sys.argv:
        try:
            register.RegisterClasses(MPQRServer)
            print("✅ MPQR.Server registrado exitosamente.")
        except Exception as e:
            print(f"❌ Error registrando MPQR.Server: {e}")
    elif "--unregister" in sys.argv:
        try:
            register.UnregisterClasses(MPQRServer)
            print("🗑️ MPQR.Server desregistrado exitosamente.")
        except Exception as e:
            print(f"❌ Error desregistrando MPQR.Server: {e}")
    else:
        _usage()