"""
Sistema de autenticación con API Keys.
"""
import hashlib
import logging
from typing import Optional, Dict, List
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


class APIKeyManager:
    """Gestor de API Keys con SHA-256 hashing."""

    def __init__(self):
        """Inicializa el gestor de API Keys."""
        self.api_keys: Dict[str, Dict] = {}
        self._load_keys_from_env()

    def _hash_key(self, api_key: str) -> str:
        """
        Genera hash SHA-256 de una API key.

        Args:
            api_key: API key en texto plano

        Returns:
            Hash SHA-256
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    def load_keys_from_config(self, config):
        """Carga API keys desde objeto de configuración Flask."""
        keys_config = [
            {'name': 'HubPedidos', 'config_var': 'API_KEY_HUBPEDIDOS', 'permissions': ['reports:read', 'reports:generate']},
            {'name': 'Admin', 'config_var': 'API_KEY_ADMIN', 'permissions': ['reports:read', 'reports:generate', 'reports:delete', 'admin:access']},
            {'name': 'Analytics', 'config_var': 'API_KEY_ANALYTICS', 'permissions': ['reports:read']}
        ]

        for key_config in keys_config:
            # Obtener desde config object (ej. app.config)
            api_key = getattr(config, key_config['config_var'], None)
            # Fallback a dict access si es un diccionario
            if api_key is None and isinstance(config, dict):
                api_key = config.get(key_config['config_var'])
            
            if api_key:
                key_hash = self._hash_key(api_key)
                self.api_keys[key_hash] = {
                    'name': key_config['name'],
                    'permissions': key_config['permissions'],
                    'active': True
                }
                logger.info(f"✅ API Key cargada desde Config: {key_config['name']}")

        if not self.api_keys:
            logger.warning("⚠️  No se cargaron API Keys desde Config. Autenticación podría fallar.")

    def _load_keys_from_env(self):
        """(Deprecado/Fallback) Carga API keys desde variables de entorno."""
        # Se mantiene por compatibilidad pero preferimos load_keys_from_config
        pass

    def validate_key(self, api_key: str) -> Optional[Dict]:
        """
        Valida una API key.

        Args:
            api_key: API key a validar

        Returns:
            Información del cliente o None si es inválida
        """
        if not api_key:
            return None

        key_hash = self._hash_key(api_key)
        client_info = self.api_keys.get(key_hash)

        if client_info and client_info['active']:
            logger.debug(f"API Key válida: {client_info['name']}")
            return client_info

        logger.warning(f"API Key inválida: {api_key[:10]}...")
        return None

    def has_permission(self, client_info: Dict, permission: str) -> bool:
        """
        Verifica si un cliente tiene un permiso específico.

        Args:
            client_info: Información del cliente
            permission: Permiso a verificar

        Returns:
            True si tiene el permiso
        """
        if not client_info:
            return False

        return permission in client_info.get('permissions', [])


# Instancia global
api_key_manager = APIKeyManager()


def require_api_key(permission: str = None):
    """
    Decorator para requerir API Key en endpoints.

    Args:
        permission: Permiso específico requerido (opcional)

    Example:
        @app.route('/api/reportes')
        @require_api_key('reports:read')
        def get_reports():
            return {...}
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Obtener API Key del header
            api_key = request.headers.get('X-API-Key')

            if not api_key:
                logger.warning(f"Request sin API Key: {request.path}")
                return jsonify({
                    'success': False,
                    'error': 'API Key requerida',
                    'message': 'Incluya X-API-Key en los headers'
                }), 401

            # Validar API Key
            client_info = api_key_manager.validate_key(api_key)

            if not client_info:
                logger.warning(f"API Key inválida en {request.path}")
                return jsonify({
                    'success': False,
                    'error': 'API Key inválida'
                }), 401

            # Verificar permiso específico
            if permission and not api_key_manager.has_permission(client_info, permission):
                logger.warning(
                    f"Cliente {client_info['name']} sin permiso {permission} "
                    f"para {request.path}"
                )
                return jsonify({
                    'success': False,
                    'error': 'Permisos insuficientes',
                    'required_permission': permission
                }), 403

            # Guardar info del cliente en request
            request.api_client = client_info

            # Ejecutar función
            return func(*args, **kwargs)

        return wrapper

    return decorator


def optional_api_key(func):
    """
    Decorator para API Key opcional.
    Si hay API Key, la valida pero no bloquea si no hay.

    Example:
        @app.route('/public/stats')
        @optional_api_key
        def get_public_stats():
            # request.api_client estará disponible si hay API Key
            return {...}
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')

        if api_key:
            client_info = api_key_manager.validate_key(api_key)
            if client_info:
                request.api_client = client_info
            else:
                request.api_client = None
        else:
            request.api_client = None

        return func(*args, **kwargs)

    return wrapper
