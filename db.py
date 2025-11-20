import os
import mysql.connector
from mysql.connector import pooling
from flask import g

# --- Configuración del Pool de Conexiones ---
# Se inicializa a None y se configurará en la fábrica de la aplicación
db_pool = None

def init_app_db(app):
    """Inicializa el pool de conexiones a la base de datos con la configuración de la app."""
    global db_pool
    try:
        db_config = {
            'host': os.getenv('DB_HOST'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME'),
        }
        db_pool = pooling.MySQLConnectionPool(
            pool_name="reportes_pool",
            pool_size=5,
            **db_config
        )
        app.logger.info("Pool de conexiones a la base de datos inicializado.")
    except mysql.connector.Error as err:
        app.logger.error(f"Error al inicializar el pool de conexiones: {err}")
        db_pool = None

def get_db():
    """
    Abre una nueva conexión a la base de datos si no hay ninguna para el contexto actual de la aplicación.
    La reutiliza si ya existe en `g`.
    """
    if 'db' not in g:
        if db_pool:
            try:
                g.db = db_pool.get_connection()
            except mysql.connector.Error as err:
                # Si el pool no está disponible, esto fallará.
                # Se podría manejar un fallback o simplemente dejar que falle.
                raise RuntimeError(f"No se pudo obtener una conexión de la base de datos: {err}")
        else:
            raise RuntimeError("El pool de la base de datos no está inicializado.")
    return g.db

def close_db(e=None):
    """
    Cierra la conexión a la base de datos al final de la petición.
    Se registra para ser llamada automáticamente por Flask.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()
