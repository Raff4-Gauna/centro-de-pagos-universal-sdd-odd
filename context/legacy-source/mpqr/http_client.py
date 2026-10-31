# mpqr/http_client.py
import logging
import requests
import time
from .db_config import get_db_config
from .const import BASE_URL

log = logging.getLogger("mpqr")

class HTTPClient:
    def __init__(self):
        # Obtener instancia del configurador de base de datos
        self.db_config = get_db_config()
        
        # Obtener credenciales activas desde la base de datos
        credentials = self.db_config.get_active_credentials()
        
        if not credentials:
            raise ValueError("No hay credenciales activas configuradas en la base de datos")
        
        self.token = credentials['access_token']
        
        if not self.token:
            raise ValueError("ACCESS_TOKEN no encontrado en las credenciales activas")
        
        # Log para debugging
        log.debug(f"HTTPClient inicializado con token del entorno: {credentials['nombre_entorno']}")
        log.debug(f"Usuario ID: {credentials['user_id']}")
        log.debug(f"Es Sandbox: {'Sí' if credentials['es_sandbox'] else 'No'}")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def _request(self, method: str, url: str, **kw):
        t0 = time.perf_counter()
        full_url = BASE_URL + url
        
        # Log de la request para debugging
        params = kw.get('params', {})
        param_str = f"?{requests.compat.urlencode(params)}" if params else ""
        log.debug("MP Request: %s %s%s", method.upper(), url, param_str)
        
        # Registrar en base de datos el inicio de la petición
        self.db_config.log_event(
            'DEBUG',
            'http_client',
            f'MP Request: {method.upper()} {url}{param_str}',
            datos_adicionales={
                'method': method,
                'url': url,
                'params': params
            }
        )
        
        try:
            resp = requests.request(method, full_url, headers=self._headers(), **kw)
            elapsed_time = time.perf_counter() - t0
            
            log.debug("MP %s %s → %s (%.3fs)", method.upper(), url, resp.status_code, elapsed_time)
            
            # Registrar respuesta en base de datos
            self.db_config.log_event(
                'INFO' if resp.status_code < 400 else 'ERROR',
                'http_client',
                f'MP Response: {method.upper()} {url} → {resp.status_code} ({elapsed_time:.3f}s)',
                datos_adicionales={
                    'status_code': resp.status_code,
                    'elapsed_time': elapsed_time,
                    'response_size': len(resp.content) if resp.content else 0
                }
            )
            
            if resp.status_code >= 400:
                log.error("MP Error %s: %s", resp.status_code, resp.text)
                
                # Registrar error en base de datos
                self.db_config.log_event(
                    'ERROR',
                    'http_client',
                    f'MP Error {resp.status_code}',
                    datos_adicionales={
                        'error_response': resp.text[:1000] if resp.text else None  # Limitar tamaño
                    }
                )
            
            resp.raise_for_status()
            return resp.json() if resp.content else {}
            
        except requests.RequestException as e:
            log.error("Request failed: %s", str(e))
            
            # Registrar excepción en base de datos
            self.db_config.log_event(
                'ERROR',
                'http_client',
                f'Request failed: {str(e)}',
                excepcion=e
            )
            
            raise RuntimeError(f"Error de conexión con MercadoPago: {str(e)}") from e
            
        except ValueError as e:  # JSON decode error
            log.error("Invalid JSON response: %s", resp.text)
            
            # Registrar error de JSON en base de datos
            self.db_config.log_event(
                'ERROR',
                'http_client',
                'Invalid JSON response',
                datos_adicionales={
                    'response_text': resp.text[:1000] if resp.text else None
                },
                excepcion=e
            )
            
            raise RuntimeError(f"Respuesta inválida de MercadoPago: {resp.text}") from e

    def refresh_token(self):
        """
        Método para refrescar el token desde la base de datos
        Útil si las credenciales cambian durante la ejecución
        """
        credentials = self.db_config.get_active_credentials()
        
        if not credentials:
            raise ValueError("No hay credenciales activas después de refrescar")
        
        old_token = self.token
        self.token = credentials['access_token']
        
        if old_token != self.token:
            log.info("Token actualizado desde base de datos")
            self.db_config.log_event(
                'INFO',
                'http_client',
                'Token actualizado desde base de datos',
                datos_adicionales={
                    'entorno': credentials['nombre_entorno']
                }
            )