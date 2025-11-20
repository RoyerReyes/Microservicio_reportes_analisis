import unittest
from unittest.mock import patch, MagicMock
from app import create_app

class TestReportesService(unittest.TestCase):

    def setUp(self):
        """Crea una nueva instancia de la app para cada prueba."""
        self.app = create_app(testing=True)
        self.client = self.app.test_client()

    def test_health_check(self):
        """Prueba que el endpoint /health funcione correctamente."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok", "service": "reportes"})

    @patch('reports.get_db')
    def test_generar_reportes_endpoint(self, mock_get_db):
        """
        Prueba el endpoint /api/reportes, mockeando la base de datos para asegurar
        que el endpoint procesa y devuelve los datos correctamente.
        """
        # --- Configuración del Mock ---
        mock_ventas_data = [{'periodo': '2023-10-10', 'total_ventas': 100.0}]
        mock_productos_data = [{'nombre': 'Producto Estrella', 'total_vendido': 50}]
        mock_clientes_data = [{'username': 'cliente_top', 'cantidad_pedidos': 15}]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            mock_ventas_data,
            mock_productos_data,
            mock_clientes_data
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value = mock_conn

        # --- Llamada a la API ---
        response = self.client.get('/api/reportes?periodo=semana')
        
        # --- Aserciones ---
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        
        self.assertIn('ventas', json_data)
        self.assertIn('productos_mas_vendidos', json_data)
        self.assertIn('pedidos_por_cliente', json_data)
        
        self.assertEqual(json_data['ventas'], mock_ventas_data)
        self.assertEqual(json_data['productos_mas_vendidos'], mock_productos_data)
        self.assertEqual(json_data['pedidos_por_cliente'], mock_clientes_data)
        
        # Se crea un cursor para cada una de las 3 consultas de reporte
        self.assertEqual(mock_conn.cursor.call_count, 3)
        
        # Se ejecuta una consulta por cada reporte
        self.assertEqual(mock_cursor.execute.call_count, 3)

    @patch('reports.get_db')
    def test_api_endpoint_handles_db_error(self, mock_get_db):
        """
        Prueba que el endpoint de la API devuelva un 500 si la base de datos falla.
        """
        # Simular que get_db lanza una excepción
        mock_get_db.side_effect = Exception("Fallo de base de datos simulado")
        
        response = self.client.get('/api/reportes')
        
        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.get_json())


if __name__ == '__main__':
    unittest.main()
