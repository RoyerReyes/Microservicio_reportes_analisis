"""
Aplicación principal del servicio de reportes - Versión 2.0
Arquitectura modular con mejores prácticas y observabilidad.
"""
import os
import time
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pydantic import ValidationError
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from config import get_config, validate_config
from models import (
    ReportRequest, ReportFormat, HealthCheckResponse,
    DatabaseHealth, CacheHealth, ErrorResponse
)
from services import DatabaseManager, CacheManager, ReportService
from services.pdf_generator import PDFGenerator
from services.excel_generator import ExcelGenerator
from middleware import (
    setup_logging, request_logging_middleware,
    setup_error_handlers, create_limiter
)
from api_auth import require_api_key, optional_api_key

logger = logging.getLogger(__name__)

# Tiempo de inicio para uptime
START_TIME = time.time()


def create_app(config_name: str = None):
    """
    Factory de la aplicación Flask.

    Args:
        config_name: Nombre del entorno ('development', 'testing', 'production')

    Returns:
        Instancia de Flask configurada
    """
    # ===== Configuración =====
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    config = get_config(config_name)

    try:
        validate_config(config)
    except ValueError as e:
        raise RuntimeError(f"Configuración inválida: {e}")

    logger_temp = logging.getLogger(__name__)
    logger_temp.info(f"🚀 Iniciando Reportes Service v2.0 - Entorno: {config_name}")

    # ===== Flask App =====
    app = Flask(__name__)
    app.config.from_object(config)

    # ===== Logging =====
    setup_logging(config)

    # ===== Auth Init =====
    from api_auth import api_key_manager
    api_key_manager.load_keys_from_config(config)

    # ===== CORS =====
    if config.CORS_ALLOWED_ORIGINS:
        CORS(
            app,
            resources={r"/*": {"origins": config.CORS_ALLOWED_ORIGINS}},
            supports_credentials=True
        )
        logger.info(f"✅ CORS configurado: {config.CORS_ALLOWED_ORIGINS}")
    else:
        logger.warning("⚠️  CORS no configurado")

    # ===== Database Manager =====
    db_manager = DatabaseManager(config)

    # ===== Cache Manager =====
    cache_manager = CacheManager(
        redis_url=config.REDIS_URL,
        enabled=config.CACHE_ENABLED,
        default_ttl=config.CACHE_DEFAULT_TTL
    )

    # ===== Report Service =====
    report_service = ReportService(db_manager, cache_manager)

    # ===== Generators =====
    pdf_generator = PDFGenerator(
        company_name=config.PDF_COMPANY_NAME,
        logo_path=config.PDF_LOGO_PATH
    )

    excel_generator = ExcelGenerator(company_name=config.PDF_COMPANY_NAME)

    # ===== Middleware =====
    request_logging_middleware(app)
    setup_error_handlers(app)

    # Rate Limiting
    limiter = create_limiter(app, config)

    # ===== Routes =====

    @app.route('/')
    def root():
        """Endpoint raíz."""
        return {
            'service': 'Reportes Service',
            'version': '2.0.0',
            'status': 'running',
            'endpoints': {
                'health': '/health',
                'metrics': '/metrics',
                'reports_json': '/api/reportes',
                'reports_pdf': '/api/reportes/export/pdf',
                'reports_excel': '/api/reportes/export/excel',
                'stats': '/api/stats'
            }
        }, 200

    @app.route('/health', methods=['GET'])
    def health_check():
        """
        Health check del servicio.

        Returns:
            200: Servicio saludable
            503: Servicio degradado o no saludable
        """
        try:
            # Check database
            db_connected = db_manager.is_connected()
            db_stats = db_manager.get_stats()

            # Check cache
            cache_connected = cache_manager.is_connected() if config.CACHE_ENABLED else None
            cache_stats = cache_manager.get_stats() if config.CACHE_ENABLED else None

            # Determinar estado
            if db_connected:
                if cache_connected or not config.CACHE_ENABLED:
                    status = 'healthy'
                    status_code = 200
                else:
                    status = 'degraded'
                    status_code = 200
            else:
                status = 'unhealthy'
                status_code = 503

            response = {
                'status': status,
                'version': '2.0.0',
                'database': {
                    'connected': db_connected,
                    'type': config.DB_TYPE,
                    'latency_ms': None
                },
                'uptime_seconds': int(time.time() - START_TIME)
            }

            if config.CACHE_ENABLED and cache_stats:
                response['cache'] = {
                    'connected': cache_connected,
                    'hit_rate': cache_stats.get('hit_rate', 0.0)
                }

            return jsonify(response), status_code

        except Exception as e:
            logger.error(f"Error en health check: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 503

    @app.route('/metrics', methods=['GET'])
    def metrics():
        """
        Endpoint de métricas Prometheus.

        Returns:
            Métricas en formato Prometheus
        """
        if not config.METRICS_ENABLED:
            return jsonify({'error': 'Metrics disabled'}), 404

        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

    @app.route('/api/reportes', methods=['GET'])
    @require_api_key('reports:read') if config.API_AUTH_ENABLED else optional_api_key
    def get_reports_json():
        """
        Genera y retorna reportes en formato JSON.

        Query params:
            report_type: ventas|productos|clientes|revenue_categoria|resumen
            period: dia|semana|mes|trimestre|año|personalizado
            start_date: Fecha inicio (YYYY-MM-DD) para periodo personalizado
            end_date: Fecha fin (YYYY-MM-DD) para periodo personalizado

        Returns:
            200: Reporte generado exitosamente
            400: Parámetros inválidos
            500: Error del servidor
        """
        try:
            # Parsear parámetros
            report_type = request.args.get('report_type', 'ventas')
            period = request.args.get('period', 'semana')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            # Crear request object
            request_data = {
                'report_type': report_type,
                'period': period,
                'format': 'json'
            }

            # Agregar date_range si es personalizado
            if period == 'personalizado' and start_date and end_date:
                request_data['date_range'] = {
                    'start_date': start_date,
                    'end_date': end_date
                }

            # Validar con Pydantic
            try:
                report_request = ReportRequest(**request_data)
            except ValidationError as e:
                return jsonify({
                    'success': False,
                    'error': 'Parámetros inválidos',
                    'details': e.errors()
                }), 400

            # Generar reporte
            result = report_service.generate_report(report_request)

            return jsonify({
                'success': True,
                **result
            }), 200

        except Exception as e:
            logger.error(f"Error en /api/reportes: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/reportes/export/pdf', methods=['GET'])
    @require_api_key('reports:generate') if config.API_AUTH_ENABLED else optional_api_key
    def export_pdf():
        """
        Exporta reporte en formato PDF.

        Query params: Igual que /api/reportes

        Returns:
            200: PDF generado
            400: Parámetros inválidos
            500: Error del servidor
        """
        try:
            # Parsear parámetros
            report_type = request.args.get('report_type', 'ventas')
            period = request.args.get('period', 'semana')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            # Crear request
            request_data = {
                'report_type': report_type,
                'period': period,
                'format': 'pdf'
            }

            if period == 'personalizado' and start_date and end_date:
                request_data['date_range'] = {
                    'start_date': start_date,
                    'end_date': end_date
                }

            report_request = ReportRequest(**request_data)

            # Generar datos del reporte
            report_data = report_service.generate_report(report_request)

            # Generar PDF según el tipo
            if report_type == 'ventas':
                pdf_buffer = pdf_generator.generate_sales_report(report_data, period)
            elif report_type == 'productos':
                pdf_buffer = pdf_generator.generate_products_report(report_data, period)
            elif report_type == 'clientes':
                pdf_buffer = pdf_generator.generate_customers_report(report_data, period)
            else:
                pdf_buffer = pdf_generator.generate_generic_report(
                    report_data,
                    f"Reporte de {report_type.title()}",
                    period
                )

            return send_file(
                pdf_buffer,
                as_attachment=True,
                download_name=f'reporte_{report_type}_{period}.pdf',
                mimetype='application/pdf'
            )

        except ValidationError as e:
            return jsonify({
                'success': False,
                'error': 'Parámetros inválidos',
                'details': e.errors()
            }), 400

        except Exception as e:
            logger.error(f"Error generando PDF: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Error generando PDF'
            }), 500

    @app.route('/api/reportes/export/excel', methods=['GET'])
    @require_api_key('reports:generate') if config.API_AUTH_ENABLED else optional_api_key
    def export_excel():
        """
        Exporta reporte en formato Excel.

        Query params: Igual que /api/reportes

        Returns:
            200: Excel generado
            400: Parámetros inválidos
            500: Error del servidor
        """
        try:
            report_type = request.args.get('report_type', 'ventas')
            period = request.args.get('period', 'semana')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            request_data = {
                'report_type': report_type,
                'period': period,
                'format': 'excel'
            }

            if period == 'personalizado' and start_date and end_date:
                request_data['date_range'] = {
                    'start_date': start_date,
                    'end_date': end_date
                }

            report_request = ReportRequest(**request_data)

            # Generar datos
            report_data = report_service.generate_report(report_request)

            # Generar Excel
            if report_type == 'ventas':
                excel_buffer = excel_generator.generate_sales_report(report_data, period)
            elif report_type == 'productos':
                excel_buffer = excel_generator.generate_products_report(report_data, period)
            elif report_type == 'clientes':
                excel_buffer = excel_generator.generate_customers_report(report_data, period)
            else:
                return jsonify({
                    'success': False,
                    'error': f'Tipo de reporte no soportado para Excel: {report_type}'
                }), 400

            return send_file(
                excel_buffer,
                as_attachment=True,
                download_name=f'reporte_{report_type}_{period}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        except ValidationError as e:
            return jsonify({
                'success': False,
                'error': 'Parámetros inválidos',
                'details': e.errors()
            }), 400

        except Exception as e:
            logger.error(f"Error generando Excel: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Error generando Excel'
            }), 500

    @app.route('/api/stats', methods=['GET'])
    @optional_api_key
    def get_stats():
        """
        Obtiene estadísticas del servicio.

        Returns:
            200: Estadísticas
        """
        try:
            stats = {
                'database': db_manager.get_stats(),
                'cache': cache_manager.get_stats() if config.CACHE_ENABLED else None,
                'uptime_seconds': int(time.time() - START_TIME)
            }

            return jsonify({
                'success': True,
                'stats': stats
            }), 200

        except Exception as e:
            logger.error(f"Error obteniendo stats: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    # ===== Cleanup =====
    @app.teardown_appcontext
    def cleanup(error=None):
        """Limpieza al cerrar."""
        if error:
            logger.error(f"Error en teardown: {error}")

    import atexit
    atexit.register(lambda: db_manager.cleanup())
    atexit.register(lambda: cache_manager.cleanup())

    logger.info("✅ Aplicación configurada correctamente")

    return app


# ===== Punto de entrada =====
if __name__ == '__main__':
    app = create_app()
    config = get_config()

    logger.info("=" * 70)
    logger.info("🚀 INICIANDO SERVICIO DE REPORTES v2.0")
    logger.info("=" * 70)
    logger.info(f"   Host: {config.HOST}")
    logger.info(f"   Port: {config.PORT}")
    logger.info(f"   Debug: {config.DEBUG}")
    logger.info(f"   DB Type: {config.DB_TYPE}")
    logger.info(f"   Cache: {'✅ Habilitado' if config.CACHE_ENABLED else '❌ Deshabilitado'}")
    logger.info(f"   API Auth: {'✅ Habilitado' if config.API_AUTH_ENABLED else '❌ Deshabilitado'}")
    logger.info(f"   Rate Limiting: {'✅ Habilitado' if config.RATELIMIT_ENABLED else '❌ Deshabilitado'}")
    logger.info(f"   Metrics: {'✅ Habilitado' if config.METRICS_ENABLED else '❌ Deshabilitado'}")
    logger.info("=" * 70)

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
