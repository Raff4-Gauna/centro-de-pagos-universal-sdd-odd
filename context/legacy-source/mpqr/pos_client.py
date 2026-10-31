# mpqr/pos_client.py
import json
import uuid
import logging
from .http_client import HTTPClient
from .db_config import get_db_config
from .const import URL_CREATE_POS, URL_GET_POS

log = logging.getLogger("mpqr.pos")

class POSClient(HTTPClient):
    
    def __init__(self):
        super().__init__()
        self.db_config = get_db_config()
    
    def get_pos(self, external_pos_id: str):
        """
        Obtiene información de un POS existente usando external_id como filtro
        
        Args:
            external_pos_id: ID único del POS en tu sistema
        """
        try:
            # Primero verificar en base de datos local
            pos_info = self.db_config.get_pos_by_external_id(external_pos_id)
            
            if pos_info and pos_info['mp_pos_id'] and pos_info['mp_pos_id'] > 0:
                log.info("POS encontrado en DB local: %s (MP ID: %s)", 
                        external_pos_id, pos_info['mp_pos_id'])
            
            # Consultar en la API de MP
            params = {"external_id": external_pos_id}
            response = self._request("GET", URL_GET_POS, params=params)
            
            # La respuesta es una lista, buscamos nuestro POS
            if "results" in response and response["results"]:
                for pos in response["results"]:
                    if pos.get("external_id") == external_pos_id:
                        log.info("POS encontrado en MP: %s", external_pos_id)
                        
                        # Actualizar mp_pos_id en la DB si es necesario
                        if pos_info and (not pos_info['mp_pos_id'] or pos_info['mp_pos_id'] == 0):
                            self._update_pos_mp_id(pos_info['caja_id'], pos['id'])
                        
                        # Registrar en logs
                        self.db_config.log_event(
                            'INFO',
                            'pos_client',
                            f'POS obtenido: {external_pos_id}',
                            external_reference=external_pos_id,
                            datos_adicionales={'mp_pos_id': pos['id']}
                        )
                        
                        return pos
                        
            # Si llegamos aquí, no se encontró el POS
            raise ValueError(f"POS con external_id '{external_pos_id}' no encontrado")
            
        except Exception as e:
            log.error("Error obteniendo POS %s: %s", external_pos_id, str(e))
            self.db_config.log_event(
                'ERROR',
                'pos_client',
                f'Error obteniendo POS: {external_pos_id}',
                external_reference=external_pos_id,
                excepcion=e
            )
            raise

    def list_all_pos(self):
        """
        Lista todos los POS de la cuenta
        """
        try:
            response = self._request("GET", URL_GET_POS)
            pos_list = response.get("results", [])
            
            # Registrar en logs
            self.db_config.log_event(
                'INFO',
                'pos_client',
                f'POS listados: {len(pos_list)} encontrados',
                datos_adicionales={'count': len(pos_list)}
            )
            
            return pos_list
            
        except Exception as e:
            log.error("Error listando POS: %s", str(e))
            self.db_config.log_event(
                'ERROR',
                'pos_client',
                'Error listando POS',
                excepcion=e
            )
            raise

    def create_pos(self, external_pos_id: str, fixed_amount: bool = True):
        """
        Crea un punto de venta (POS) en MercadoPago
        
        Args:
            external_pos_id: ID único del POS en tu sistema
            fixed_amount: Si el monto es fijo o variable
        """
        try:
            # Verificar si existe en la base de datos local
            pos_info = self.db_config.get_pos_by_external_id(external_pos_id)
            
            if not pos_info:
                raise ValueError(f"POS {external_pos_id} no está configurado en la base de datos local")
            
            # Si ya tiene mp_pos_id, verificar si existe en MP
            if pos_info['mp_pos_id'] and pos_info['mp_pos_id'] > 0:
                try:
                    existing_pos = self.get_pos(external_pos_id)
                    log.warning("POS %s ya existe en MP, retornando datos existentes", external_pos_id)
                    return existing_pos
                except ValueError:
                    # No existe en MP pero sí en DB local, continuar con la creación
                    log.info("POS tiene mp_pos_id en DB pero no existe en MP, creando...")
            
            # Verificar si ya existe en MP (por si acaso)
            try:
                existing_pos = self.get_pos(external_pos_id)
                log.warning("POS %s ya existe en MP, retornando datos existentes", external_pos_id)
                return existing_pos
            except ValueError:
                # No existe, procedemos a crearlo
                pass
            
            # Usar datos de la base de datos
            body = {
                "name": pos_info['nombre'],
                "fixed_amount": fixed_amount,
                "store_id": pos_info['mp_store_id'],
                "external_store_id": pos_info['store_external_id'],
                "external_id": external_pos_id,
                "category": pos_info['categoria_mp']
            }
            
            log.info("Creando POS con datos: %s", json.dumps(body, indent=2))
            
            result = self._request("POST", URL_CREATE_POS, json=body)
            
            # Actualizar mp_pos_id en la base de datos
            if 'id' in result:
                self._update_pos_mp_id(pos_info['caja_id'], result['id'])
            
            # Registrar en logs
            self.db_config.log_event(
                'INFO',
                'pos_client',
                f'POS creado exitosamente: {external_pos_id}',
                external_reference=external_pos_id,
                datos_adicionales={
                    'mp_pos_id': result.get('id'),
                    'store_id': pos_info['mp_store_id']
                }
            )
            
            log.info("POS creado exitosamente: %s (MP ID: %s)", external_pos_id, result.get('id'))
            return result
            
        except Exception as e:
            log.error("Error creando POS %s: %s", external_pos_id, str(e))
            self.db_config.log_event(
                'ERROR',
                'pos_client',
                f'Error creando POS: {external_pos_id}',
                external_reference=external_pos_id,
                excepcion=e
            )
            raise

    def pos_exists(self, external_pos_id: str) -> bool:
        """
        Verifica si un POS existe sin lanzar excepción
        
        Args:
            external_pos_id: ID único del POS en tu sistema
            
        Returns:
            bool: True si existe, False si no
        """
        try:
            self.get_pos(external_pos_id)
            return True
        except:
            return False
    
    def _update_pos_mp_id(self, caja_id: int, mp_pos_id: int):
        """
        Actualiza el mp_pos_id en la base de datos
        
        Args:
            caja_id: ID de la caja en la DB local
            mp_pos_id: ID del POS en MercadoPago
        """
        try:
            conn = self.db_config.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE mp_cajas 
                SET mp_pos_id = ?,
                    fecha_modificacion = GETDATE(),
                    fecha_sincronizacion = GETDATE()
                WHERE caja_id = ?
            """, (mp_pos_id, caja_id))
            
            conn.commit()
            conn.close()
            
            log.info("mp_pos_id actualizado para caja_id %s: %s", caja_id, mp_pos_id)
            
        except Exception as e:
            log.error("Error actualizando mp_pos_id: %s", str(e))
            raise
    
    def sync_all_pos_with_mp(self):
        """
        Sincroniza todos los POS locales con MercadoPago
        Útil para mantener la base de datos actualizada
        """
        try:
            # Obtener todos los POS de la DB local
            conn = self.db_config.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.external_id, p.nombre, p.mp_pos_id
                FROM mp_cajas p
                INNER JOIN mp_sucursales s ON p.sucursal_id = s.sucursal_id
                WHERE p.estado = 'ACTIVO' AND s.estado = 'ACTIVO'
            """)
            
            local_pos_list = cursor.fetchall()
            conn.close()
            
            # Obtener todos los POS de MP
            mp_pos_list = self.list_all_pos()
            
            sync_results = {
                'created': 0,
                'updated': 0,
                'errors': 0
            }
            
            for local_pos in local_pos_list:
                external_id = local_pos[0]
                nombre = local_pos[1]
                mp_pos_id = local_pos[2]
                
                try:
                    # Buscar en la lista de MP
                    mp_pos = None
                    for pos in mp_pos_list:
                        if pos.get('external_id') == external_id:
                            mp_pos = pos
                            break
                    
                    if mp_pos:
                        # Existe en MP, actualizar ID si es necesario
                        if not mp_pos_id or mp_pos_id != mp_pos['id']:
                            pos_info = self.db_config.get_pos_by_external_id(external_id)
                            self._update_pos_mp_id(pos_info['caja_id'], mp_pos['id'])
                            sync_results['updated'] += 1
                            log.info("POS %s sincronizado (MP ID: %s)", external_id, mp_pos['id'])
                    else:
                        # No existe en MP, crearlo
                        log.info("POS %s no existe en MP, creando...", external_id)
                        self.create_pos(external_id)
                        sync_results['created'] += 1
                        
                except Exception as e:
                    log.error("Error sincronizando POS %s: %s", external_id, str(e))
                    sync_results['errors'] += 1
            
            # Registrar resultado de sincronización
            self.db_config.log_event(
                'INFO',
                'pos_client',
                'Sincronización de POS completada',
                datos_adicionales=sync_results
            )
            
            return sync_results
            
        except Exception as e:
            log.error("Error en sincronización masiva: %s", str(e))
            self.db_config.log_event(
                'ERROR',
                'pos_client',
                'Error en sincronización masiva de POS',
                excepcion=e
            )
            raise