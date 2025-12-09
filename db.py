import os
import sqlite3
from flask import g

try:
    import mysql.connector
    from mysql.connector import pooling
    MYSQL_AVAILABLE = True
except ImportError:
    mysql = None
    pooling = None
    MYSQL_AVAILABLE = False

# --- Configuración del Pool de Conexiones ---
db_pool = None

def init_app_db(app):
    """Inicializa la conexión a la base de datos (SQLite o MySQL)."""
    global db_pool
    
    # Determinar tipo de DB basado en variables de entorno
    # Si DB_TYPE no está definido, intentamos inferir o usar SQLite por defecto
    db_type = os.getenv('DB_TYPE', 'sqlite')
    
    if db_type == 'mysql':
        if not MYSQL_AVAILABLE:
            app.logger.error("mysql-connector-python no está instalado. Cambiando a SQLite.")
            db_type = 'sqlite'
        else:
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
                app.logger.info("Pool de conexiones MySQL inicializado.")
            except Exception as err:
                app.logger.error(f"Error al inicializar el pool MySQL: {err}")
                db_pool = None
                db_type = 'sqlite'
    else:
        # Configuración SQLite
        # Intentar encontrar la DB del Hub automáticamente si no se especifica
        db_path = os.getenv('SQLITE_DB_PATH')
        if not db_path:
            # Fallback: Asumir estructura de directorios standard
            # reportes_service/ -> root -> HubPedidos/db.sqlite3
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(current_dir)
            db_path = os.path.join(root_dir, 'HubPedidos', 'db.sqlite3')
        
        
        app.config['SQLITE_DB_PATH'] = db_path
        app.logger.info(f"Usando base de datos SQLite en: {db_path}")
    
    # Store the final db_type in app config so get_db can use it
    app.config['DB_TYPE'] = db_type

def get_db():
    """
    Obtiene una conexión a la base de datos.
    """
    if 'db' not in g:
        # Usar la configuración de Flask que puede haber sido actualizada en init_app_db
        db_type = current_app.config.get('DB_TYPE', os.getenv('DB_TYPE', 'sqlite'))
        
        if db_type == 'mysql':
            if db_pool and MYSQL_AVAILABLE:
                try:
                    g.db = db_pool.get_connection()
                    g.db_type = 'mysql'
                except Exception as err:
                    raise RuntimeError(f"No se pudo obtener conexión MySQL: {err}")
            else:
                raise RuntimeError("El pool MySQL no está inicializado.")
        else:
            # Conexión SQLite
            db_path = current_app.config.get('SQLITE_DB_PATH')
            try:
                # check_same_thread=False es necesario si se usa en múltiples hilos (común en Flask dev)
                g.db = sqlite3.connect(db_path, check_same_thread=False)
                g.db.row_factory = sqlite3.Row # Para acceder a columnas por nombre
                g.db_type = 'sqlite'
            except sqlite3.Error as e:
                raise RuntimeError(f"Error al conectar a SQLite: {e}")

    return g.db

def close_db(e=None):
    """Cierra la conexión."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

from flask import current_app