from datetime import datetime, timedelta
from flask import current_app
from db import get_db

def get_start_date(periodo):
    """Calcula la fecha de inicio basado en el periodo ('semana', 'mes', 'año')."""
    today = datetime.now()
    if periodo == 'mes':
        return today - timedelta(days=30)
    elif periodo == 'año':
        return today - timedelta(days=365)
    else: # Por defecto, 'semana'
        return today - timedelta(days=7)

def get_ventas_report(periodo):
    """Obtiene el reporte de ventas por día."""
    start_date = get_start_date(periodo)
    db = get_db()
    cursor = db.cursor(dictionary=True)
    query = """
        SELECT DATE(fecha_pedido) as periodo, SUM(total) as total_ventas
        FROM pedidos_pedido
        WHERE estado = 'COMPLETADO' AND fecha_pedido >= %s
        GROUP BY DATE(fecha_pedido) ORDER BY periodo;
    """
    try:
        cursor.execute(query, (start_date,))
        return cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error en get_ventas_report: {e}")
        return []
    finally:
        cursor.close()

def get_productos_mas_vendidos_report(periodo):
    """Obtiene el reporte de los 10 productos más vendidos."""
    start_date = get_start_date(periodo)
    db = get_db()
    cursor = db.cursor(dictionary=True)
    query = """
        SELECT p.nombre, SUM(dp.cantidad) as total_vendido
        FROM pedidos_detallepedido dp
        JOIN pedidos_producto p ON dp.producto_id = p.id
        JOIN pedidos_pedido pe ON dp.pedido_id = pe.id
        WHERE pe.estado = 'COMPLETADO' AND pe.fecha_pedido >= %s
        GROUP BY p.nombre ORDER BY total_vendido DESC LIMIT 10;
    """
    try:
        cursor.execute(query, (start_date,))
        return cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error en get_productos_mas_vendidos_report: {e}")
        return []
    finally:
        cursor.close()

def get_pedidos_por_cliente_report(periodo):
    """Obtiene el reporte de la cantidad de pedidos por cliente."""
    start_date = get_start_date(periodo)
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # El nombre del reporte original era 'pedidos_por_trabajador', lo que era confuso.
    # El query apunta a 'cliente_id' en 'pedidos_pedido' y a 'auth_user', 
    # por lo que 'pedidos_por_cliente' es más preciso.
    query = """
        SELECT u.id, u.username, u.first_name, u.last_name, COUNT(p.id) as cantidad_pedidos
        FROM auth_user u
        JOIN pedidos_pedido p ON u.id = p.cliente_id
        WHERE p.fecha_pedido >= %s
        GROUP BY u.id, u.username, u.first_name, u.last_name
        ORDER BY cantidad_pedidos DESC;
    """
    try:
        cursor.execute(query, (start_date,))
        return cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error en get_pedidos_por_cliente_report: {e}")
        return []
    finally:
        cursor.close()
