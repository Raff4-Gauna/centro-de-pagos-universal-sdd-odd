# mpqr/db_config.py - VERSIÓN CORREGIDA SIN ERRORES DECIMAL
"""
Módulo de configuración de base de datos para MPQR COM
Lee la cadena de conexión desde .env y gestiona todas las configuraciones desde SQL Server
"""

import pyodbc
import logging
import json
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import threading
from decimal import Decimal
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

log = logging.getLogger("mpqr.db_config")

class DecimalEncoder(json.JSONEncoder):
    """Encoder personalizado para manejar tipos Decimal de SQL Server"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

class DatabaseConfig:
    """
    Gestor de configuración que lee desde base de datos SQL Server
    Incluye cache en memoria para performance
    """
    
    def __init__(self, connection_string: str = None):
        """
        Inicializa la conexión a base de datos
        
        Args:
            connection_string: String de conexión a SQL Server
                Si es None, lee desde variable de entorno DB_CONNECTION_STRING
        """
        if connection_string is None:
            # Leer cadena de conexión desde .env
            self.connection_string = os.getenv('DB_CONNECTION_STRING')
            if not self.connection_string:
                raise ValueError("DB_CONNECTION_STRING no está definida en el archivo .env")
        else:
            self.connection_string = connection_string
        
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._cache_timeout = 300  # 5 minutos
        self._last_cache_update = {}
        
        # Probar conexión inicial
        self._test_connection()
    
    def _test_connection(self):
        """Prueba la conexión a la base de datos"""
        try:
            conn = pyodbc.connect(self.connection_string)
            conn.close()
            log.info("Conexión a base de datos establecida correctamente")
        except Exception as e:
            log.error("Error conectando a base de datos: %s", str(e))
            raise RuntimeError(f"No se puede conectar a la base de datos: {str(e)}")
    
    def get_connection(self) -> pyodbc.Connection:
        """Obtiene una nueva conexión a la base de datos"""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            log.error("Error obteniendo conexión: %s", str(e))
            raise
    
    def get_config(self, clave: str, default: str = None) -> Optional[str]:
        """
        Obtiene un valor de configuración desde la base de datos
        
        Args:
            clave: Clave de configuración a buscar
            default: Valor por defecto si no se encuentra
            
        Returns:
            Valor de configuración o default
        """
        # Verificar cache primero
        with self._cache_lock:
            if clave in self._cache:
                cache_time = self._last_cache_update.get(clave, 0)
                if (datetime.now().timestamp() - cache_time) < self._cache_timeout:
                    return self._cache[clave]
        
        # Buscar en base de datos
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT valor FROM mp_configuraciones WHERE clave = ? AND activo = 1",
                (clave,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                valor = row[0]
                # Actualizar cache
                with self._cache_lock:
                    self._cache[clave] = valor
                    self._last_cache_update[clave] = datetime.now().timestamp()
                return valor
            else:
                log.warning("Configuración no encontrada: %s", clave)
                return default
                
        except Exception as e:
            log.error("Error obteniendo configuración %s: %s", clave, str(e))
            return default
    
    def set_config(self, clave: str, valor: str, descripcion: str = None, categoria: str = "GENERAL"):
        """
        Establece un valor de configuración en la base de datos
        
        Args:
            clave: Clave de configuración
            valor: Valor a establecer
            descripcion: Descripción opcional
            categoria: Categoría de la configuración
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Verificar si existe
            cursor.execute(
                "SELECT config_id FROM mp_configuraciones WHERE clave = ?",
                (clave,)
            )
            exists = cursor.fetchone()
            
            if exists:
                # Actualizar
                cursor.execute("""
                    UPDATE mp_configuraciones 
                    SET valor = ?, 
                        descripcion = COALESCE(?, descripcion),
                        categoria = ?,
                        fecha_modificacion = GETDATE(),
                        usuario_modificacion = SYSTEM_USER
                    WHERE clave = ?
                """, (valor, descripcion, categoria, clave))
            else:
                # Insertar
                cursor.execute("""
                    INSERT INTO mp_configuraciones 
                    (clave, valor, descripcion, categoria)
                    VALUES (?, ?, ?, ?)
                """, (clave, valor, descripcion, categoria))
            
            conn.commit()
            conn.close()
            
            # Limpiar cache
            with self._cache_lock:
                if clave in self._cache:
                    del self._cache[clave]
                if clave in self._last_cache_update:
                    del self._last_cache_update[clave]
            
            log.info("Configuración actualizada: %s", clave)
            
        except Exception as e:
            log.error("Error estableciendo configuración %s: %s", clave, str(e))
            raise
    
    def get_all_config(self, categoria: str = None) -> Dict[str, str]:
        """
        Obtiene todas las configuraciones activas
        
        Args:
            categoria: Filtrar por categoría específica
            
        Returns:
            Diccionario con todas las configuraciones
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if categoria:
                cursor.execute(
                    "SELECT clave, valor FROM mp_configuraciones WHERE activo = 1 AND categoria = ?",
                    (categoria,)
                )
            else:
                cursor.execute(
                    "SELECT clave, valor FROM mp_configuraciones WHERE activo = 1"
                )
            
            config = {}
            for row in cursor.fetchall():
                config[row[0]] = row[1]
            
            conn.close()
            return config
            
        except Exception as e:
            log.error("Error obteniendo todas las configuraciones: %s", str(e))
            return {}
    
    def get_active_credentials(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene las credenciales activas de Mercado Pago
        
        Returns:
            Diccionario con las credenciales activas o None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    credencial_id,
                    nombre_entorno,
                    access_token,
                    user_id,
                    public_key,
                    webhook_secret,
                    webhook_url,
                    es_sandbox
                FROM mp_credenciales
                WHERE es_activo = 1 AND estado = 'ACTIVO'
            """)
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'credencial_id': row[0],
                    'nombre_entorno': row[1],
                    'access_token': row[2],
                    'user_id': row[3],
                    'public_key': row[4],
                    'webhook_secret': row[5],
                    'webhook_url': row[6],
                    'es_sandbox': row[7]
                }
            return None
            
        except Exception as e:
            log.error("Error obteniendo credenciales activas: %s", str(e))
            return None
    
    def get_store_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de una sucursal por su ID externo
        
        Args:
            external_id: ID externo de la sucursal
            
        Returns:
            Diccionario con información de la sucursal o None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    s.sucursal_id,
                    s.mp_store_id,
                    s.external_id,
                    s.nombre,
                    s.estado,
                    c.access_token
                FROM mp_sucursales s
                INNER JOIN mp_credenciales c ON s.credencial_id = c.credencial_id
                WHERE s.external_id = ? AND s.estado = 'ACTIVO'
            """, (external_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'sucursal_id': row[0],
                    'mp_store_id': row[1],
                    'external_id': row[2],
                    'nombre': row[3],
                    'estado': row[4],
                    'access_token': row[5]
                }
            return None
            
        except Exception as e:
            log.error("Error obteniendo sucursal %s: %s", external_id, str(e))
            return None
    
    def get_pos_by_external_id(self, external_pos_id: str, external_store_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un POS por su ID externo
        
        Args:
            external_pos_id: ID externo del POS
            external_store_id: ID externo de la sucursal (opcional)
            
        Returns:
            Diccionario con información del POS o None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if external_store_id:
                cursor.execute("""
                    SELECT 
                        p.caja_id,
                        p.mp_pos_id,
                        p.external_id,
                        p.nombre,
                        p.categoria_mp,
                        p.monto_fijo,
                        p.qr_estatico,
                        s.mp_store_id,
                        s.external_id as store_external_id,
                        c.access_token
                    FROM mp_cajas p
                    INNER JOIN mp_sucursales s ON p.sucursal_id = s.sucursal_id
                    INNER JOIN mp_credenciales c ON s.credencial_id = c.credencial_id
                    WHERE p.external_id = ? 
                        AND s.external_id = ?
                        AND p.estado = 'ACTIVO'
                        AND s.estado = 'ACTIVO'
                """, (external_pos_id, external_store_id))
            else:
                cursor.execute("""
                    SELECT 
                        p.caja_id,
                        p.mp_pos_id,
                        p.external_id,
                        p.nombre,
                        p.categoria_mp,
                        p.monto_fijo,
                        p.qr_estatico,
                        s.mp_store_id,
                        s.external_id as store_external_id,
                        c.access_token
                    FROM mp_cajas p
                    INNER JOIN mp_sucursales s ON p.sucursal_id = s.sucursal_id
                    INNER JOIN mp_credenciales c ON s.credencial_id = c.credencial_id
                    WHERE p.external_id = ? 
                        AND p.estado = 'ACTIVO'
                        AND s.estado = 'ACTIVO'
                """, (external_pos_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'caja_id': row[0],
                    'mp_pos_id': row[1],
                    'external_id': row[2],
                    'nombre': row[3],
                    'categoria_mp': row[4],
                    'monto_fijo': row[5],
                    'qr_estatico': row[6],
                    'mp_store_id': row[7],
                    'store_external_id': row[8],
                    'access_token': row[9]
                }
            return None
            
        except Exception as e:
            log.error("Error obteniendo POS %s: %s", external_pos_id, str(e))
            return None
    
    def log_event(self, nivel: str, modulo: str, mensaje: str, 
                  external_reference: str = None, datos_adicionales: Dict = None,
                  excepcion: Exception = None):
        """
        Registra un evento en la tabla de logs
        
        Args:
            nivel: Nivel del log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            modulo: Módulo que genera el log
            mensaje: Mensaje del log
            external_reference: Referencia externa relacionada
            datos_adicionales: Datos adicionales en formato dict
            excepcion: Excepción si aplica
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Preparar datos de excepción
            exc_tipo = None
            exc_mensaje = None
            stack_trace = None
            
            if excepcion:
                exc_tipo = type(excepcion).__name__
                exc_mensaje = str(excepcion)
                import traceback
                stack_trace = traceback.format_exc()
            
            # Convertir datos adicionales a JSON usando el encoder personalizado
            datos_json = None
            if datos_adicionales:
                try:
                    # Usar el encoder personalizado para manejar Decimals
                    datos_json = json.dumps(datos_adicionales, cls=DecimalEncoder, ensure_ascii=False)
                except Exception as json_error:
                    # Si falla la serialización, convertir a string seguro
                    log.warning("Error serializando datos adicionales: %s", str(json_error))
                    datos_json = str(datos_adicionales)
            
            cursor.execute("""
                INSERT INTO mp_logs 
                (nivel, modulo, mensaje, external_reference, datos_adicionales,
                 excepcion_tipo, excepcion_mensaje, stack_trace)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (nivel, modulo, mensaje, external_reference, datos_json,
                  exc_tipo, exc_mensaje, stack_trace))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            # Si falla el log a DB, al menos loguearlo en archivo
            log.error("Error guardando log en DB: %s", str(e))
    
    def clear_cache(self):
        """Limpia toda la cache en memoria"""
        with self._cache_lock:
            self._cache.clear()
            self._last_cache_update.clear()
        log.info("Cache limpiada")


# Instancia global para uso en toda la aplicación
_db_config = None

def get_db_config() -> DatabaseConfig:
    """
    Obtiene la instancia global del configurador de base de datos
    
    Returns:
        Instancia de DatabaseConfig
    """
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config