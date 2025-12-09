"""
Gestor de base de datos con pool de conexiones y Circuit Breaker.
Soporta MySQL y SQLite con failover automático.
"""
import os
import time
import sqlite3
import logging
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

try:
    import mysql.connector
    from mysql.connector import pooling, Error as MySQLError
    MYSQL_AVAILABLE = True
except ImportError:
    mysql = None
    pooling = None
    MySQLError = Exception
    MYSQL_AVAILABLE = False

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Excepción cuando el Circuit Breaker está abierto."""
    pass


class DatabaseManager:
    """
    Gestor de conexiones a base de datos con:
    - Pool de conexiones (MySQL)
    - Circuit Breaker para resiliencia
    - Soporte para MySQL y SQLite
    - Retry logic automático
    - Query logging
    """

    def __init__(self, config):
        """
        Inicializa el gestor de base de datos.

        Args:
            config: Objeto de configuración con parámetros de DB
        """
        self.config = config
        self.db_type = config.DB_TYPE
        self.pool: Optional[pooling.MySQLConnectionPool] = None
        self.sqlite_path: Optional[str] = None

        # Circuit Breaker state
        self.circuit_open = False
        self.failure_count = 0
        self.failure_threshold = config.CIRCUIT_BREAKER_THRESHOLD
        self.circuit_timeout = config.CIRCUIT_BREAKER_TIMEOUT
        self.last_failure_time = None

        # Métricas
        self.queries_executed = 0
        self.slow_queries = 0
        self.errors = 0

        self._initialize_connection()

    def _initialize_connection(self):
        """Inicializa la conexión según el tipo de DB."""
        if self.db_type == 'mysql':
            self._initialize_mysql_pool()
        else:
            self._initialize_sqlite()

    def _initialize_mysql_pool(self):
        """Inicializa el pool de conexiones MySQL."""
        logger.warning(f"DEBUG: Intentando init MySQL. Config: {self.config.DB_HOST}")
        # FORZAR ERROR PARA DIAGNÓSTICO E INMEDIATO FALLBACK
        # raise Exception("DEBUG: Forzando fallo MySQL para usar SQLite") 
        # (Comentado para probar el catch real primero, pero si falla de nuevo, descomentar)
        
        if not MYSQL_AVAILABLE:
            logger.error("mysql-connector-python no está instalado. Fallback a SQLite.")
            self.db_type = 'sqlite'
            self._initialize_sqlite()
            return

        try:
            db_config = {
                'host': self.config.DB_HOST,
                'port': self.config.DB_PORT,
                'user': self.config.DB_USER,
                'password': self.config.DB_PASSWORD,
                'database': self.config.DB_NAME,
                'autocommit': False,
            }

            self.pool = pooling.MySQLConnectionPool(
                pool_name=self.config.DB_POOL_NAME,
                pool_size=self.config.DB_POOL_SIZE,
                pool_reset_session=True,
                **db_config
            )

            # Test conexión
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()  # Consumir el resultado para evitar "Unread result found"
            cursor.close()
            conn.close()

            logger.info(f"✅ Pool MySQL inicializado: {self.config.DB_HOST}:{self.config.DB_PORT}/{self.config.DB_NAME}")
            logger.info("✅ MySQL SELECT 1 exitoso")

        except Exception as e:
            logger.error(f"❌ Error inicializando pool MySQL (o fallo en test de conexión): {e}")
            logger.info("⚠️ Forzando Fallback a SQLite debido a error en arranque MySQL...")
            self.db_type = 'sqlite'
            self._initialize_sqlite()

    def _initialize_sqlite(self):
        """Inicializa SQLite."""
        db_path = self.config.SQLITE_DB_PATH

        # Si es :memory:, usamos memoria
        if db_path == ':memory:':
            self.sqlite_path = ':memory:'
            logger.info("✅ Usando SQLite en memoria (testing)")
            return

        # Si no existe el path, intentar encontrar HubPedidos/db.sqlite3
        if not os.path.exists(db_path):
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            root_dir = os.path.dirname(current_dir)
            fallback_path = os.path.join(root_dir, 'HubPedidos', 'db.sqlite3')

            if os.path.exists(fallback_path):
                db_path = fallback_path
                logger.info(f"Usando DB de HubPedidos: {fallback_path}")
            else:
                logger.warning(f"⚠️ No se encontró base de datos en {db_path} ni {fallback_path}")

        self.sqlite_path = db_path
        logger.info(f"✅ Usando SQLite: {self.sqlite_path}")

    def _handle_failure(self):
        """Maneja un fallo de conexión para el Circuit Breaker."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.errors += 1

        if self.failure_count >= self.failure_threshold:
            self.circuit_open = True
            logger.error(f"🔴 Circuit Breaker ABIERTO tras {self.failure_count} fallos")

    def _check_circuit_breaker(self):
        """Verifica si el Circuit Breaker debe cerrarse."""
        if not self.circuit_open:
            return

        # Verificar si pasó el timeout
        if self.last_failure_time and (time.time() - self.last_failure_time) > self.circuit_timeout:
            logger.info("🟡 Intentando cerrar Circuit Breaker...")
            self.circuit_open = False
            self.failure_count = 0

    @contextmanager
    def get_connection(self):
        """
        Context manager para obtener una conexión a la DB.

        Yields:
            Conexión a la base de datos

        Raises:
            CircuitBreakerError: Si el Circuit Breaker está abierto
            RuntimeError: Si hay error de conexión

        Example:
            >>> with db_manager.get_connection() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("SELECT * FROM tabla")
        """
        self._check_circuit_breaker()

        if self.circuit_open:
            raise CircuitBreakerError("Circuit Breaker está abierto. DB no disponible.")

        conn = None
        try:
            if self.db_type == 'mysql':
                conn = self.pool.get_connection()
            else:
                conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row  # Para acceder a columnas por nombre

            yield conn

            # Si hubo éxito, resetear failure count
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)

        except (MySQLError, sqlite3.Error) as e:
            self._handle_failure()
            logger.error(f"Error en conexión DB: {e}")
            raise RuntimeError(f"Error de base de datos: {e}")

        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error cerrando conexión: {e}")

    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Ejecuta una query y retorna los resultados.

        Args:
            query: Query SQL a ejecutar
            params: Parámetros para la query (usa placeholders)
            fetch_one: Si True, retorna solo un resultado
            fetch_all: Si True, retorna todos los resultados (default)

        Returns:
            Lista de diccionarios con los resultados, o None si no hay

        Example:
            >>> results = db.execute_query(
            ...     "SELECT * FROM pedidos WHERE id = ?",
            ...     (123,)
            ... )
        """
        start_time = time.time()

        try:
            with self.get_connection() as conn:
                # Ajustar placeholders según el tipo de DB
                if self.db_type == 'mysql':
                    query = query.replace('?', '%s')
                    cursor = conn.cursor(dictionary=True)
                else:
                    cursor = conn.cursor()

                # Ejecutar query
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # Fetch results
                if fetch_one:
                    result = cursor.fetchone()
                    results = [dict(result)] if result else []
                elif fetch_all:
                    rows = cursor.fetchall()
                    results = [dict(row) for row in rows]
                else:
                    results = []

                cursor.close()

                # Métricas
                execution_time = (time.time() - start_time) * 1000
                self.queries_executed += 1

                if execution_time > 1000:  # > 1 segundo
                    self.slow_queries += 1
                    logger.warning(f"⚠️ Query lenta ({execution_time:.2f}ms): {query[:100]}")
                else:
                    logger.debug(f"Query ejecutada en {execution_time:.2f}ms")

                return results

        except Exception as e:
            logger.error(f"Error ejecutando query: {e}\nQuery: {query}")
            raise

    def execute_update(
        self,
        query: str,
        params: Optional[Tuple] = None,
        commit: bool = True
    ) -> int:
        """
        Ejecuta una query de UPDATE/INSERT/DELETE.

        Args:
            query: Query SQL
            params: Parámetros
            commit: Si True, hace commit automático

        Returns:
            Número de filas afectadas
        """
        try:
            with self.get_connection() as conn:
                if self.db_type == 'mysql':
                    query = query.replace('?', '%s')

                cursor = conn.cursor()

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                affected_rows = cursor.rowcount

                if commit:
                    conn.commit()

                cursor.close()

                self.queries_executed += 1
                logger.debug(f"Update ejecutado: {affected_rows} filas afectadas")

                return affected_rows

        except Exception as e:
            logger.error(f"Error en execute_update: {e}")
            raise

    @contextmanager
    def transaction(self):
        """
        Context manager para transacciones.

        Example:
            >>> with db_manager.transaction() as conn:
            ...     cursor = conn.cursor()
            ...     cursor.execute("INSERT INTO ...")
            ...     cursor.execute("UPDATE ...")
            ...     # Auto-commit si no hay excepciones
        """
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
                logger.debug("Transacción committed")
            except Exception as e:
                conn.rollback()
                logger.error(f"Transacción rolled back: {e}")
                raise

    def is_connected(self) -> bool:
        """Verifica si la conexión está activa."""
        if self.circuit_open:
            return False

        try:
            with self.get_connection() as conn:
                if self.db_type == 'mysql':
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                else:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                cursor.close()
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del DatabaseManager."""
        return {
            'db_type': self.db_type,
            'connected': self.is_connected(),
            'circuit_open': self.circuit_open,
            'failure_count': self.failure_count,
            'queries_executed': self.queries_executed,
            'slow_queries': self.slow_queries,
            'errors': self.errors,
            'pool_size': self.config.DB_POOL_SIZE if self.db_type == 'mysql' else 'N/A'
        }

    def cleanup(self):
        """Limpia recursos."""
        if self.pool:
            # MySQL connection pool no tiene método close() global
            logger.info("MySQL pool limpiado (conexiones se cierran automáticamente)")
        logger.info("DatabaseManager cleanup completado")
