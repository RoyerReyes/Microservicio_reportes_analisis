import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

def create_app(testing=False):
    """Fábrica de la aplicación Flask."""
    # Cargar variables de entorno
    load_dotenv()

    app = Flask(__name__)
    app.config['TESTING'] = testing

    # Habilitar CORS
    CORS(app)

    # Configurar logging
    if not app.debug or testing:
        logging.basicConfig(level=logging.INFO)
        app.logger.setLevel(logging.INFO)

    # --- Inicialización de la Base de Datos ---
    import db
    db.init_app_db(app)
    # Registrar el cleanup de la base de datos
    app.teardown_appcontext(db.close_db)

    # --- Registro de Rutas ---
    @app.route('/health', methods=['GET'])
    def health_check():
        # En una implementación más avanzada, podríamos verificar la conexión a la BD aquí.
        return jsonify({"status": "ok", "service": "reportes"}), 200

    @app.route('/api/reportes', methods=['GET'])
    def generar_reportes_endpoint():
        """
        Endpoint principal que genera y devuelve todos los reportes.
        Acepta un parámetro 'periodo' en la URL (ej: /api/reportes?periodo=mes).
        """
        periodo = request.args.get('periodo', 'semana')
        
        import reports
        try:
            reportes = {
                'ventas': reports.get_ventas_report(periodo),
                'productos_mas_vendidos': reports.get_productos_mas_vendidos_report(periodo),
                'pedidos_por_cliente': reports.get_pedidos_por_cliente_report(periodo)
            }
            return jsonify(reportes)
        except Exception as e:
            app.logger.error(f"Error al generar reportes: {e}")
            # El error ya fue logueado en la capa de `reports`, pero podemos añadir un log a nivel de API.
            return jsonify({"error": "Ocurrió un error al generar los reportes."}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # Ejecutar en el puerto 5001
    app.run(debug=True, port=5001)
