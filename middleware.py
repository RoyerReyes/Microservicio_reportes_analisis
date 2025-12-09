"""
Middleware para logging, métricas y manejo de errores.
"""
import time
import uuid
import logging
from flask import Flask, request, g, has_request_context
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from functools import wraps

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    Limiter = None
    LIMITER_AVAILABLE = False

logger = logging.getLogger(__name__)

# ===== Prometheus Metrics =====
REQUEST_COUNT = Counter(
    'reportes_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'reportes_http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

REPORT_GENERATION_TIME = Histogram(
    'reportes_generation_duration_seconds',
    'Report generation time',
    ['report_type', 'format']
)

CACHE_HITS = Counter(
    'reportes_cache_hits_total',
    'Cache hits',
    ['cache_type']
)

CACHE_MISSES = Counter(
    'reportes_cache_misses_total',
    'Cache misses',
    ['cache_type']
)

DATABASE_QUERIES = Counter(
    'reportes_database_queries_total',
    'Database queries executed',
    ['query_type']
)

ACTIVE_REQUESTS = Gauge(
    'reportes_active_requests',
    'Active requests'
)


# ===== Request Context Filter =====
class RequestContextFilter(logging.Filter):
    """Filtro para agregar request_id a logs."""

    def filter(self, record):
        try:
            if has_request_context():
                record.request_id = getattr(g, 'request_id', 'N/A')
            else:
                record.request_id = 'INIT'
        except:
            record.request_id = 'N/A'
        return True


def setup_logging(config):
    """
    Configura logging estructurado.

    Args:
        config: Objeto de configuración
    """
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    # Formato
    formatter = logging.Formatter(config.LOG_FORMAT)

    # Handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = []
    root_logger.addHandler(handler)

    logger.info(f"✅ Logging configurado: nivel={config.LOG_LEVEL}")


def request_logging_middleware(app: Flask):
    """
    Middleware para logging de requests.

    Args:
        app: Instancia de Flask
    """

    @app.before_request
    def before_request():
        """Ejecuta antes de cada request."""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()

        ACTIVE_REQUESTS.inc()

        logger.info(
            f"→ {request.method} {request.path} "
            f"from {request.remote_addr}"
        )

    @app.after_request
    def after_request(response):
        """Ejecuta después de cada request."""
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time

            # Metrics
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.endpoint or 'unknown',
                status=response.status_code
            ).inc()

            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.endpoint or 'unknown'
            ).observe(duration)

            ACTIVE_REQUESTS.dec()

            logger.info(
                f"← {request.method} {request.path} "
                f"{response.status_code} {duration*1000:.2f}ms"
            )

        return response

    logger.info("✅ Request logging middleware configurado")


def setup_error_handlers(app: Flask):
    """
    Configura manejadores de errores.

    Args:
        app: Instancia de Flask
    """

    @app.errorhandler(404)
    def not_found(error):
        """Handler para 404."""
        logger.warning(f"404: {request.path}")
        return {
            'success': False,
            'error': 'Endpoint no encontrado',
            'path': request.path
        }, 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handler para 500."""
        logger.error(f"500: {error}", exc_info=True)
        return {
            'success': False,
            'error': 'Error interno del servidor'
        }, 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handler genérico."""
        logger.error(f"Excepción no manejada: {error}", exc_info=True)
        return {
            'success': False,
            'error': str(error)
        }, 500

    logger.info("✅ Error handlers configurados")


def create_limiter(app: Flask, config) -> Limiter:
    """
    Crea el rate limiter.

    Args:
        app: Instancia de Flask
        config: Configuración

    Returns:
        Instancia de Limiter o None
    """
    if not config.RATELIMIT_ENABLED or not LIMITER_AVAILABLE:
        logger.info("⚠️  Rate limiting deshabilitado")
        return None

    try:
        storage_uri = config.RATELIMIT_STORAGE_URL if config.REDIS_ENABLED else None

        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[config.RATELIMIT_DEFAULT],
            storage_uri=storage_uri,
            storage_options={"socket_connect_timeout": 5} if storage_uri else {}
        )

        logger.info(f"✅ Rate limiting configurado: {config.RATELIMIT_DEFAULT}")
        return limiter

    except Exception as e:
        logger.error(f"Error configurando rate limiter: {e}")
        logger.info("Rate limiting deshabilitado debido a error")
        return None


def track_report_generation(report_type: str, format: str):
    """
    Decorator para trackear generación de reportes.

    Args:
        report_type: Tipo de reporte
        format: Formato de salida

    Example:
        @track_report_generation('ventas', 'pdf')
        def generate_sales_pdf():
            pass
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                REPORT_GENERATION_TIME.labels(
                    report_type=report_type,
                    format=format
                ).observe(duration)

                logger.info(f"Reporte generado: {report_type}.{format} en {duration*1000:.2f}ms")
                return result

            except Exception as e:
                logger.error(f"Error generando reporte {report_type}.{format}: {e}")
                raise

        return wrapper

    return decorator
