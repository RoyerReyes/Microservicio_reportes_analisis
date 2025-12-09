"""
Configuración centralizada del servicio de reportes.
Maneja configuración por entorno (development, testing, production).
"""
import os
from typing import List


class Config:
    """Configuración base compartida por todos los entornos."""

    # App Info
    APP_NAME: str = os.getenv('APP_NAME', 'Reportes Service Premium')
    APP_VERSION: str = os.getenv('APP_VERSION', '2.0.0')

    # Flask
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV: str = os.getenv('FLASK_ENV', 'development')

    # Server
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', 5001))
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'

    # Database
    DB_TYPE: str = os.getenv('DB_TYPE', 'mysql')  # mysql o sqlite
    DB_HOST: str = os.getenv('DB_HOST', '127.0.0.1')
    DB_PORT: int = int(os.getenv('DB_PORT', 3306))
    DB_USER: str = os.getenv('DB_USER', 'root')
    DB_PASSWORD: str = os.getenv('DB_PASSWORD', '')
    DB_NAME: str = os.getenv('DB_NAME', 'hubpedidos_db')
    DB_POOL_SIZE: int = int(os.getenv('DB_POOL_SIZE', 5))
    DB_POOL_NAME: str = os.getenv('DB_POOL_NAME', 'reportes_pool')

    # SQLite (fallback)
    SQLITE_DB_PATH: str = os.getenv('SQLITE_DB_PATH', '../HubPedidos/db.sqlite3')

    # Redis / Cache
    REDIS_URL: str = os.getenv('REDIS_URL', 'redis://localhost:6379/1')
    REDIS_ENABLED: bool = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'
    CACHE_ENABLED: bool = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
    CACHE_DEFAULT_TTL: int = int(os.getenv('CACHE_DEFAULT_TTL', 300))  # 5 minutos

    # CORS
    CORS_ALLOWED_ORIGINS: List[str] = [
        o.strip() for o in os.getenv(
            'CORS_ALLOWED_ORIGINS',
            'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000'
        ).split(',')
    ]

    # Rate Limiting
    RATELIMIT_ENABLED: bool = os.getenv('RATELIMIT_ENABLED', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URL: str = os.getenv('RATELIMIT_STORAGE_URL', REDIS_URL)
    RATELIMIT_DEFAULT: str = os.getenv('RATELIMIT_DEFAULT', '200 per day;50 per hour')

    # API Authentication
    API_AUTH_ENABLED: bool = os.getenv('API_AUTH_ENABLED', 'false').lower() == 'true'
    API_KEY_HUBPEDIDOS: str = os.getenv('API_KEY_HUBPEDIDOS', 'hub_reportes_9x4m7n2p8k5w1')
    API_KEY_ADMIN: str = os.getenv('API_KEY_ADMIN', '')
    API_KEY_ANALYTICS: str = os.getenv('API_KEY_ANALYTICS', '')

    # JWT (para autenticación futura)
    JWT_SECRET: str = os.getenv('JWT_SECRET', SECRET_KEY)
    JWT_ALGORITHM: str = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_EXPIRATION_HOURS: int = int(os.getenv('JWT_EXPIRATION_HOURS', 24))

    # Reportes
    REPORT_MAX_ROWS: int = int(os.getenv('REPORT_MAX_ROWS', 10000))
    REPORT_PAGE_SIZE: int = int(os.getenv('REPORT_PAGE_SIZE', 50))
    REPORT_CACHE_TTL: int = int(os.getenv('REPORT_CACHE_TTL', 600))  # 10 minutos

    # PDF Generation
    PDF_LOGO_PATH: str = os.getenv('PDF_LOGO_PATH', '')
    PDF_COMPANY_NAME: str = os.getenv('PDF_COMPANY_NAME', 'SOA Minimarket')
    PDF_INCLUDE_CHARTS: bool = os.getenv('PDF_INCLUDE_CHARTS', 'true').lower() == 'true'

    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = os.getenv(
        'LOG_FORMAT',
        '[%(asctime)s] [%(request_id)s] %(levelname)s in %(module)s: %(message)s'
    )

    # Metrics
    METRICS_ENABLED: bool = os.getenv('METRICS_ENABLED', 'true').lower() == 'true'
    METRICS_PORT: int = int(os.getenv('METRICS_PORT', PORT))

    # Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', 5))
    CIRCUIT_BREAKER_TIMEOUT: int = int(os.getenv('CIRCUIT_BREAKER_TIMEOUT', 60))


class DevelopmentConfig(Config):
    """Configuración para entorno de desarrollo."""
    DEBUG: bool = True
    LOG_LEVEL: str = 'DEBUG'

    # Cache desactivado en desarrollo para ver cambios en tiempo real
    CACHE_ENABLED: bool = False
    CACHE_DEFAULT_TTL: int = 60  # 1 minuto si se habilita

    # Rate limiting más permisivo
    RATELIMIT_DEFAULT: str = '1000 per day;200 per hour'


class TestingConfig(Config):
    """Configuración para tests."""
    TESTING: bool = True
    DEBUG: bool = False

    # Usar SQLite en memoria para tests
    DB_TYPE: str = 'sqlite'
    SQLITE_DB_PATH: str = ':memory:'

    # Desactivar servicios externos
    REDIS_ENABLED: bool = False
    CACHE_ENABLED: bool = False
    RATELIMIT_ENABLED: bool = False
    METRICS_ENABLED: bool = False

    # Autenticación desactivada para tests
    API_AUTH_ENABLED: bool = False

    # Límites bajos para tests rápidos
    REPORT_MAX_ROWS: int = 100
    REPORT_PAGE_SIZE: int = 10


class ProductionConfig(Config):
    """Configuración para producción."""
    DEBUG: bool = False
    TESTING: bool = False

    # Seguridad estricta
    API_AUTH_ENABLED: bool = True
    RATELIMIT_ENABLED: bool = True

    # Cache agresivo
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 600  # 10 minutos
    REPORT_CACHE_TTL: int = 1800  # 30 minutos

    # Logging menos verboso
    LOG_LEVEL: str = 'WARNING'

    # Rate limiting estricto
    RATELIMIT_DEFAULT: str = '100 per day;20 per hour'

    # Circuit breaker más conservador
    CIRCUIT_BREAKER_THRESHOLD: int = 3
    CIRCUIT_BREAKER_TIMEOUT: int = 120


# Diccionario de configuraciones
config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(env: str = None) -> Config:
    """
    Obtiene la configuración basada en el entorno.

    Args:
        env: Nombre del entorno ('development', 'testing', 'production')
            Si es None, usa FLASK_ENV de variables de entorno

    Returns:
        Instancia de configuración correspondiente
    """
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    config_class = config_by_name.get(env, DevelopmentConfig)
    return config_class()


def validate_config(config: Config) -> bool:
    """
    Valida que la configuración tenga todos los valores necesarios.

    Args:
        config: Instancia de configuración a validar

    Returns:
        True si la configuración es válida

    Raises:
        ValueError: Si falta algún valor crítico
    """
    # Validar que el SECRET_KEY no sea el default en producción
    if config.FLASK_ENV == 'production' and config.SECRET_KEY == 'dev-secret-key-change-in-production':
        raise ValueError("SECRET_KEY debe ser configurado en producción")

    # Validar DB config si es MySQL
    if config.DB_TYPE == 'mysql':
        if not config.DB_HOST or not config.DB_USER or not config.DB_NAME:
            raise ValueError("DB_HOST, DB_USER y DB_NAME son requeridos para MySQL")

    # Validar API Keys si auth está habilitado
    if config.API_AUTH_ENABLED:
        if not config.API_KEY_HUBPEDIDOS and not config.API_KEY_ADMIN:
            raise ValueError("Al menos un API Key debe estar configurado")

    return True
