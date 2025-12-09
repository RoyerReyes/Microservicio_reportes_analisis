"""
Gestor de caché usando Redis con fallback a memoria.
"""
import json
import logging
import hashlib
from typing import Optional, Any, Dict
from datetime import timedelta

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    RedisError = Exception
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Gestor de caché con Redis y fallback a memoria.
    Implementa Circuit Breaker para Redis.
    """

    def __init__(self, redis_url: str, enabled: bool = True, default_ttl: int = 300):
        """
        Inicializa el gestor de caché.

        Args:
            redis_url: URL de conexión a Redis
            enabled: Si el caché está habilitado
            default_ttl: TTL por defecto en segundos
        """
        self.redis_url = redis_url
        self.enabled = enabled
        self.default_ttl = default_ttl
        self.redis_client: Optional[redis.Redis] = None
        self.memory_cache: Dict[str, Any] = {}

        # Circuit Breaker
        self.circuit_open = False
        self.failure_count = 0
        self.failure_threshold = 3

        # Métricas
        self.hits = 0
        self.misses = 0
        self.sets = 0

        if self.enabled and REDIS_AVAILABLE:
            self._connect_redis()
        else:
            logger.warning("⚠️ Caché usando memoria (Redis no disponible o deshabilitado)")

    def _connect_redis(self):
        """Intenta conectar a Redis."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test conexión
            self.redis_client.ping()
            logger.info(f"✅ Conectado a Redis: {self.redis_url}")
        except (RedisError, Exception) as e:
            logger.warning(f"⚠️ No se pudo conectar a Redis: {e}. Usando memoria.")
            self.redis_client = None

    def _handle_failure(self):
        """Maneja un fallo de Redis."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.circuit_open = True
            logger.error("🔴 Circuit Breaker del caché ABIERTO")

    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """
        Genera una clave de caché única basada en parámetros.

        Args:
            prefix: Prefijo de la clave (ej: 'report:sales')
            **kwargs: Parámetros para generar la clave única

        Returns:
            Clave de caché única
        """
        # Ordenar kwargs para consistencia
        params_str = json.dumps(kwargs, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"{prefix}:{params_hash}"

    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor del caché.

        Args:
            key: Clave del caché

        Returns:
            Valor cacheado o None si no existe
        """
        if not self.enabled:
            return None

        # Intentar Redis primero
        if self.redis_client and not self.circuit_open:
            try:
                value = self.redis_client.get(key)
                if value:
                    self.hits += 1
                    logger.debug(f"Cache HIT (Redis): {key}")
                    return json.loads(value)
                else:
                    self.misses += 1
                    logger.debug(f"Cache MISS (Redis): {key}")
                    return None
            except RedisError as e:
                logger.error(f"Error obteniendo de Redis: {e}")
                self._handle_failure()

        # Fallback a memoria
        if key in self.memory_cache:
            self.hits += 1
            logger.debug(f"Cache HIT (Memory): {key}")
            return self.memory_cache[key]

        self.misses += 1
        logger.debug(f"Cache MISS (Memory): {key}")
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Guarda un valor en el caché.

        Args:
            key: Clave del caché
            value: Valor a guardar (debe ser JSON-serializable)
            ttl: TTL en segundos (usa default_ttl si es None)

        Returns:
            True si se guardó exitosamente
        """
        if not self.enabled:
            return False

        ttl = ttl or self.default_ttl

        # Intentar Redis primero
        if self.redis_client and not self.circuit_open:
            try:
                value_json = json.dumps(value)
                self.redis_client.setex(key, ttl, value_json)
                self.sets += 1
                logger.debug(f"Cache SET (Redis): {key}, TTL={ttl}s")
                return True
            except (RedisError, TypeError) as e:
                logger.error(f"Error guardando en Redis: {e}")
                self._handle_failure()

        # Fallback a memoria (sin TTL real en memoria por simplicidad)
        try:
            self.memory_cache[key] = value
            self.sets += 1
            logger.debug(f"Cache SET (Memory): {key}")
            return True
        except Exception as e:
            logger.error(f"Error guardando en memoria: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Elimina una clave del caché.

        Args:
            key: Clave a eliminar

        Returns:
            True si se eliminó
        """
        deleted = False

        if self.redis_client and not self.circuit_open:
            try:
                self.redis_client.delete(key)
                deleted = True
            except RedisError as e:
                logger.error(f"Error eliminando de Redis: {e}")

        if key in self.memory_cache:
            del self.memory_cache[key]
            deleted = True

        return deleted

    def delete_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coincidan con un patrón.

        Args:
            pattern: Patrón de claves (ej: 'report:*')

        Returns:
            Número de claves eliminadas
        """
        count = 0

        if self.redis_client and not self.circuit_open:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    count = self.redis_client.delete(*keys)
                    logger.info(f"Eliminadas {count} claves de Redis: {pattern}")
            except RedisError as e:
                logger.error(f"Error eliminando patrón de Redis: {e}")

        # Memoria: eliminar claves que coincidan con el patrón
        # Convertir patrón Redis a regex simple
        import re
        regex_pattern = pattern.replace('*', '.*').replace('?', '.')
        keys_to_delete = [k for k in self.memory_cache.keys() if re.match(regex_pattern, k)]

        for key in keys_to_delete:
            del self.memory_cache[key]
            count += 1

        return count

    def invalidate_reports(self):
        """Invalida todos los reportes cacheados."""
        count = self.delete_pattern('report:*')
        logger.info(f"Invalidados {count} reportes cacheados")

    def get_hit_rate(self) -> float:
        """Calcula la tasa de aciertos del caché."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return round(self.hits / total, 2)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del caché."""
        return {
            'enabled': self.enabled,
            'using_redis': self.redis_client is not None and not self.circuit_open,
            'circuit_open': self.circuit_open,
            'hits': self.hits,
            'misses': self.misses,
            'sets': self.sets,
            'hit_rate': self.get_hit_rate(),
            'memory_cache_size': len(self.memory_cache)
        }

    def is_connected(self) -> bool:
        """Verifica si Redis está conectado."""
        if not self.redis_client or self.circuit_open:
            return False

        try:
            self.redis_client.ping()
            return True
        except RedisError:
            return False

    def cleanup(self):
        """Limpia recursos."""
        if self.redis_client:
            try:
                self.redis_client.close()
                logger.info("Redis conexión cerrada")
            except Exception as e:
                logger.error(f"Error cerrando Redis: {e}")

        self.memory_cache.clear()
        logger.info("CacheManager cleanup completado")
