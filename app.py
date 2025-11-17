import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import mysql.connector
from datetime import datetime, timedelta

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- Configuración de la Aplicación Flask ---
app = Flask(__name__)
CORS(app) # Habilitar CORS para permitir peticiones desde nuestro frontend

# --- Configuración de la Base de Datos ---
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
}

def get_db_connection():
    """Crea y devuelve una nueva conexión a la base de datos."""
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error de conexión a la base de datos: {err}")
        return None

def get_start_date(periodo):
    """Calcula la fecha de inicio basado en el periodo ('semana', 'mes', 'año')."""
    today = datetime.now()
    if periodo == 'mes':
        return today - timedelta(days=30)
    elif periodo == 'año':
        return today - timedelta(days=365)
    else: # Por defecto, 'semana'
        return today - timedelta(days=7)

@app.route('/api/reportes', methods=['GET'])
def generar_reportes_endpoint():
    """
    Endpoint principal que genera y devuelve los reportes.
    Acepta un parámetro 'periodo' en la URL (ej: /api/reportes?periodo=mes).
    """
    periodo = request.args.get('periodo', 'semana')
    start_date = get_start_date(periodo)
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos."}), 500

    cursor = conn.cursor(dictionary=True) # Devuelve filas como diccionarios
    reportes = {}

    try:
        # 1. Reporte de Ventas por Día
        query_ventas = """
            SELECT DATE(fecha_pedido) as periodo, SUM(total) as total_ventas
            FROM pedidos_pedido
            WHERE estado = 'COMPLETADO' AND fecha_pedido >= %s
            GROUP BY DATE(fecha_pedido) ORDER BY periodo;
        """
        cursor.execute(query_ventas, (start_date,))
        reportes['ventas'] = cursor.fetchall()

        # 2. Reporte de Productos Más Vendidos
        query_productos = """
            SELECT p.nombre, SUM(dp.cantidad) as total_vendido
            FROM pedidos_detallepedido dp
            JOIN pedidos_producto p ON dp.producto_id = p.id
            JOIN pedidos_pedido pe ON dp.pedido_id = pe.id
            WHERE pe.estado = 'COMPLETADO' AND pe.fecha_pedido >= %s
            GROUP BY p.nombre ORDER BY total_vendido DESC LIMIT 10;
        """
        cursor.execute(query_productos, (start_date,))
        reportes['productos_mas_vendidos'] = cursor.fetchall()

        # 3. Reporte de Pedidos por Cliente/Trabajador
        query_pedidos_trabajador = """
            SELECT u.id, u.username, u.first_name, u.last_name, COUNT(p.id) as cantidad_pedidos
            FROM auth_user u
            JOIN pedidos_pedido p ON u.id = p.cliente_id
            WHERE p.fecha_pedido >= %s
            GROUP BY u.id, u.username, u.first_name, u.last_name
            ORDER BY cantidad_pedidos DESC;
        """
        cursor.execute(query_pedidos_trabajador, (start_date,))
        reportes['pedidos_por_trabajador'] = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"Error al ejecutar consulta: {err}")
        return jsonify({"error": "Ocurrió un error al generar los reportes."}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(reportes)

if __name__ == '__main__':
    # Ejecutar el microservicio en el puerto 5001 para no chocar con Django (8000) o Vite (5173)
    app.run(debug=True, port=5001)